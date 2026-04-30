from __future__ import annotations
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel


class LogSummary(BaseModel):
    id: int
    repo_full_name: str
    pr_number: int
    pr_title: Optional[str]
    author: Optional[str]
    verdict: Optional[str]
    score: Optional[int]
    issues_count: int
    critical_count: int
    high_count: int
    merged: bool
    reviewed_at: datetime


class LogDetail(LogSummary):
    review_json: Optional[str]


class LogListResponse(BaseModel):
    total: int
    page: int
    per_page: int
    items: List[LogSummary]
