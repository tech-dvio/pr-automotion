import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

# Ensure backend dir is on path for sibling imports
sys.path.insert(0, str(Path(__file__).parent))

from database import init_db, SessionLocal
from routers import auth, repos, dashboard, settings, logs
from routers.settings import initialize_admin_token
from webhook_handler import handle_webhook


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    db = SessionLocal()
    try:
        initialize_admin_token(db)
    finally:
        db.close()
    yield


app = FastAPI(title="PR Review Agent Dashboard", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:4173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API routers
app.include_router(auth.router,      prefix="/api/auth",      tags=["auth"])
app.include_router(repos.router,     prefix="/api/repos",     tags=["repos"])
app.include_router(dashboard.router, prefix="/api/dashboard", tags=["dashboard"])
app.include_router(settings.router,  prefix="/api/settings",  tags=["settings"])
app.include_router(logs.router,      prefix="/api/logs",      tags=["logs"])

# GitHub webhook receiver
app.post("/webhook")(handle_webhook)


@app.get("/health")
def health():
    return {"status": "ok", "agent": "pr-review-dashboard"}


# Serve React SPA — must be after all API routes
FRONTEND_DIST = Path(__file__).parent.parent / "frontend" / "dist"
if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIST / "assets")), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(request: Request, full_path: str):
        index = FRONTEND_DIST / "index.html"
        return FileResponse(str(index))
