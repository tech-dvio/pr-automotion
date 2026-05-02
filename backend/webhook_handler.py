import asyncio
import hashlib
import hmac
import json
import os
import threading
from datetime import datetime

from fastapi import Request, Response
from sqlalchemy.orm import Session

from database import Repo, ReviewLog, SessionLocal
from encryption import decrypt
from config_loader import build_review_config, build_email_config


def _verify_signature(body: bytes, secret: str, sig_header: str) -> bool:
    if not secret:
        return True  # dev mode
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, sig_header or "")


def _run_review_thread(repo_full_name: str, pr_number: int, pr_title: str, author: str):
    db: Session = SessionLocal()
    try:
        row = db.query(Repo).filter_by(repo_full_name=repo_full_name, webhook_active=True).first()
        if not row:
            print(f"[webhook] No active config for {repo_full_name}")
            return

        github_token = decrypt(row.github_token_enc)
        anthropic_key = _get_global_setting(db, "anthropic_api_key")

        # Set per-request env vars for the agent (thread-local enough for single repo/thread)
        os.environ["GITHUB_TOKEN"] = github_token
        if anthropic_key:
            os.environ["ANTHROPIC_API_KEY"] = anthropic_key

        review_cfg = build_review_config(row)
        email_cfg = build_email_config(row, db)

        from pr_agent import review_pr, GitHubClient
        from smtp_notifier import SmtpNotifier

        gh = GitHubClient(github_token)
        notifier = SmtpNotifier(email_cfg) if email_cfg.enabled else None

        verdict = None
        score = None
        issues_count = 0
        critical_count = 0
        high_count = 0
        merged = False
        review_json_str = None

        try:
            print(f"[webhook] Starting review for {repo_full_name}#{pr_number}")
            result = asyncio.run(review_pr(
                config=review_cfg,
                pr_number=pr_number,
                gh=gh,
                notifier=notifier,
            ))
            if result:
                verdict = result.get("verdict")
                score = result.get("score")
                issues = result.get("issues", [])
                issues_count = len(issues)
                critical_count = sum(1 for i in issues if i.get("severity") == "critical")
                high_count = sum(1 for i in issues if i.get("severity") == "high")
                merged = result.get("merged", False)
                review_json_str = json.dumps(result)
                print(f"[webhook] Review done: verdict={verdict} score={score} issues={issues_count} critical={critical_count}")

                # Auto-close PR when critical security issues are found
                if critical_count > 0 and not merged:
                    critical_msgs = [
                        f"- {i.get('title') or i.get('message', '')}" for i in issues
                        if i.get("severity") == "critical"
                    ]
                    close_reason = (
                        "## 🚨 PR Closed — Critical Security Issues Detected\n\n"
                        "This PR has been automatically closed because the AI reviewer found "
                        f"**{critical_count} critical issue(s)** that must be resolved before merging:\n\n"
                        + "\n".join(critical_msgs)
                        + "\n\nPlease fix these issues and open a new PR."
                    )
                    try:
                        gh.close_pr(repo_full_name, pr_number, reason=close_reason)
                        print(f"[webhook] 🚨 PR #{pr_number} closed — {critical_count} critical issue(s)")
                    except Exception as ce:
                        print(f"[webhook] Could not close PR #{pr_number}: {ce}")

        except Exception as e:
            import traceback
            print(f"[webhook] ✗ Review FAILED for {repo_full_name}#{pr_number}: {type(e).__name__}: {e}")
            traceback.print_exc()
            # Post a fallback comment so the developer knows the review ran but failed
            try:
                gh.post_pr_comment(
                    repo_full_name, pr_number,
                    f"## 🤖 PR Review — Error\n\n"
                    f"The automated review encountered an error (`{type(e).__name__}`). "
                    f"Please check the server logs or re-open this PR to retry.\n\n"
                    f"_Error: {str(e)[:200]}_"
                )
            except Exception:
                pass

        try:
            log = ReviewLog(
                repo_id=row.id,
                repo_full_name=repo_full_name,
                pr_number=pr_number,
                pr_title=pr_title,
                author=author,
                verdict=verdict,
                score=score,
                issues_count=issues_count,
                critical_count=critical_count,
                high_count=high_count,
                merged=merged,
                reviewed_at=datetime.utcnow(),
                review_json=review_json_str,
            )
            db.add(log)
            db.commit()
            print(f"[webhook] Log saved for {repo_full_name}#{pr_number} verdict={verdict}")
        except Exception as db_err:
            print(f"[webhook] Failed to save log: {db_err}")

    except Exception as e:
        print(f"[webhook] Thread error for {repo_full_name}: {e}")
    finally:
        db.close()


def _get_global_setting(db: Session, key: str) -> str:
    from database import GlobalSetting
    row = db.query(GlobalSetting).filter_by(key=key).first()
    if row and row.value_enc:
        return decrypt(row.value_enc)
    return ""


async def handle_webhook(request: Request) -> Response:
    event = request.headers.get("X-GitHub-Event", "")
    sig = request.headers.get("X-Hub-Signature-256", "")
    body = await request.body()

    if event == "ping":
        return Response(content='{"ok":true}', media_type="application/json")

    if event != "pull_request":
        return Response(content='{"skipped":true}', media_type="application/json", status_code=200)

    try:
        payload = json.loads(body)
    except Exception:
        return Response(content='{"error":"invalid json"}', media_type="application/json", status_code=400)

    action = payload.get("action", "")
    if action not in ("opened", "synchronize", "reopened"):
        return Response(content='{"skipped":true}', media_type="application/json")

    repo_full_name = payload.get("repository", {}).get("full_name", "")
    pr_number = payload.get("pull_request", {}).get("number")
    pr_title = payload.get("pull_request", {}).get("title", "")
    author = payload.get("pull_request", {}).get("user", {}).get("login", "")

    if not repo_full_name or not pr_number:
        return Response(content='{"error":"missing fields"}', status_code=400)

    # Verify signature per-repo
    db: Session = SessionLocal()
    try:
        row = db.query(Repo).filter_by(repo_full_name=repo_full_name, webhook_active=True).first()
        webhook_secret = decrypt(row.webhook_secret_enc) if row else ""
    finally:
        db.close()

    if not _verify_signature(body, webhook_secret, sig):
        return Response(content='{"error":"signature mismatch"}', status_code=401)

    thread = threading.Thread(
        target=_run_review_thread,
        args=(repo_full_name, pr_number, pr_title, author),
        daemon=True,
    )
    thread.start()

    return Response(content='{"status":"accepted"}', media_type="application/json", status_code=202)
