import json
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import Repo, EmailRecipient, ReviewLog, GlobalSetting, get_db
from encryption import encrypt, decrypt, generate_webhook_secret
from github_api import github_manager
from models.repo import (
    RepoCreate, RepoUpdate, RepoSummary, RepoDetail,
    EmailRecipientOut, TestConnectionRequest, TestConnectionResponse, RevealRequest,
)
from .auth import require_admin

router = APIRouter()


def _get_global(db: Session, key: str) -> str:
    row = db.query(GlobalSetting).filter_by(key=key).first()
    return decrypt(row.value_enc) if row and row.value_enc else ""


def _enrich_summary(row: Repo, db: Session) -> RepoSummary:
    count = db.query(func.count(EmailRecipient.id)).filter_by(repo_id=row.id).scalar()
    last_log = (
        db.query(ReviewLog)
        .filter_by(repo_id=row.id)
        .order_by(ReviewLog.reviewed_at.desc())
        .first()
    )
    return RepoSummary(
        id=row.id,
        repo_full_name=row.repo_full_name,
        display_name=row.display_name,
        webhook_active=row.webhook_active,
        github_hook_id=row.github_hook_id,
        auto_merge=row.auto_merge,
        created_at=row.created_at,
        updated_at=row.updated_at,
        recipient_count=count,
        last_verdict=last_log.verdict if last_log else None,
        last_score=last_log.score if last_log else None,
        last_reviewed_at=last_log.reviewed_at if last_log else None,
    )


@router.get("", response_model=List[RepoSummary])
def list_repos(db: Session = Depends(get_db), _=Depends(require_admin)):
    rows = db.query(Repo).order_by(Repo.created_at.desc()).all()
    return [_enrich_summary(r, db) for r in rows]


@router.post("", response_model=RepoDetail, status_code=201)
def create_repo(body: RepoCreate, db: Session = Depends(get_db), _=Depends(require_admin)):
    if db.query(Repo).filter_by(repo_full_name=body.repo_full_name).first():
        raise HTTPException(status_code=409, detail="Repo already registered")

    # Validate token against GitHub
    github_manager.verify_token(body.github_token)

    webhook_secret = body.webhook_secret or generate_webhook_secret()
    payload_url = _get_global(db, "webhook_base_url").rstrip("/") + "/webhook"
    if not payload_url.startswith("http"):
        raise HTTPException(
            status_code=400,
            detail="webhook_base_url not configured in Settings — set it first",
        )

    owner, repo_name = body.repo_full_name.split("/", 1)
    hook_id = github_manager.register_webhook(
        owner=owner,
        repo=repo_name,
        token=body.github_token,
        secret=webhook_secret,
        payload_url=payload_url,
    )

    now = datetime.utcnow()
    row = Repo(
        repo_full_name=body.repo_full_name,
        display_name=body.display_name,
        github_token_enc=encrypt(body.github_token),
        webhook_secret_enc=encrypt(webhook_secret),
        github_hook_id=hook_id,
        webhook_active=True,
        auto_merge=body.auto_merge,
        auto_merge_strategy=body.auto_merge_strategy,
        require_tests=body.require_tests,
        block_on_severity=json.dumps(body.block_on_severity),
        protected_files=json.dumps(body.protected_files),
        custom_rules=json.dumps(body.custom_rules),
        max_file_changes=body.max_file_changes,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.flush()  # get row.id

    for rec in body.email_recipients:
        db.add(EmailRecipient(repo_id=row.id, email=rec.email, role=rec.role))

    db.commit()
    db.refresh(row)
    return _build_detail(row, db)


@router.get("/{repo_id}", response_model=RepoDetail)
def get_repo(repo_id: int, db: Session = Depends(get_db), _=Depends(require_admin)):
    row = db.query(Repo).filter_by(id=repo_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Repo not found")
    return _build_detail(row, db)


@router.put("/{repo_id}", response_model=RepoDetail)
def update_repo(repo_id: int, body: RepoUpdate, db: Session = Depends(get_db), _=Depends(require_admin)):
    row = db.query(Repo).filter_by(id=repo_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Repo not found")

    token_changed = body.github_token is not None
    if token_changed:
        github_manager.verify_token(body.github_token)
        row.github_token_enc = encrypt(body.github_token)

    if body.webhook_secret is not None:
        row.webhook_secret_enc = encrypt(body.webhook_secret)
    if body.display_name is not None:
        row.display_name = body.display_name
    if body.auto_merge is not None:
        row.auto_merge = body.auto_merge
    if body.auto_merge_strategy is not None:
        row.auto_merge_strategy = body.auto_merge_strategy
    if body.require_tests is not None:
        row.require_tests = body.require_tests
    if body.block_on_severity is not None:
        row.block_on_severity = json.dumps(body.block_on_severity)
    if body.protected_files is not None:
        row.protected_files = json.dumps(body.protected_files)
    if body.custom_rules is not None:
        row.custom_rules = json.dumps(body.custom_rules)
    if body.max_file_changes is not None:
        row.max_file_changes = body.max_file_changes
    if body.email_recipients is not None:
        db.query(EmailRecipient).filter_by(repo_id=row.id).delete()
        for rec in body.email_recipients:
            db.add(EmailRecipient(repo_id=row.id, email=rec.email, role=rec.role))

    row.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(row)
    return _build_detail(row, db)


@router.delete("/{repo_id}", status_code=204)
def delete_repo(repo_id: int, db: Session = Depends(get_db), _=Depends(require_admin)):
    row = db.query(Repo).filter_by(id=repo_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Repo not found")

    if row.github_hook_id:
        owner, repo_name = row.repo_full_name.split("/", 1)
        token = decrypt(row.github_token_enc)
        github_manager.delete_webhook(owner, repo_name, token, row.github_hook_id)

    db.query(EmailRecipient).filter_by(repo_id=repo_id).delete()
    db.delete(row)
    db.commit()


@router.post("/{repo_id}/test-connection", response_model=TestConnectionResponse)
def test_connection(repo_id: int, db: Session = Depends(get_db), _=Depends(require_admin)):
    row = db.query(Repo).filter_by(id=repo_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Repo not found")
    token = decrypt(row.github_token_enc)
    try:
        info = github_manager.verify_token(token)
        return TestConnectionResponse(valid=True, login=info.get("login"))
    except HTTPException as e:
        return TestConnectionResponse(valid=False, error=e.detail)


@router.post("/test-token", response_model=TestConnectionResponse)
def test_token(body: TestConnectionRequest, _=Depends(require_admin)):
    try:
        info = github_manager.verify_token(body.github_token)
        return TestConnectionResponse(valid=True, login=info.get("login"))
    except HTTPException as e:
        return TestConnectionResponse(valid=False, error=e.detail)


@router.post("/{repo_id}/test-webhook")
def test_webhook(repo_id: int, db: Session = Depends(get_db), _=Depends(require_admin)):
    row = db.query(Repo).filter_by(id=repo_id).first()
    if not row or not row.github_hook_id:
        raise HTTPException(status_code=404, detail="Repo or webhook not found")
    owner, repo_name = row.repo_full_name.split("/", 1)
    token = decrypt(row.github_token_enc)
    ok = github_manager.ping_webhook(owner, repo_name, token, row.github_hook_id)
    return {"ok": ok}


@router.post("/{repo_id}/reveal")
def reveal_field(
    repo_id: int,
    body: RevealRequest,
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    allowed = {"github_token", "webhook_secret"}
    if body.field not in allowed:
        raise HTTPException(status_code=400, detail=f"field must be one of {allowed}")
    row = db.query(Repo).filter_by(id=repo_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Repo not found")
    if body.field == "github_token":
        return {"value": decrypt(row.github_token_enc)}
    return {"value": decrypt(row.webhook_secret_enc)}


def _build_detail(row: Repo, db: Session) -> RepoDetail:
    recipients = db.query(EmailRecipient).filter_by(repo_id=row.id).all()
    last_log = (
        db.query(ReviewLog)
        .filter_by(repo_id=row.id)
        .order_by(ReviewLog.reviewed_at.desc())
        .first()
    )
    count = len(recipients)
    return RepoDetail(
        id=row.id,
        repo_full_name=row.repo_full_name,
        display_name=row.display_name,
        webhook_active=row.webhook_active,
        github_hook_id=row.github_hook_id,
        auto_merge=row.auto_merge,
        auto_merge_strategy=row.auto_merge_strategy,
        require_tests=row.require_tests,
        block_on_severity=json.loads(row.block_on_severity or '["critical","high"]'),
        protected_files=json.loads(row.protected_files or "[]"),
        custom_rules=json.loads(row.custom_rules or "[]"),
        max_file_changes=row.max_file_changes,
        created_at=row.created_at,
        updated_at=row.updated_at,
        recipient_count=count,
        last_verdict=last_log.verdict if last_log else None,
        last_score=last_log.score if last_log else None,
        last_reviewed_at=last_log.reviewed_at if last_log else None,
        email_recipients=[
            EmailRecipientOut(id=r.id, email=r.email, role=r.role) for r in recipients
        ],
    )
