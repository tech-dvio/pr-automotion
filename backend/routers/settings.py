import bcrypt
import os
import smtplib
import ssl
from typing import Optional
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import GlobalSetting, get_db
from encryption import encrypt, decrypt
from .auth import require_admin

router = APIRouter()

SENSITIVE_KEYS = {"smtp_password", "anthropic_api_key"}

SETTING_KEYS = {
    "webhook_base_url",
    "anthropic_api_key",
    "smtp_host",
    "smtp_port",
    "smtp_username",
    "smtp_password",
    "smtp_sender_email",
}


class SettingsUpdate(BaseModel):
    webhook_base_url: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    smtp_host: Optional[str] = None
    smtp_port: Optional[str] = None
    smtp_username: Optional[str] = None
    smtp_password: Optional[str] = None
    smtp_sender_email: Optional[str] = None


def _upsert(db: Session, key: str, value: str):
    row = db.query(GlobalSetting).filter_by(key=key).first()
    encrypted = encrypt(value)
    if row:
        row.value_enc = encrypted
    else:
        db.add(GlobalSetting(key=key, value_enc=encrypted))


def _read(db: Session, key: str) -> str:
    row = db.query(GlobalSetting).filter_by(key=key).first()
    if row and row.value_enc:
        return decrypt(row.value_enc)
    return ""


@router.get("")
def get_settings(db: Session = Depends(get_db), _=Depends(require_admin)):
    result = {}
    for key in SETTING_KEYS:
        val = _read(db, key)
        result[key] = "••••••••" if (val and key in SENSITIVE_KEYS) else val
    return result


@router.put("")
def update_settings(body: SettingsUpdate, db: Session = Depends(get_db), _=Depends(require_admin)):
    for key, value in body.model_dump(exclude_none=True).items():
        if key in SETTING_KEYS and value:
            _upsert(db, key, value)
    db.commit()
    return {"ok": True}


class TestEmailRequest(BaseModel):
    to: str


@router.post("/test-email")
def test_email(body: TestEmailRequest, db: Session = Depends(get_db), _=Depends(require_admin)):
    host = _read(db, "smtp_host")
    port_raw = _read(db, "smtp_port")
    username = _read(db, "smtp_username")
    password = _read(db, "smtp_password")
    sender = _read(db, "smtp_sender_email") or username

    if not host or not username:
        return {"ok": False, "error": "SMTP not configured — set smtp_host and smtp_username in Settings"}

    port = int(port_raw) if port_raw.isdigit() else 587

    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    msg = MIMEMultipart("alternative")
    msg["Subject"] = "✅ PR Review Agent — SMTP Test"
    msg["From"] = sender
    msg["To"] = body.to
    html = """
    <div style="font-family:sans-serif;max-width:480px;margin:40px auto;padding:24px;border:1px solid #E2E8F0;border-radius:12px">
      <h2 style="color:#6366F1">PR Review Agent</h2>
      <p>Your SMTP configuration is working correctly. 🎉</p>
      <p style="color:#64748B;font-size:13px">Email notifications will be sent to this address when PRs are reviewed.</p>
    </div>"""
    msg.attach(MIMEText(html, "html", "utf-8"))

    try:
        ctx = ssl.create_default_context()
        if port == 465:
            with smtplib.SMTP_SSL(host, 465, context=ctx, timeout=15) as server:
                server.login(username, password)
                server.sendmail(sender, [body.to], msg.as_string())
        else:
            with smtplib.SMTP(host, port, timeout=15) as server:
                server.ehlo()
                server.starttls(context=ctx)
                server.ehlo()
                server.login(username, password)
                server.sendmail(sender, [body.to], msg.as_string())
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def initialize_admin_token(db: Session):
    token = os.environ.get("ADMIN_TOKEN", "")
    if not token:
        return
    existing = db.query(GlobalSetting).filter_by(key="admin_token_hash").first()
    if not existing:
        hashed = bcrypt.hashpw(token.encode(), bcrypt.gensalt()).decode()
        db.add(GlobalSetting(key="admin_token_hash", value_enc=hashed))
        db.commit()
