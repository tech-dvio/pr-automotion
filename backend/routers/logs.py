from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from database import ReviewLog, get_db
from models.log import LogDetail, LogListResponse, LogSummary
from .auth import require_admin

router = APIRouter()


@router.get("", response_model=LogListResponse)
def list_logs(
    repo_id: Optional[int] = Query(None),
    verdict: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    q = db.query(ReviewLog)
    if repo_id is not None:
        q = q.filter(ReviewLog.repo_id == repo_id)
    if verdict:
        q = q.filter(ReviewLog.verdict == verdict)
    total = q.count()
    items = q.order_by(ReviewLog.reviewed_at.desc()).offset((page - 1) * per_page).limit(per_page).all()

    return LogListResponse(
        total=total,
        page=page,
        per_page=per_page,
        items=[LogSummary.model_validate(i, from_attributes=True) for i in items],
    )


@router.get("/{log_id}", response_model=LogDetail)
def get_log(log_id: int, db: Session = Depends(get_db), _=Depends(require_admin)):
    log = db.query(ReviewLog).filter_by(id=log_id).first()
    if not log:
        raise HTTPException(status_code=404, detail="Log not found")
    return LogDetail.model_validate(log, from_attributes=True)
