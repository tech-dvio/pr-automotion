import bcrypt
from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional

from database import GlobalSetting, get_db

router = APIRouter()


def require_admin(
    x_admin_token: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    if not x_admin_token:
        raise HTTPException(status_code=401, detail="Missing X-Admin-Token header")
    row = db.query(GlobalSetting).filter_by(key="admin_token_hash").first()
    if not row or not row.value_enc:
        raise HTTPException(status_code=503, detail="Admin token not configured on server")
    try:
        valid = bcrypt.checkpw(x_admin_token.encode(), row.value_enc.encode())
    except Exception:
        valid = False
    if not valid:
        raise HTTPException(status_code=401, detail="Invalid admin token")


class VerifyRequest(BaseModel):
    token: str


@router.post("/verify")
def verify(body: VerifyRequest, db: Session = Depends(get_db)):
    row = db.query(GlobalSetting).filter_by(key="admin_token_hash").first()
    if not row or not row.value_enc:
        raise HTTPException(status_code=503, detail="Admin token not configured on server")
    try:
        valid = bcrypt.checkpw(body.token.encode(), row.value_enc.encode())
    except Exception:
        valid = False
    if not valid:
        raise HTTPException(status_code=401, detail="Invalid token")
    return {"ok": True}
