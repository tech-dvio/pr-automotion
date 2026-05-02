"""
PR Review Agent — Pipeline Test Script
=======================================
Run this on Railway (or locally with the right env vars) to verify each
component works before a real PR arrives.

Usage:
    python test_pipeline.py                    # test DB + SMTP only
    python test_pipeline.py --github           # also test GitHub API
    python test_pipeline.py --review owner/repo 123   # dry-run full review
    python test_pipeline.py --email you@example.com   # send test email
"""

import argparse
import asyncio
import os
import sys

# Allow running from the backend/ directory directly
sys.path.insert(0, os.path.dirname(__file__))


def section(title: str):
    print(f"\n{'='*55}")
    print(f"  {title}")
    print(f"{'='*55}")


# ── 1. Database ───────────────────────────────────────────────────────────────

def test_database():
    section("1. DATABASE")
    try:
        from database import init_db, SessionLocal, Repo, EmailRecipient, GlobalSetting
        init_db()
        db = SessionLocal()
        repos = db.query(Repo).all()
        settings = db.query(GlobalSetting).all()
        recipients = db.query(EmailRecipient).all()
        print(f"  ✓ DB connected")
        print(f"  ✓ Repos: {len(repos)}")
        print(f"  ✓ Settings keys: {[s.key for s in settings]}")
        print(f"  ✓ Email recipients: {len(recipients)}")
        db.close()
        return True
    except Exception as e:
        print(f"  ✗ DB error: {e}")
        return False


# ── 2. Global Settings ────────────────────────────────────────────────────────

def test_settings():
    section("2. GLOBAL SETTINGS")
    try:
        from database import SessionLocal, GlobalSetting
        from encryption import decrypt
        db = SessionLocal()
        keys = ["anthropic_api_key", "smtp_host", "smtp_port", "smtp_username",
                "smtp_sender_email", "webhook_base_url"]
        for key in keys:
            row = db.query(GlobalSetting).filter_by(key=key).first()
            if row and row.value_enc:
                val = decrypt(row.value_enc)
                display = "••••••••" if key in ("anthropic_api_key", "smtp_password") else val
                status = "✓" if val else "✗ empty"
                print(f"  {status}  {key}: {display}")
            else:
                print(f"  ✗ missing  {key}")
        db.close()
        return True
    except Exception as e:
        print(f"  ✗ Settings error: {e}")
        return False


# ── 3. SMTP Email ─────────────────────────────────────────────────────────────

def test_smtp(to_email: str = None):
    section("3. SMTP EMAIL")
    try:
        from database import SessionLocal, GlobalSetting
        from encryption import decrypt

        db = SessionLocal()
        def _read(key):
            row = db.query(GlobalSetting).filter_by(key=key).first()
            return decrypt(row.value_enc) if row and row.value_enc else ""

        host     = _read("smtp_host")
        port_raw = _read("smtp_port")
        username = _read("smtp_username")
        password = _read("smtp_password")
        sender   = _read("smtp_sender_email") or username
        db.close()

        if not host or not username:
            print("  ✗ SMTP not configured (smtp_host / smtp_username missing)")
            return False

        port = int(port_raw) if port_raw.isdigit() else 587
        print(f"  Host    : {host}:{port}")
        print(f"  Username: {username}")
        print(f"  Sender  : {sender}")

        import socket
        try:
            sock = socket.create_connection((host, port), timeout=10)
            sock.close()
            print(f"  ✓ TCP reachable on port {port}")
        except Exception as e:
            print(f"  ✗ Cannot reach {host}:{port} — {e}")
            if "amazonaws" in host:
                print("    Hint: AWS SES blocks port 587 on many cloud hosts. Try port 2587.")
            return False

        if to_email:
            import smtplib, ssl
            from email.mime.multipart import MIMEMultipart
            from email.mime.text import MIMEText

            msg = MIMEMultipart("alternative")
            msg["Subject"] = "✅ PR Review Agent — Pipeline Test"
            msg["From"] = sender
            msg["To"] = to_email
            msg.attach(MIMEText(
                "<h2>Pipeline test passed</h2><p>SMTP is working correctly.</p>",
                "html", "utf-8"
            ))

            ctx = ssl.create_default_context()
            ssl_ports = {465, 2465}
            try:
                if port in ssl_ports:
                    with smtplib.SMTP_SSL(host, port, context=ctx, timeout=15) as server:
                        server.login(username, password)
                        server.sendmail(sender, [to_email], msg.as_string())
                else:
                    with smtplib.SMTP(host, port, timeout=15) as server:
                        server.ehlo()
                        server.starttls(context=ctx)
                        server.ehlo()
                        server.login(username, password)
                        server.sendmail(sender, [to_email], msg.as_string())
                print(f"  ✓ Test email sent to {to_email}")
            except smtplib.SMTPAuthenticationError:
                print("  ✗ Auth failed — check smtp_username and smtp_password")
                return False
            except Exception as e:
                print(f"  ✗ Send failed: {e}")
                return False
        else:
            print("  (skipping send — pass --email addr@example.com to send a test)")

        return True
    except Exception as e:
        print(f"  ✗ SMTP test error: {e}")
        return False


# ── 4. GitHub API ─────────────────────────────────────────────────────────────

def test_github(repo_full_name: str = None):
    section("4. GITHUB API")
    try:
        from database import SessionLocal, Repo
        from encryption import decrypt
        from pr_agent import GitHubClient

        db = SessionLocal()
        rows = db.query(Repo).filter_by(webhook_active=True).all()
        db.close()

        if not rows:
            print("  ✗ No active repos found in DB")
            return False

        target = None
        for r in rows:
            if repo_full_name is None or r.repo_full_name == repo_full_name:
                target = r
                break

        if not target:
            print(f"  ✗ Repo '{repo_full_name}' not found")
            return False

        token = decrypt(target.github_token_enc)
        gh = GitHubClient(token)

        user = gh.get("https://api.github.com/user")
        print(f"  ✓ GitHub token valid — authenticated as: {user.get('login')}")
        print(f"  ✓ Testing repo: {target.repo_full_name}")

        repo_data = gh.get(f"https://api.github.com/repos/{target.repo_full_name}")
        print(f"  ✓ Repo accessible: {repo_data.get('full_name')} (private={repo_data.get('private')})")

        open_prs = gh.list_open_prs(target.repo_full_name)
        print(f"  ✓ Open PRs: {len(open_prs)}")
        return True

    except Exception as e:
        import traceback
        print(f"  ✗ GitHub error: {e}")
        traceback.print_exc()
        return False


# ── 5. Full Dry-Run Review ────────────────────────────────────────────────────

def test_review(repo_full_name: str, pr_number: int):
    section(f"5. FULL DRY-RUN REVIEW — {repo_full_name} #{pr_number}")
    try:
        from database import SessionLocal, Repo
        from encryption import decrypt
        from config_loader import build_review_config, build_email_config
        from pr_agent import review_pr, GitHubClient
        from smtp_notifier import SmtpNotifier

        db = SessionLocal()
        row = db.query(Repo).filter_by(repo_full_name=repo_full_name, webhook_active=True).first()
        if not row:
            print(f"  ✗ Repo '{repo_full_name}' not found or not active")
            db.close()
            return False

        token = decrypt(row.github_token_enc)
        review_cfg = build_review_config(row)
        email_cfg = build_email_config(row, db)
        db.close()

        from database import GlobalSetting
        db2 = SessionLocal()
        row2 = db2.query(GlobalSetting).filter_by(key="anthropic_api_key").first()
        anthropic_key = decrypt(row2.value_enc) if row2 and row2.value_enc else ""
        db2.close()

        if anthropic_key:
            os.environ["ANTHROPIC_API_KEY"] = anthropic_key
            print(f"  ✓ Anthropic API key loaded")
        else:
            print("  ✗ Anthropic API key not configured — review will fail")
            return False

        gh = GitHubClient(token)
        notifier = SmtpNotifier(email_cfg) if email_cfg.enabled else None

        print(f"  Running DRY RUN (will NOT post to GitHub or send emails)…")
        result = asyncio.run(review_pr(
            config=review_cfg,
            pr_number=pr_number,
            gh=gh,
            notifier=None,   # no email in dry run
            dry_run=True,
        ))
        print(f"\n  ✓ Dry-run complete")
        print(f"  Verdict : {result.get('verdict', '?')}")
        print(f"  Score   : {result.get('score', '?')}/100")
        print(f"  Issues  : {len(result.get('issues', []))}")

        _ = notifier  # referenced to avoid lint warning
        return True

    except Exception as e:
        import traceback
        print(f"  ✗ Review failed: {e}")
        traceback.print_exc()
        return False


# ── 6. Email Recipient Config ─────────────────────────────────────────────────

def test_recipients():
    section("6. EMAIL RECIPIENTS")
    try:
        from database import SessionLocal, Repo, EmailRecipient
        db = SessionLocal()
        repos = db.query(Repo).filter_by(webhook_active=True).all()
        for repo in repos:
            recipients = db.query(EmailRecipient).filter_by(repo_id=repo.id).all()
            print(f"\n  Repo: {repo.repo_full_name}")
            if not recipients:
                print("    ⚠️  No email recipients configured — notifications will be skipped")
            else:
                for r in recipients:
                    print(f"    ✓ {r.email} [{r.role}]")
        db.close()
        return True
    except Exception as e:
        print(f"  ✗ Error: {e}")
        return False


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PR Review Agent — Pipeline Test")
    parser.add_argument("--email",   metavar="ADDR",      help="Send a test email to this address")
    parser.add_argument("--github",  action="store_true", help="Test GitHub API connectivity")
    parser.add_argument("--review",  nargs=2, metavar=("REPO", "PR"), help="Dry-run review e.g. owner/repo 42")
    args = parser.parse_args()

    results = {}
    results["db"]         = test_database()
    results["settings"]   = test_settings()
    results["smtp"]       = test_smtp(args.email)
    results["recipients"] = test_recipients()

    if args.github or args.review:
        repo_arg = args.review[0] if args.review else None
        results["github"] = test_github(repo_arg)

    if args.review:
        results["review"] = test_review(args.review[0], int(args.review[1]))

    # Summary
    section("SUMMARY")
    all_ok = True
    for name, ok in results.items():
        icon = "✓" if ok else "✗"
        print(f"  {icon}  {name}")
        if not ok:
            all_ok = False

    print()
    if all_ok:
        print("  All checks passed. Pipeline is ready.")
    else:
        print("  Some checks failed. Fix the issues above and re-run.")
    print()
    sys.exit(0 if all_ok else 1)
