import json
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from database import Repo, EmailRecipient, GlobalSetting
from encryption import decrypt
from pr_agent import ReviewConfig
from smtp_notifier import EmailConfig, SmtpNotifier


def _get_global(db, key: str) -> str:
    row = db.query(GlobalSetting).filter_by(key=key).first()
    if row and row.value_enc:
        return decrypt(row.value_enc)
    return ""


def build_review_config(row: Repo) -> ReviewConfig:
    return ReviewConfig(
        repo=row.repo_full_name,
        auto_merge=row.auto_merge,
        auto_merge_strategy=row.auto_merge_strategy,
        block_on_severity=json.loads(row.block_on_severity or '["critical","high"]'),
        require_tests=row.require_tests,
        max_file_changes=row.max_file_changes,
        protected_files=json.loads(row.protected_files or "[]"),
        custom_rules=json.loads(row.custom_rules or "[]"),
    )


def build_email_config(row: Repo, db) -> EmailConfig:
    recipients = db.query(EmailRecipient).filter_by(repo_id=row.id).all()

    def by_role(role: str):
        return [r.email for r in recipients if r.role == role]

    smtp_port_raw = _get_global(db, "smtp_port")
    smtp_port = int(smtp_port_raw) if smtp_port_raw.isdigit() else 587

    return EmailConfig(
        enabled=True,
        smtp_host=_get_global(db, "smtp_host"),
        smtp_port=smtp_port,
        smtp_username=_get_global(db, "smtp_username"),
        smtp_password=_get_global(db, "smtp_password"),
        sender_email=_get_global(db, "smtp_sender_email"),
        notify_on_critical=by_role("critical"),
        notify_on_high=by_role("high"),
        notify_on_block=by_role("block"),
        notify_on_merge=by_role("merge"),
        notify_on_approve=by_role("approve"),
        daily_digest_to=by_role("digest"),
    )


def build_notifier(row: Repo, db) -> SmtpNotifier:
    return SmtpNotifier(build_email_config(row, db))
