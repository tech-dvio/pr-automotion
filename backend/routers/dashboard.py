from datetime import datetime, timedelta
from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import Repo, ReviewLog, get_db
from .auth import require_admin

router = APIRouter()


@router.get("/stats")
def get_stats(db: Session = Depends(get_db), _=Depends(require_admin)):
    today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    week_ago = today - timedelta(days=7)

    repos_total = db.query(func.count(Repo.id)).scalar()
    repos_active = db.query(func.count(Repo.id)).filter(Repo.webhook_active == True).scalar()

    prs_today = db.query(func.count(ReviewLog.id)).filter(ReviewLog.reviewed_at >= today).scalar()
    prs_week = db.query(func.count(ReviewLog.id)).filter(ReviewLog.reviewed_at >= week_ago).scalar()

    approvals_today = (
        db.query(func.count(ReviewLog.id))
        .filter(ReviewLog.reviewed_at >= today, ReviewLog.verdict == "approve")
        .scalar()
    )
    blocks_today = (
        db.query(func.count(ReviewLog.id))
        .filter(ReviewLog.reviewed_at >= today, ReviewLog.verdict.in_(["block", "request_changes"]))
        .scalar()
    )
    critical_today = (
        db.query(func.sum(ReviewLog.critical_count))
        .filter(ReviewLog.reviewed_at >= today)
        .scalar() or 0
    )
    avg_score = (
        db.query(func.avg(ReviewLog.score))
        .filter(ReviewLog.reviewed_at >= today, ReviewLog.score.isnot(None))
        .scalar()
    )

    return {
        "repos_total": repos_total,
        "repos_active": repos_active,
        "prs_reviewed_today": prs_today,
        "prs_reviewed_this_week": prs_week,
        "approvals_today": approvals_today,
        "blocks_today": blocks_today,
        "critical_issues_today": int(critical_today),
        "avg_score_today": round(avg_score, 1) if avg_score else None,
    }


@router.get("/recent-activity")
def recent_activity(limit: int = 10, db: Session = Depends(get_db), _=Depends(require_admin)):
    logs = (
        db.query(ReviewLog)
        .order_by(ReviewLog.reviewed_at.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": l.id,
            "repo_full_name": l.repo_full_name,
            "pr_number": l.pr_number,
            "pr_title": l.pr_title,
            "verdict": l.verdict,
            "score": l.score,
            "reviewed_at": l.reviewed_at.isoformat() if l.reviewed_at else None,
        }
        for l in logs
    ]
