from __future__ import annotations
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, field_validator
import re


ROLE_OPTIONS = {"critical", "high", "block", "merge", "approve", "digest"}


class EmailRecipientIn(BaseModel):
    email: str
    role: str

    @field_validator("role")
    @classmethod
    def valid_role(cls, v: str) -> str:
        if v not in ROLE_OPTIONS:
            raise ValueError(f"role must be one of {ROLE_OPTIONS}")
        return v


class RepoCreate(BaseModel):
    repo_full_name: str
    display_name: Optional[str] = None
    github_token: str
    webhook_secret: Optional[str] = None   # auto-generated if blank
    auto_merge: bool = False
    auto_merge_strategy: str = "squash"
    require_tests: bool = True
    block_on_severity: List[str] = ["critical", "high"]
    protected_files: List[str] = []
    custom_rules: List[str] = []
    max_file_changes: int = 50
    email_recipients: List[EmailRecipientIn] = []

    @field_validator("repo_full_name")
    @classmethod
    def valid_repo(cls, v: str) -> str:
        if not re.match(r"^[\w\-\.]+/[\w\-\.]+$", v):
            raise ValueError('repo_full_name must be in "owner/repo" format')
        return v

    @field_validator("auto_merge_strategy")
    @classmethod
    def valid_strategy(cls, v: str) -> str:
        if v not in {"squash", "merge", "rebase"}:
            raise ValueError("auto_merge_strategy must be squash, merge, or rebase")
        return v


class RepoUpdate(BaseModel):
    display_name: Optional[str] = None
    github_token: Optional[str] = None
    webhook_secret: Optional[str] = None
    auto_merge: Optional[bool] = None
    auto_merge_strategy: Optional[str] = None
    require_tests: Optional[bool] = None
    block_on_severity: Optional[List[str]] = None
    protected_files: Optional[List[str]] = None
    custom_rules: Optional[List[str]] = None
    max_file_changes: Optional[int] = None
    email_recipients: Optional[List[EmailRecipientIn]] = None


class EmailRecipientOut(BaseModel):
    id: int
    email: str
    role: str


class RepoSummary(BaseModel):
    id: int
    repo_full_name: str
    display_name: Optional[str]
    webhook_active: bool
    github_hook_id: Optional[int]
    auto_merge: bool
    created_at: datetime
    updated_at: datetime
    recipient_count: int = 0
    last_verdict: Optional[str] = None
    last_score: Optional[int] = None
    last_reviewed_at: Optional[datetime] = None


class RepoDetail(RepoSummary):
    auto_merge_strategy: str
    require_tests: bool
    block_on_severity: List[str]
    protected_files: List[str]
    custom_rules: List[str]
    max_file_changes: int
    github_token_masked: str = "••••••••"
    webhook_secret_masked: str = "••••••••"
    email_recipients: List[EmailRecipientOut] = []


class TestConnectionRequest(BaseModel):
    github_token: str


class TestConnectionResponse(BaseModel):
    valid: bool
    login: Optional[str] = None
    error: Optional[str] = None


class RevealRequest(BaseModel):
    field: str   # "github_token" | "webhook_secret"
