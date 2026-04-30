import bcrypt
import os
from typing import Dict, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import GlobalSetting, get_db
from encryption import encrypt, decrypt
from .auth import require_admin

router = APIRouter()

SENSITIVE_KEYS = {
    "azure_tenant_id", "azure_client_id", "azure_client_secret",
    "outlook_sender_email", "anthropic_api_key",
}

SETTING_KEYS = {
    "azure_tenant_id", "azure_client_id", "azure_client_secret",
    "outlook_sender_email", "anthropic_api_key", "webhook_base_url",
}


class SettingsUpdate(BaseModel):
    azure_tenant_id: Optional[str] = None
    azure_client_id: Optional[str] = None
    azure_client_secret: Optional[str] = None
    outlook_sender_email: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    webhook_base_url: Optional[str] = None


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
        if val and key in SENSITIVE_KEYS:
            result[key] = "••••••••"
        else:
            result[key] = val
    return result


@router.put("")
def update_settings(body: SettingsUpdate, db: Session = Depends(get_db), _=Depends(require_admin)):
    data = body.model_dump(exclude_none=True)
    for key, value in data.items():
        if key in SETTING_KEYS and value is not None:
            _upsert(db, key, value)
    db.commit()
    return {"ok": True}


def initialize_admin_token(db: Session):
    """Hash and store the ADMIN_TOKEN env var at startup if not already stored."""
    token = os.environ.get("ADMIN_TOKEN", "")
    if not token:
        return
    existing = db.query(GlobalSetting).filter_by(key="admin_token_hash").first()
    if not existing:
        hashed = bcrypt.hashpw(token.encode(), bcrypt.gensalt()).decode()
        db.add(GlobalSetting(key="admin_token_hash", value_enc=hashed))
        db.commit()
