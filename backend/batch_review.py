"""
Batch PR Reviewer
=================
Review ALL open PRs in one or more repos at once.
Useful for:
  - Catching up on a backlog
  - Running a nightly review sweep
  - Onboarding a new client repo

Usage:
    python batch_review.py --repo owner/repo
    python batch_review.py --repos config/repos.json
    python batch_review.py --repo owner/repo --dry-run
"""

import asyncio
import argparse
import json
from pathlib import Path
from datetime import datetime

from pr_agent import GitHubClient, ReviewConfig, review_pr
from dotenv import load_dotenv
import os

load_dotenv()
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")


async def batch_review_repo(
    repo: str,
    config: ReviewConfig,
    dry_run: bool = False,
    max_concurrent: int = 2
):
    """Review all open PRs in a single repo."""
    gh = GitHubClient(GITHUB_TOKEN)
    prs = gh.list_open_prs(repo)

    if not prs:
        print(f"[BATCH] No open PRs in {repo}")
        return []

    print(f"\n[BATCH] {len(prs)} open PRs in {repo}")
    for pr in prs:
        print(f"  #{pr['number']}: {pr['title']} by @{pr['user']['login']}")

    semaphore = asyncio.Semaphore(max_concurrent)
    results = []

    async def review_one(pr: dict):
        async with semaphore:
            pr_number = pr["number"]
            try:
                result = await review_pr(repo, pr_number, config, dry_run=dry_run)
                results.append({"pr": pr_number, "status": "success", **result})
            except Exception as e:
                print(f"[BATCH] ✗ PR #{pr_number} failed: {e}")
                results.append({"pr": pr_number, "status": "error", "error": str(e)})

    await asyncio.gather(*[review_one(pr) for pr in prs])

    # Save batch summary
    summary = {
        "run_at": datetime.now().isoformat(),
        "repo": repo,
        "total": len(prs),
        "success": sum(1 for r in results if r["status"] == "success"),
        "dry_run": dry_run,
        "results": results,
    }
    path = Path("output/reports") / f"batch_{repo.replace('/', '_')}_{datetime.now().strftime('%Y%m%d_%H%M')}.json"
    path.write_text(json.dumps(summary, indent=2, default=str))
    print(f"\n[BATCH] Report → {path}")
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo",       help="owner/repo to review")
    parser.add_argument("--repos",      help="JSON file with list of repos")
    parser.add_argument("--dry-run",    action="store_true")
    parser.add_argument("--concurrent", type=int, default=2)
    args = parser.parse_args()

    repos = []
    if args.repo:
        repos = [args.repo]
    elif args.repos:
        repos = json.loads(Path(args.repos).read_text())

    if not repos:
        print("Provide --repo or --repos")
        exit(1)

    async def main():
        for repo in repos:
            config = ReviewConfig(repo=repo, auto_merge=False)
            await batch_review_repo(repo, config, dry_run=args.dry_run, max_concurrent=args.concurrent)

    asyncio.run(main())
