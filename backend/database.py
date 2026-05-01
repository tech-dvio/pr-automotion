import os
from datetime import datetime
from sqlalchemy import (
    create_engine, Column, Integer, String, Boolean, DateTime, ForeignKey, Text, text
)
from sqlalchemy.orm import declarative_base, sessionmaker, Session

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./data/dashboard.db")

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class Repo(Base):
    __tablename__ = "repos"

    id = Column(Integer, primary_key=True, autoincrement=True)
    repo_full_name = Column(String, unique=True, nullable=False)  # "owner/repo"
    display_name = Column(String, nullable=True)
    github_token_enc = Column(Text, nullable=False)       # Fernet-encrypted
    webhook_secret_enc = Column(Text, nullable=False)     # Fernet-encrypted
    github_hook_id = Column(Integer, nullable=True)
    webhook_active = Column(Boolean, default=False)
    auto_merge = Column(Boolean, default=False)
    auto_merge_strategy = Column(String, default="squash")
    require_tests = Column(Boolean, default=True)
    block_on_severity = Column(Text, default='["critical","high"]')   # JSON
    protected_files = Column(Text, default="[]")                      # JSON
    custom_rules = Column(Text, default="[]")                         # JSON
    max_file_changes = Column(Integer, default=50)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class EmailRecipient(Base):
    __tablename__ = "email_recipients"

    id = Column(Integer, primary_key=True, autoincrement=True)
    repo_id = Column(Integer, ForeignKey("repos.id", ondelete="CASCADE"), nullable=False)
    email = Column(String, nullable=False)
    role = Column(String, nullable=False)  # critical/high/block/merge/approve/digest


class GlobalSetting(Base):
    __tablename__ = "global_settings"

    key = Column(String, primary_key=True)
    value_enc = Column(Text, nullable=False, default="")


class ReviewLog(Base):
    __tablename__ = "review_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    repo_id = Column(Integer, ForeignKey("repos.id", ondelete="SET NULL"), nullable=True)
    repo_full_name = Column(String, nullable=False)
    pr_number = Column(Integer, nullable=False)
    pr_title = Column(String, nullable=True)
    author = Column(String, nullable=True)
    verdict = Column(String, nullable=True)   # approve/request_changes/block
    score = Column(Integer, nullable=True)
    issues_count = Column(Integer, default=0)
    critical_count = Column(Integer, default=0)
    high_count = Column(Integer, default=0)
    merged = Column(Boolean, default=False)
    reviewed_at = Column(DateTime, default=datetime.utcnow)
    review_json = Column(Text, nullable=True)


def _migrate_db():
    """Add columns that may be missing from older DB instances (SQLite doesn't support ALTER easily)."""
    migrations = [
        "ALTER TABLE review_log ADD COLUMN critical_count INTEGER DEFAULT 0",
        "ALTER TABLE review_log ADD COLUMN high_count INTEGER DEFAULT 0",
        "ALTER TABLE review_log ADD COLUMN merged BOOLEAN DEFAULT 0",
        "ALTER TABLE review_log ADD COLUMN author TEXT",
        "ALTER TABLE review_log ADD COLUMN pr_title TEXT",
    ]
    with engine.connect() as conn:
        for sql in migrations:
            try:
                conn.execute(text(sql))
                conn.commit()
            except Exception:
                pass  # column already exists


def init_db():
    os.makedirs("data", exist_ok=True)
    Base.metadata.create_all(bind=engine)
    _migrate_db()


def get_db():
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()
