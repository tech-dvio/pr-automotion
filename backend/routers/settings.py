import bcrypt
import os
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


def initialize_admin_token(db: Session):
    token = os.environ.get("ADMIN_TOKEN", "")
    if not token:
        return
    existing = db.query(GlobalSetting).filter_by(key="admin_token_hash").first()
    if not existing:
        hashed = bcrypt.hashpw(token.encode(), bcrypt.gensalt()).decode()
        db.add(GlobalSetting(key="admin_token_hash", value_enc=hashed))
        db.commit()
