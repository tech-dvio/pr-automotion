"""
Outlook Email Notifier — PR Review Agent
=========================================
Sends rich HTML emails via Microsoft Graph API (Outlook / Microsoft 365).

Supports two auth methods:
  1. Client Credentials (app-only, recommended for servers/automation)
  2. Device Code Flow (interactive login, good for testing)

Setup (one-time):
  1. Go to https://portal.azure.com → Azure Active Directory → App Registrations
  2. Click "New registration" → name it "PR Review Bot"
  3. Under "API permissions" → Add → Microsoft Graph → Application permissions:
       - Mail.Send
  4. Click "Grant admin consent"
  5. Under "Certificates & secrets" → New client secret → copy it
  6. Copy the Application (client) ID and Tenant ID from the Overview page
  7. Add all three to your .env file

Email triggers:
  - 🔴 CRITICAL security issue found in any PR
  - 🟠 HIGH severity issues found (optional)
  - ✅ PR auto-merged successfully
  - 🚫 PR blocked (request changes posted)
  - 📋 Daily digest of all PRs reviewed (optional)
"""

import os
import json
import requests
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

from dotenv import load_dotenv

load_dotenv()


# ── Config ────────────────────────────────────────────────────────────────────

@dataclass
class EmailConfig:
    """Email notification configuration."""
    enabled: bool = True

    # Microsoft Graph / Azure AD credentials
    tenant_id: str     = field(default_factory=lambda: os.getenv("AZURE_TENANT_ID", ""))
    client_id: str     = field(default_factory=lambda: os.getenv("AZURE_CLIENT_ID", ""))
    client_secret: str = field(default_factory=lambda: os.getenv("AZURE_CLIENT_SECRET", ""))

    # The mailbox that sends the emails (must be licensed M365 user)
    sender_email: str  = field(default_factory=lambda: os.getenv("OUTLOOK_SENDER_EMAIL", ""))

    # Notification recipients — these get emailed on PR events
    notify_on_critical: list = field(default_factory=list)   # Always email on critical
    notify_on_high:     list = field(default_factory=list)   # Email on high severity
    notify_on_merge:    list = field(default_factory=list)   # Email when PR merged
    notify_on_block:    list = field(default_factory=list)   # Email when PR blocked
    notify_on_approve:  list = field(default_factory=list)   # Email when PR approved
    daily_digest_to:    list = field(default_factory=list)   # Daily summary recipients

    # Thresholds
    send_on_score_below: int = 60   # Also email if overall score drops below this


# ── Microsoft Graph Auth ──────────────────────────────────────────────────────

class GraphAuthClient:
    """Gets and caches access tokens from Microsoft identity platform."""

    TOKEN_URL = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
    GRAPH_URL = "https://graph.microsoft.com/v1.0"

    def __init__(self, config: EmailConfig):
        self.config = config
        self._token: Optional[str] = None
        self._token_expiry: Optional[datetime] = None

    def get_token(self) -> str:
        """Get a valid access token, refreshing if expired."""
        if self._token and self._token_expiry and datetime.now() < self._token_expiry:
            return self._token

        resp = requests.post(
            self.TOKEN_URL.format(tenant=self.config.tenant_id),
            data={
                "grant_type":    "client_credentials",
                "client_id":     self.config.client_id,
                "client_secret": self.config.client_secret,
                "scope":         "https://graph.microsoft.com/.default",
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()

        self._token = data["access_token"]
        # Tokens are valid for 3600s; refresh at 3500s to be safe
        from datetime import timedelta
        self._token_expiry = datetime.now() + timedelta(seconds=data.get("expires_in", 3600) - 100)
        return self._token

    def send_mail(self, sender: str, payload: dict) -> bool:
        """Send mail via Microsoft Graph sendMail endpoint."""
        token = self.get_token()
        resp = requests.post(
            f"{self.GRAPH_URL}/users/{sender}/sendMail",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type":  "application/json",
            },
            json=payload,
            timeout=30,
        )
        if resp.status_code == 202:
            return True
        print(f"  ✗ Graph API error {resp.status_code}: {resp.text[:300]}")
        return False


# ── HTML Email Templates ──────────────────────────────────────────────────────

def _severity_color(severity: str) -> str:
    return {"critical": "#C0392B", "high": "#E67E22", "medium": "#F1C40F",
            "low": "#3498DB", "info": "#95A5A6"}.get(severity, "#666")

def _severity_emoji(severity: str) -> str:
    return {"critical": "🔴", "high": "🟠", "medium": "🟡",
            "low": "🔵", "info": "ℹ️"}.get(severity, "•")

def _verdict_badge(verdict: str) -> tuple[str, str]:
    """Returns (color, label) for verdict badge."""
    return {
        "approve":         ("#27AE60", "✅ APPROVED"),
        "request_changes": ("#E67E22", "⚠️ CHANGES REQUESTED"),
        "block":           ("#C0392B", "🚫 BLOCKED"),
    }.get(verdict, ("#666", verdict.upper()))


def build_review_email_html(
    repo: str,
    pr_number: int,
    pr_title: str,
    author: str,
    review: dict,
    github_pr_url: str,
) -> tuple[str, str]:
    """
    Build subject + full HTML email body for a PR review notification.
    Returns (subject, html_body).
    """
    verdict        = review.get("verdict", "request_changes")
    score          = review.get("overall_score", 0)
    summary        = review.get("summary", "")
    issues         = review.get("issues", [])
    blockers       = review.get("approval_blockers", [])
    positives      = review.get("positives", [])
    has_security   = review.get("has_security_issues", False)
    badge_color, badge_label = _verdict_badge(verdict)

    # Group issues by severity
    critical_issues = [i for i in issues if i.get("severity") == "critical"]
    high_issues     = [i for i in issues if i.get("severity") == "high"]
    other_issues    = [i for i in issues if i.get("severity") not in ("critical", "high")]

    # Subject
    security_flag = " 🔐 SECURITY ALERT" if has_security else ""
    subject = f"[PR Review]{security_flag} #{pr_number} {pr_title} — {badge_label.split()[-1]} ({score}/100)"

    # Score bar color
    score_color = "#27AE60" if score >= 80 else "#E67E22" if score >= 60 else "#C0392B"

    def issues_rows(issue_list: list) -> str:
        if not issue_list:
            return ""
        rows = ""
        for issue in issue_list:
            sev   = issue.get("severity", "low")
            color = _severity_color(sev)
            emoji = _severity_emoji(sev)
            rows += f"""
            <tr>
              <td style="padding:8px 12px;border-bottom:1px solid #eee;">
                <span style="color:{color};font-weight:600;">{emoji} {sev.upper()}</span>
              </td>
              <td style="padding:8px 12px;border-bottom:1px solid #eee;font-family:monospace;font-size:12px;color:#555;">
                {issue.get('file','')}<span style="color:#999;">:{issue.get('line','')}</span>
              </td>
              <td style="padding:8px 12px;border-bottom:1px solid #eee;">
                <strong>{issue.get('title','')}</strong><br>
                <span style="color:#666;font-size:13px;">{issue.get('description','')}</span>
              </td>
              <td style="padding:8px 12px;border-bottom:1px solid #eee;">
                <span style="background:#f5f5f5;padding:2px 8px;border-radius:12px;font-size:12px;color:#333;">
                  {issue.get('category','')}
                </span>
              </td>
            </tr>"""
        return rows

    blockers_html = ""
    if blockers:
        items = "".join(f"<li style='margin:6px 0;color:#C0392B;'>{b}</li>" for b in blockers)
        blockers_html = f"""
        <div style="background:#FEF0F0;border-left:4px solid #C0392B;padding:16px 20px;margin:20px 0;border-radius:0 8px 8px 0;">
          <strong style="color:#C0392B;">🚫 Blockers — Must Fix Before Merge</strong>
          <ul style="margin:10px 0 0 0;padding-left:20px;">{items}</ul>
        </div>"""

    positives_html = ""
    if positives:
        items = "".join(f"<li style='margin:6px 0;'>{p}</li>" for p in positives)
        positives_html = f"""
        <div style="background:#F0FEF4;border-left:4px solid #27AE60;padding:16px 20px;margin:20px 0;border-radius:0 8px 8px 0;">
          <strong style="color:#27AE60;">✨ What's Done Well</strong>
          <ul style="margin:10px 0 0 0;padding-left:20px;">{items}</ul>
        </div>"""

    all_issues_rows = issues_rows(critical_issues) + issues_rows(high_issues) + issues_rows(other_issues)
    issues_table = ""
    if all_issues_rows:
        issues_table = f"""
        <h3 style="margin:24px 0 12px;color:#333;">Issues Found ({len(issues)} total)</h3>
        <table style="width:100%;border-collapse:collapse;background:#fff;border-radius:8px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,0.1);">
          <thead>
            <tr style="background:#F8F9FA;">
              <th style="padding:10px 12px;text-align:left;font-size:12px;color:#666;text-transform:uppercase;">Severity</th>
              <th style="padding:10px 12px;text-align:left;font-size:12px;color:#666;text-transform:uppercase;">File</th>
              <th style="padding:10px 12px;text-align:left;font-size:12px;color:#666;text-transform:uppercase;">Issue</th>
              <th style="padding:10px 12px;text-align:left;font-size:12px;color:#666;text-transform:uppercase;">Category</th>
            </tr>
          </thead>
          <tbody>{all_issues_rows}</tbody>
        </table>"""

    html_body = f"""
<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"></head>
<body style="margin:0;padding:0;background:#F4F6F8;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">

  <div style="max-width:760px;margin:32px auto;background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 2px 12px rgba(0,0,0,0.08);">

    <!-- Header -->
    <div style="background:#1A1A2E;padding:24px 32px;display:flex;align-items:center;justify-content:space-between;">
      <div>
        <div style="color:#8B9DC3;font-size:13px;letter-spacing:0.05em;text-transform:uppercase;">AI PR Review</div>
        <div style="color:#fff;font-size:20px;font-weight:600;margin-top:4px;">{repo}</div>
      </div>
      <div style="background:{badge_color};color:#fff;padding:8px 18px;border-radius:20px;font-weight:700;font-size:14px;">
        {badge_label}
      </div>
    </div>

    <!-- PR Info Bar -->
    <div style="background:#F8F9FA;padding:16px 32px;border-bottom:1px solid #eee;display:flex;gap:32px;">
      <div>
        <div style="font-size:11px;color:#999;text-transform:uppercase;letter-spacing:0.05em;">Pull Request</div>
        <div style="font-size:15px;font-weight:600;color:#333;margin-top:2px;">#{pr_number}: {pr_title}</div>
      </div>
      <div>
        <div style="font-size:11px;color:#999;text-transform:uppercase;letter-spacing:0.05em;">Author</div>
        <div style="font-size:15px;font-weight:500;color:#333;margin-top:2px;">@{author}</div>
      </div>
      <div>
        <div style="font-size:11px;color:#999;text-transform:uppercase;letter-spacing:0.05em;">Reviewed At</div>
        <div style="font-size:15px;font-weight:500;color:#333;margin-top:2px;">{datetime.now().strftime('%b %d, %Y %H:%M')}</div>
      </div>
    </div>

    <div style="padding:28px 32px;">

      <!-- Score -->
      <div style="display:flex;align-items:center;gap:16px;margin-bottom:24px;">
        <div style="font-size:48px;font-weight:700;color:{score_color};">{score}</div>
        <div>
          <div style="color:#999;font-size:13px;">out of 100</div>
          <div style="background:#eee;border-radius:4px;height:8px;width:200px;margin-top:6px;overflow:hidden;">
            <div style="background:{score_color};height:100%;width:{score}%;border-radius:4px;"></div>
          </div>
        </div>
      </div>

      <!-- Summary -->
      <div style="background:#F8F9FA;border-radius:8px;padding:16px 20px;margin-bottom:20px;color:#444;line-height:1.6;">
        {summary}
      </div>

      {'<div style="background:#FEF0F0;border:2px solid #C0392B;border-radius:8px;padding:16px 20px;margin-bottom:20px;"><strong style="color:#C0392B;font-size:15px;">🔐 SECURITY ALERT: Security vulnerabilities detected in this PR. Immediate review required.</strong></div>' if has_security else ''}

      {blockers_html}
      {issues_table}
      {positives_html}

      <!-- CTA -->
      <div style="text-align:center;margin-top:32px;">
        <a href="{github_pr_url}"
           style="display:inline-block;background:#1A1A2E;color:#fff;text-decoration:none;padding:14px 32px;border-radius:8px;font-weight:600;font-size:15px;">
          View PR on GitHub →
        </a>
      </div>

    </div>

    <!-- Footer -->
    <div style="background:#F8F9FA;padding:16px 32px;border-top:1px solid #eee;text-align:center;">
      <span style="color:#999;font-size:12px;">
        Sent by PR Review Agent • Powered by Claude AI •
        <a href="{github_pr_url}" style="color:#666;text-decoration:none;">View on GitHub</a>
      </span>
    </div>

  </div>
</body>
</html>"""

    return subject, html_body


def build_merge_email_html(repo: str, pr_number: int, pr_title: str, author: str,
                            strategy: str, github_pr_url: str) -> tuple[str, str]:
    subject = f"[PR Merged] ✅ #{pr_number} {pr_title} — Auto-merged via {strategy}"
    html_body = f"""
<!DOCTYPE html><html><body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#F4F6F8;margin:0;padding:32px;">
<div style="max-width:600px;margin:0 auto;background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 2px 12px rgba(0,0,0,0.08);">
  <div style="background:#27AE60;padding:24px 32px;">
    <div style="color:#fff;font-size:22px;font-weight:700;">✅ PR Auto-Merged</div>
    <div style="color:#D5F5E3;margin-top:4px;font-size:14px;">{repo} • {datetime.now().strftime('%b %d, %Y %H:%M')}</div>
  </div>
  <div style="padding:28px 32px;">
    <p style="color:#333;font-size:16px;margin:0 0 16px;">
      Pull request <strong>#{pr_number}: {pr_title}</strong> by <strong>@{author}</strong>
      was reviewed, approved, and automatically merged using the <strong>{strategy}</strong> strategy.
    </p>
    <div style="text-align:center;margin-top:24px;">
      <a href="{github_pr_url}" style="background:#1A1A2E;color:#fff;text-decoration:none;padding:12px 28px;border-radius:8px;font-weight:600;">
        View Merged PR →
      </a>
    </div>
  </div>
</div>
</body></html>"""
    return subject, html_body


# ── Main Notifier Class ───────────────────────────────────────────────────────

class OutlookNotifier:
    """
    Sends Outlook email notifications for PR review events.
    Plug this into pr_agent.py's pipeline.
    """

    def __init__(self, config: EmailConfig):
        self.config = config
        self.auth   = GraphAuthClient(config)

    def _send(self, to_emails: list[str], subject: str, html_body: str) -> bool:
        """Core send method — builds Graph API payload and sends."""
        if not to_emails:
            return True  # No recipients configured, silently skip
        if not self.config.enabled:
            print(f"  [EMAIL] Notifications disabled, would send to: {', '.join(to_emails)}")
            return True

        to_list = [{"emailAddress": {"address": addr}} for addr in to_emails]

        payload = {
            "message": {
                "subject": subject,
                "body": {
                    "contentType": "HTML",
                    "content": html_body,
                },
                "toRecipients": to_list,
                "from": {
                    "emailAddress": {"address": self.config.sender_email}
                },
            },
            "saveToSentItems": True,
        }

        success = self.auth.send_mail(self.config.sender_email, payload)
        if success:
            print(f"  ✓ Email sent to: {', '.join(to_emails)}")
        return success

    def notify_review_complete(
        self,
        repo: str,
        pr_number: int,
        pr_title: str,
        author: str,
        review: dict,
    ) -> dict:
        """
        Main entry point. Decides which emails to send based on review outcome.
        Call this after post_review_to_github() in the pipeline.
        """
        if not self.config.enabled:
            return {"sent": False, "reason": "notifications disabled"}

        verdict      = review.get("verdict", "")
        has_security = review.get("has_security_issues", False)
        issues       = review.get("issues", [])
        score        = review.get("overall_score", 100)
        sent_emails  = []

        github_pr_url = f"https://github.com/{repo}/pull/{pr_number}"

        # ── Notify on CRITICAL issues ──
        critical_issues = [i for i in issues if i.get("severity") == "critical"]
        if critical_issues and self.config.notify_on_critical:
            subject, html = build_review_email_html(
                repo, pr_number, pr_title, author, review, github_pr_url
            )
            if self._send(self.config.notify_on_critical, subject, html):
                sent_emails.append(("critical_alert", self.config.notify_on_critical))

        # ── Notify on HIGH issues (separate recipient list) ──
        high_issues = [i for i in issues if i.get("severity") == "high"]
        if high_issues and self.config.notify_on_high:
            # Avoid double-emailing people already in critical list
            extra_recipients = [
                e for e in self.config.notify_on_high
                if e not in self.config.notify_on_critical
            ]
            if extra_recipients:
                subject, html = build_review_email_html(
                    repo, pr_number, pr_title, author, review, github_pr_url
                )
                if self._send(extra_recipients, subject, html):
                    sent_emails.append(("high_alert", extra_recipients))

        # ── Notify on BLOCK ──
        if verdict in ("block", "request_changes") and self.config.notify_on_block:
            if not critical_issues:  # Don't double-email if already sent critical
                subject, html = build_review_email_html(
                    repo, pr_number, pr_title, author, review, github_pr_url
                )
                if self._send(self.config.notify_on_block, subject, html):
                    sent_emails.append(("block_alert", self.config.notify_on_block))

        # ── Notify on APPROVE ──
        if verdict == "approve" and self.config.notify_on_approve:
            subject, html = build_review_email_html(
                repo, pr_number, pr_title, author, review, github_pr_url
            )
            if self._send(self.config.notify_on_approve, subject, html):
                sent_emails.append(("approved", self.config.notify_on_approve))

        # ── Notify on LOW SCORE ──
        if score < self.config.send_on_score_below:
            all_already_notified = set(
                e for _, recipients in sent_emails for e in recipients
            )
            extra = [e for e in (self.config.notify_on_block or self.config.notify_on_critical)
                     if e not in all_already_notified]
            if extra:
                subject, html = build_review_email_html(
                    repo, pr_number, pr_title, author, review, github_pr_url
                )
                self._send(extra, subject, html)

        return {"sent": len(sent_emails) > 0, "emails_sent": sent_emails}

    def notify_merge(
        self,
        repo: str,
        pr_number: int,
        pr_title: str,
        author: str,
        strategy: str,
    ):
        """Send merge notification email."""
        if not self.config.notify_on_merge:
            return
        github_pr_url = f"https://github.com/{repo}/pull/{pr_number}"
        subject, html = build_merge_email_html(
            repo, pr_number, pr_title, author, strategy, github_pr_url
        )
        self._send(self.config.notify_on_merge, subject, html)

    def send_daily_digest(self, reviews: list[dict]):
        """Send a daily summary of all PRs reviewed."""
        if not self.config.daily_digest_to or not reviews:
            return

        date_str = datetime.now().strftime("%B %d, %Y")
        rows = ""
        for r in reviews:
            verdict = r.get("verdict", "")
            color, label = _verdict_badge(verdict)
            rows += f"""
            <tr>
              <td style="padding:10px 12px;border-bottom:1px solid #eee;">
                <a href="https://github.com/{r.get('repo')}/pull/{r.get('pr_number')}"
                   style="color:#1A1A2E;font-weight:500;">#{r.get('pr_number')}: {r.get('title','')}</a>
              </td>
              <td style="padding:10px 12px;border-bottom:1px solid #eee;color:#666;">{r.get('repo','')}</td>
              <td style="padding:10px 12px;border-bottom:1px solid #eee;">
                <span style="background:{color};color:#fff;padding:3px 10px;border-radius:12px;font-size:12px;">{label}</span>
              </td>
              <td style="padding:10px 12px;border-bottom:1px solid #eee;color:#333;font-weight:600;">{r.get('score',0)}/100</td>
            </tr>"""

        html = f"""
<!DOCTYPE html><html><body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#F4F6F8;margin:0;padding:32px;">
<div style="max-width:760px;margin:0 auto;background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 2px 12px rgba(0,0,0,0.08);">
  <div style="background:#1A1A2E;padding:24px 32px;">
    <div style="color:#fff;font-size:20px;font-weight:700;">📋 Daily PR Review Digest</div>
    <div style="color:#8B9DC3;margin-top:4px;">{date_str} • {len(reviews)} PRs reviewed</div>
  </div>
  <div style="padding:28px 32px;">
    <table style="width:100%;border-collapse:collapse;">
      <thead>
        <tr style="background:#F8F9FA;">
          <th style="padding:10px 12px;text-align:left;font-size:12px;color:#666;text-transform:uppercase;">PR</th>
          <th style="padding:10px 12px;text-align:left;font-size:12px;color:#666;text-transform:uppercase;">Repo</th>
          <th style="padding:10px 12px;text-align:left;font-size:12px;color:#666;text-transform:uppercase;">Verdict</th>
          <th style="padding:10px 12px;text-align:left;font-size:12px;color:#666;text-transform:uppercase;">Score</th>
        </tr>
      </thead>
      <tbody>{rows}</tbody>
    </table>
  </div>
  <div style="background:#F8F9FA;padding:16px 32px;border-top:1px solid #eee;text-align:center;">
    <span style="color:#999;font-size:12px;">PR Review Agent • Daily Digest • {date_str}</span>
  </div>
</div>
</body></html>"""

        self._send(
            self.config.daily_digest_to,
            f"[PR Digest] {len(reviews)} PRs Reviewed — {date_str}",
            html
        )
