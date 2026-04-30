# Deployment Guide — PR Review Agent Dashboard

## Overview

The dashboard is deployed as a single Docker container on **Fly.io** (free tier, always-on). It includes:
- Python FastAPI backend (API + webhook receiver)
- React frontend (served as static files)
- SQLite database on a persistent Fly volume

**Why Fly.io?** It's the only major platform with a free tier that keeps your app running 24/7 without sleeping. This is critical because GitHub needs to deliver webhook events at any time — Render's free tier would spin down after 15 minutes and miss events.

---

## Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) installed
- Node.js 20+ installed
- Python 3.12+ installed
- A free [Fly.io account](https://fly.io/app/sign-up)

---

## First-Time Deployment

### Step 1 — Install flyctl

```bash
# macOS/Linux
curl -L https://fly.io/install.sh | sh

# Windows (PowerShell)
pwsh -Command "iwr https://fly.io/install.ps1 -useb | iex"
```

### Step 2 — Log in to Fly.io

```bash
fly auth login
```

### Step 3 — Create the Fly app

```bash
cd pr-review-dashboard

# Create app (don't deploy yet)
fly launch --no-deploy --name pr-review-dashboard-new
```

> If `pr-review-dashboard` name is taken, choose another name. Update `fly.toml` with the new app name.

### Step 4 — Create a persistent volume for SQLite

```bash
fly volumes create dashboard_data --region iad --size 1
```

> The region `iad` is US East (Virginia). Choose the closest to you:  
> `lhr` (London), `fra` (Frankfurt), `sin` (Singapore), `syd` (Sydney), `nrt` (Tokyo)

### Step 5 — Generate and set secrets

```bash
# Generate a Fernet encryption key
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# Set secrets (these are stored encrypted by Fly, never in fly.toml)
fly secrets set SECRET_KEY="<paste generated key>"
fly secrets set ADMIN_TOKEN="<choose a strong password for the dashboard>"
```

### Step 6 — Build and deploy

```bash
fly deploy
```

This runs the two-stage Docker build (Node → Python) and deploys to Fly.io. First deploy takes ~3-4 minutes.

### Step 7 — Set your webhook base URL

After deploy, your app URL is `https://pr-review-dashboard.fly.dev` (or your custom name).

Open the dashboard, go to **Settings**, and set **Webhook Base URL** to:
```
https://pr-review-dashboard.fly.dev
```

### Step 8 — Open the dashboard

```bash
fly open
```

Log in with the `ADMIN_TOKEN` you set in Step 5.

---

## Subsequent Deploys

```bash
fly deploy
```

The SQLite database on the persistent volume is preserved across all deploys.

---

## Adding a Repository

1. Click **Add Repository** in the sidebar
2. Fill in:
   - **Repository**: `owner/repo` format (e.g., `acme/backend-api`)
   - **GitHub Token**: Personal Access Token with `repo` + `admin:repo_hook` scopes
   - **Webhook Secret**: Click **Generate** or enter your own
   - **Email Recipients**: Add each person and their notification role
3. Click **Add Repository**

The agent will:
- Validate your GitHub token
- Register a webhook on the GitHub repo automatically
- Start receiving PR events immediately

---

## GitHub Token Scopes

Your GitHub Personal Access Token needs:
- `repo` — to read PR diffs and post review comments
- `admin:repo_hook` — to register/manage webhooks on the repository

Generate at: **GitHub → Settings → Developer settings → Personal access tokens → Fine-grained tokens**

---

## Email Setup (Optional)

Email notifications require a Microsoft 365 mailbox and Azure app registration.

### Azure Setup (one-time)

1. Go to [portal.azure.com](https://portal.azure.com) → **Azure Active Directory** → **App registrations** → **New registration**
2. Name: `PR Review Bot`, Account type: Single tenant
3. Under **API permissions** → **Add a permission** → **Microsoft Graph** → **Application permissions** → `Mail.Send`
4. Click **Grant admin consent**
5. Under **Certificates & secrets** → **New client secret** → copy the value
6. Copy **Application (client) ID** and **Directory (tenant) ID** from the Overview page

### Enter in Settings

Open **Settings** in the dashboard and fill in:
- Azure Tenant ID
- Azure Client ID
- Azure Client Secret
- Outlook Sender Email (a licensed M365 mailbox)

---

## Monitoring & Logs

```bash
# View live logs
fly logs

# Check app status
fly status

# SSH into the container
fly ssh console
```

---

## Local Development

### Backend

```bash
cd pr-review-dashboard

# Create .env from example
cp .env.example .env
# Edit .env: set SECRET_KEY, ADMIN_TOKEN, WEBHOOK_BASE_URL=http://localhost:8080

# Install Python deps
pip install -r requirements.txt

# Run the backend
uvicorn backend.main:app --reload --port 8080
```

### Frontend (separate terminal)

```bash
cd pr-review-dashboard/frontend

# Install deps
npm install

# Start dev server (proxies /api to localhost:8080)
npm run dev
```

Open `http://localhost:5173` — the Vite dev server proxies API calls to the Python backend.

### Expose webhook to GitHub (for testing)

```bash
# Install ngrok (free)
# https://ngrok.com/download

ngrok http 8080
# Copy the https URL (e.g., https://abc123.ngrok-free.app)
# Set WEBHOOK_BASE_URL=https://abc123.ngrok-free.app in Settings
```

---

## Environment Variables Reference

| Variable | Required | Description |
|----------|----------|-------------|
| `SECRET_KEY` | ✅ | Fernet key for encrypting credentials at rest |
| `ADMIN_TOKEN` | ✅ | Password to access the dashboard |
| `WEBHOOK_BASE_URL` | ✅ | Public URL of this server (set in Settings UI) |
| `DATABASE_URL` | — | SQLite path (default: `sqlite:////data/dashboard.db`) |
| `ANTHROPIC_API_KEY` | — | Can be set in Settings UI instead |

---

## Free Tier Limits (Fly.io)

| Resource | Free Allowance |
|----------|---------------|
| VMs | 3 shared-cpu-1x |
| RAM | 256 MB per VM |
| Storage | 3 GB total volumes |
| Bandwidth | 160 GB/month |
| Always-on | Yes (no sleep) |

This dashboard uses 1 VM and 1 GB storage — well within the free tier.

---

## Scaling (When Needed)

The SQLite + single-VM design works well for:
- Up to ~50 monitored repositories
- Up to ~500 PR reviews per day
- 1-5 dashboard users

For higher scale, upgrade the VM size in `fly.toml`:
```toml
[[vm]]
  size = "shared-cpu-2x"   # $3/month
  memory = "512mb"
```

Or migrate to PostgreSQL by changing `DATABASE_URL` to a PostgreSQL connection string (Fly Postgres costs ~$0/month on free tier).

---

## Troubleshooting

**Dashboard shows "Connecting…"**  
→ The backend isn't running. Check `fly logs` for errors.

**"Admin token not configured on server"**  
→ `ADMIN_TOKEN` env var wasn't set. Run: `fly secrets set ADMIN_TOKEN="your-password"` then `fly deploy`.

**"Token lacks admin:repo_hook scope"**  
→ Regenerate your GitHub PAT with the `admin:repo_hook` permission checked.

**Webhook showing as inactive after registering**  
→ Ensure `WEBHOOK_BASE_URL` in Settings points to the correct public URL (not localhost).

**Email not sending**  
→ Verify Azure admin consent was granted for `Mail.Send`. Check that the sender email is a licensed M365 user (not a shared mailbox without a license).
