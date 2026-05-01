"""
SMTP Email Notifier — PR Review Agent
======================================
Sends rich HTML emails via any SMTP server (Office 365, Gmail, etc.).
Drop-in replacement for outlook_notifier.py — same interface, no Azure needed.

SMTP settings to configure (via dashboard Settings page):
  smtp_host     — e.g. smtp.office365.com  or  smtp.gmail.com
  smtp_port     — 587 (STARTTLS, recommended)  or  465 (SSL)
  smtp_username — your email / service account login
  smtp_password — your email password or app password
  sender_email  — the From address (usually same as smtp_username)
"""

import smtplib
import ssl
from dataclasses import dataclass, field
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


@dataclass
class EmailConfig:
    enabled: bool = True

    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    sender_email: str = ""

    notify_on_critical: list = field(default_factory=list)
    notify_on_high: list = field(default_factory=list)
    notify_on_merge: list = field(default_factory=list)
    notify_on_block: list = field(default_factory=list)
    notify_on_approve: list = field(default_factory=list)
    daily_digest_to: list = field(default_factory=list)
    send_on_score_below: int = 60


def _build_review_html(
    repo: str, pr_number: int, pr_title: str, author: str,
    review: dict, pr_url: str
) -> tuple[str, str]:
    verdict = review.get("verdict", "")
    score = review.get("overall_score", review.get("score", 0))
    issues = review.get("issues", [])
    blockers = [i for i in issues if i.get("severity") in ("critical", "high")]

    VERDICT_COLOR = {
        "approve": "#10B981",
        "request_changes": "#F59E0B",
        "block": "#EF4444",
    }
    SEVERITY_COLOR = {
        "critical": "#EF4444",
        "high": "#F97316",
        "medium": "#F59E0B",
        "low": "#3B82F6",
    }

    verdict_color = VERDICT_COLOR.get(verdict, "#6B7280")
    verdict_label = verdict.replace("_", " ").title()

    score_bar_color = "#10B981" if score >= 80 else "#F59E0B" if score >= 60 else "#EF4444"

    issues_rows = "".join(
        f"""<tr>
          <td style="padding:8px;border-bottom:1px solid #F1F5F9;color:{SEVERITY_COLOR.get(i.get('severity',''), '#6B7280')};font-weight:600;font-size:12px;text-transform:uppercase">{i.get('severity','')}</td>
          <td style="padding:8px;border-bottom:1px solid #F1F5F9;font-size:13px;color:#374151">{i.get('message','')}</td>
          <td style="padding:8px;border-bottom:1px solid #F1F5F9;font-size:12px;color:#6B7280">{i.get('file','')}</td>
        </tr>"""
        for i in issues[:15]
    )

    blocker_html = ""
    if blockers:
        blocker_items = "".join(f"<li style='margin:6px 0;color:#374151;font-size:13px'>🔴 {b.get('message','')}</li>" for b in blockers)
        blocker_html = f"""
        <div style="background:#FEF2F2;border:1px solid #FECACA;border-radius:8px;padding:16px;margin:16px 0">
          <p style="margin:0 0 8px;font-weight:600;color:#DC2626">Blockers</p>
          <ul style="margin:0;padding-left:20px">{blocker_items}</ul>
        </div>"""

    subject = f"[PR Review] {'🚨' if verdict == 'block' else '✅' if verdict == 'approve' else '⚠️'} {repo} #{pr_number} — {verdict_label}"

    html = f"""
<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"></head>
<body style="font-family:Inter,system-ui,sans-serif;background:#F8FAFC;margin:0;padding:24px">
  <div style="max-width:620px;margin:0 auto;background:#fff;border-radius:12px;border:1px solid #E2E8F0;overflow:hidden">

    <!-- Header -->
    <div style="background:#0F172A;padding:24px 28px">
      <p style="margin:0;color:#94A3B8;font-size:12px;text-transform:uppercase;letter-spacing:.05em">PR Review Agent</p>
      <h1 style="margin:8px 0 0;color:#fff;font-size:20px">{repo} <span style="color:#6366F1">#{pr_number}</span></h1>
      <p style="margin:6px 0 0;color:#CBD5E1;font-size:14px">{pr_title}</p>
    </div>

    <!-- Verdict + Score -->
    <div style="padding:20px 28px;border-bottom:1px solid #F1F5F9;display:flex;align-items:center;gap:16px">
      <span style="background:{verdict_color}20;color:{verdict_color};border:1px solid {verdict_color}40;border-radius:20px;padding:4px 14px;font-size:13px;font-weight:600">{verdict_label}</span>
      <div style="flex:1">
        <p style="margin:0 0 4px;font-size:12px;color:#94A3B8">Quality Score</p>
        <div style="background:#F1F5F9;border-radius:4px;height:8px;overflow:hidden">
          <div style="background:{score_bar_color};width:{score}%;height:100%"></div>
        </div>
      </div>
      <span style="font-size:22px;font-weight:700;color:{score_bar_color}">{score}<span style="font-size:14px;color:#94A3B8">/100</span></span>
    </div>

    <!-- Meta -->
    <div style="padding:16px 28px;border-bottom:1px solid #F1F5F9;display:flex;gap:24px">
      <div><p style="margin:0;font-size:11px;color:#94A3B8;text-transform:uppercase">Author</p><p style="margin:4px 0 0;font-size:13px;color:#374151;font-weight:500">@{author}</p></div>
      <div><p style="margin:0;font-size:11px;color:#94A3B8;text-transform:uppercase">Issues Found</p><p style="margin:4px 0 0;font-size:13px;color:#374151;font-weight:500">{len(issues)}</p></div>
      <div><p style="margin:0;font-size:11px;color:#94A3B8;text-transform:uppercase">Blockers</p><p style="margin:4px 0 0;font-size:13px;color:#EF4444;font-weight:600">{len(blockers)}</p></div>
    </div>

    <!-- Body -->
    <div style="padding:20px 28px">
      {blocker_html}

      {'<table style="width:100%;border-collapse:collapse;margin-top:16px"><thead><tr><th style="text-align:left;padding:8px;font-size:11px;color:#94A3B8;text-transform:uppercase;border-bottom:2px solid #F1F5F9">Severity</th><th style="text-align:left;padding:8px;font-size:11px;color:#94A3B8;text-transform:uppercase;border-bottom:2px solid #F1F5F9">Issue</th><th style="text-align:left;padding:8px;font-size:11px;color:#94A3B8;text-transform:uppercase;border-bottom:2px solid #F1F5F9">File</th></tr></thead><tbody>' + issues_rows + '</tbody></table>' if issues else '<p style="color:#94A3B8;font-size:14px;text-align:center;padding:16px 0">No issues found 🎉</p>'}

      <!-- CTA -->
      <div style="text-align:center;margin-top:24px">
        <a href="{pr_url}" style="background:#6366F1;color:#fff;text-decoration:none;padding:10px 24px;border-radius:8px;font-size:14px;font-weight:600">View Pull Request →</a>
      </div>
    </div>

    <!-- Footer -->
    <div style="background:#F8FAFC;padding:16px 28px;border-top:1px solid #F1F5F9;text-align:center">
      <p style="margin:0;font-size:11px;color:#94A3B8">Sent by PR Review Agent • <a href="{pr_url}" style="color:#6366F1">{repo}#{pr_number}</a></p>
    </div>
  </div>
</body>
</html>"""

    return subject, html


def _build_merge_html(repo: str, pr_number: int, pr_title: str, author: str, strategy: str) -> tuple[str, str]:
    subject = f"[PR Merged] ✅ {repo} #{pr_number} — {pr_title}"
    html = f"""
<!DOCTYPE html><html><body style="font-family:Inter,system-ui,sans-serif;background:#F8FAFC;margin:0;padding:24px">
  <div style="max-width:560px;margin:0 auto;background:#fff;border-radius:12px;border:1px solid #E2E8F0;overflow:hidden">
    <div style="background:#0F172A;padding:20px 24px">
      <p style="margin:0;color:#94A3B8;font-size:12px">PR Review Agent</p>
      <h1 style="margin:8px 0 0;color:#fff;font-size:18px">Pull Request Merged ✅</h1>
    </div>
    <div style="padding:24px">
      <p style="margin:0;font-size:15px;color:#374151"><strong>{repo} #{pr_number}</strong> was automatically merged.</p>
      <div style="background:#F0FDF4;border:1px solid #BBF7D0;border-radius:8px;padding:16px;margin:16px 0">
        <p style="margin:0;font-size:13px;color:#166534"><strong>Title:</strong> {pr_title}</p>
        <p style="margin:6px 0 0;font-size:13px;color:#166534"><strong>Author:</strong> @{author}</p>
        <p style="margin:6px 0 0;font-size:13px;color:#166534"><strong>Strategy:</strong> {strategy}</p>
      </div>
      <div style="text-align:center;margin-top:20px">
        <a href="https://github.com/{repo}/pull/{pr_number}" style="background:#10B981;color:#fff;text-decoration:none;padding:10px 24px;border-radius:8px;font-size:14px;font-weight:600">View on GitHub →</a>
      </div>
    </div>
  </div>
</body></html>"""
    return subject, html


class SmtpNotifier:
    def __init__(self, config: EmailConfig):
        self.config = config

    def _send(self, to_emails: list[str], subject: str, html: str) -> bool:
        if not to_emails or not self.config.enabled:
            return False
        if not self.config.smtp_host or not self.config.smtp_username:
            print("[smtp] SMTP not configured — skipping email")
            return False
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = self.config.sender_email or self.config.smtp_username
            msg["To"] = ", ".join(to_emails)
            msg.attach(MIMEText(html, "html", "utf-8"))

            if self.config.smtp_port == 465:
                ctx = ssl.create_default_context()
                with smtplib.SMTP_SSL(self.config.smtp_host, 465, context=ctx) as server:
                    server.login(self.config.smtp_username, self.config.smtp_password)
                    server.sendmail(msg["From"], to_emails, msg.as_string())
            else:
                with smtplib.SMTP(self.config.smtp_host, self.config.smtp_port) as server:
                    server.ehlo()
                    server.starttls()
                    server.login(self.config.smtp_username, self.config.smtp_password)
                    server.sendmail(msg["From"], to_emails, msg.as_string())

            print(f"[smtp] ✓ Email sent to: {', '.join(to_emails)}")
            return True
        except Exception as e:
            print(f"[smtp] ✗ Failed to send email: {e}")
            return False

    def _all_recipients(self) -> list[str]:
        """Return every configured email address deduplicated."""
        seen: set[str] = set()
        result = []
        for lst in [
            self.config.notify_on_critical,
            self.config.notify_on_high,
            self.config.notify_on_block,
            self.config.notify_on_approve,
            self.config.notify_on_merge,
            self.config.daily_digest_to,
        ]:
            for email in lst:
                if email not in seen:
                    seen.add(email)
                    result.append(email)
        return result

    def notify_review_complete(
        self,
        repo: str,
        pr_number: int,
        pr_title: str,
        author: str,
        review: dict,
    ) -> dict:
        if not self.config.enabled:
            return {"sent": False, "reason": "notifications disabled"}

        verdict = review.get("verdict", "")
        issues = review.get("issues", [])
        score = review.get("overall_score", review.get("score", 100))
        sent_emails = []
        already_sent: set[str] = set()

        pr_url = f"https://github.com/{repo}/pull/{pr_number}"

        def _send_once(label: str, to: list[str]):
            extra = [e for e in to if e not in already_sent]
            if not extra:
                return
            subject, html = _build_review_html(repo, pr_number, pr_title, author, review, pr_url)
            if self._send(extra, subject, html):
                sent_emails.append((label, extra))
                already_sent.update(extra)

        critical_issues = [i for i in issues if i.get("severity") == "critical"]
        high_issues = [i for i in issues if i.get("severity") == "high"]

        # Critical issues → notify critical-role recipients + ALL recipients as fallback
        if critical_issues:
            targets = self.config.notify_on_critical or self._all_recipients()
            _send_once("critical_alert", targets)

        # High-severity issues → notify high-role recipients
        if high_issues:
            _send_once("high_alert", self.config.notify_on_high)

        # Block / request_changes → notify block-role recipients (or ALL as fallback)
        if verdict in ("block", "request_changes"):
            targets = self.config.notify_on_block or self._all_recipients()
            _send_once("block_alert", targets)

        # Approve → notify approve-role recipients
        if verdict == "approve":
            targets = self.config.notify_on_approve or self.config.notify_on_merge
            if targets:
                _send_once("approved", targets)

        # Low score fallback — catch anything that slipped through
        if score < self.config.send_on_score_below and not already_sent:
            _send_once("low_score", self._all_recipients())

        return {"sent": len(sent_emails) > 0, "emails_sent": sent_emails}

    def notify_merge(self, repo: str, pr_number: int, pr_title: str, author: str, strategy: str):
        if not self.config.notify_on_merge:
            return
        subject, html = _build_merge_html(repo, pr_number, pr_title, author, strategy)
        self._send(self.config.notify_on_merge, subject, html)
