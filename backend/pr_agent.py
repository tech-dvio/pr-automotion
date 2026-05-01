"""
GitHub PR Review & Merge Agent — Built with Claude Agent SDK
=============================================================
Full pipeline:
  1. Fetch PR       — Pull diff, files changed, metadata from GitHub API
  2. Code Review    — Multi-lens analysis: bugs, security, perf, style, tests
  3. Post Comments  — Inline comments on specific lines + overall PR review
  4. Merge Decision — Approve / Request Changes / Block based on severity
  5. Auto-Merge     — Optionally merge if all checks pass and review is clean

Supports:
  - Any GitHub repo (public or private)
  - Configurable review rules per repo / team
  - Webhook mode (trigger on PR open/update events)
  - Batch mode (review all open PRs in a repo)
"""

import asyncio
import json
import os
import re
import argparse
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, field

import requests
from dotenv import load_dotenv

from claude_agent_sdk import query, ClaudeAgentOptions, AssistantMessage, TextBlock
from smtp_notifier import EmailConfig, SmtpNotifier

load_dotenv()

# ── Config ────────────────────────────────────────────────────────────────────

OUTPUT_DIR  = Path("output")
REVIEW_DIR  = OUTPUT_DIR / "reviews"
REPORT_DIR  = OUTPUT_DIR / "reports"
for d in [REVIEW_DIR, REPORT_DIR]:
    d.mkdir(parents=True, exist_ok=True)

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
GITHUB_API   = "https://api.github.com"

HEADERS = {
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}


@dataclass
class ReviewConfig:
    """Per-repo review configuration."""
    repo: str                           # "owner/repo"
    auto_merge: bool = False            # Merge automatically if review passes
    auto_merge_strategy: str = "squash" # squash | merge | rebase
    block_on_severity: list = field(default_factory=lambda: ["critical", "high"])
    require_tests: bool = True          # Block if no test files changed alongside code
    max_file_changes: int = 50          # Flag PRs touching too many files
    protected_files: list = field(default_factory=list)  # Files that need extra scrutiny
    custom_rules: list = field(default_factory=list)      # e.g. ["No hardcoded secrets", "Use TypeScript"]
    language: str = "auto"              # auto-detect or specify: python, javascript, go, etc.
    notify_slack: bool = False
    slack_webhook: str = ""


# ── GitHub API Helpers ────────────────────────────────────────────────────────

class GitHubClient:
    def __init__(self, token: str):
        self.token = token
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def get(self, url: str, params: dict = None) -> dict:
        resp = requests.get(url, headers=self.headers, params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def post(self, url: str, payload: dict) -> dict:
        resp = requests.post(url, headers=self.headers, json=payload, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def put(self, url: str, payload: dict) -> dict:
        resp = requests.put(url, headers=self.headers, json=payload, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def fetch_pr(self, repo: str, pr_number: int) -> dict:
        """Fetch PR metadata."""
        return self.get(f"{GITHUB_API}/repos/{repo}/pulls/{pr_number}")

    def fetch_pr_files(self, repo: str, pr_number: int) -> list:
        """Fetch list of changed files with patches."""
        return self.get(
            f"{GITHUB_API}/repos/{repo}/pulls/{pr_number}/files",
            params={"per_page": 100}
        )

    def fetch_pr_commits(self, repo: str, pr_number: int) -> list:
        """Fetch commit messages in the PR."""
        return self.get(f"{GITHUB_API}/repos/{repo}/pulls/{pr_number}/commits")

    def fetch_pr_comments(self, repo: str, pr_number: int) -> list:
        """Fetch existing review comments."""
        return self.get(f"{GITHUB_API}/repos/{repo}/pulls/{pr_number}/comments")

    def fetch_file_content(self, repo: str, path: str, ref: str) -> str:
        """Fetch full file content at a given commit ref."""
        try:
            data = self.get(f"{GITHUB_API}/repos/{repo}/contents/{path}", params={"ref": ref})
            import base64
            return base64.b64decode(data.get("content", "")).decode("utf-8", errors="replace")
        except Exception:
            return ""

    def post_review(self, repo: str, pr_number: int, review: dict) -> dict:
        """
        Post a full review with inline comments.
        review = {
            "body": "overall review comment",
            "event": "APPROVE" | "REQUEST_CHANGES" | "COMMENT",
            "comments": [{"path": "...", "line": N, "body": "..."}]
        }
        """
        return self.post(
            f"{GITHUB_API}/repos/{repo}/pulls/{pr_number}/reviews",
            payload=review
        )

    def post_pr_comment(self, repo: str, pr_number: int, body: str) -> dict:
        """Post a general comment on the PR."""
        return self.post(
            f"{GITHUB_API}/repos/{repo}/issues/{pr_number}/comments",
            payload={"body": body}
        )

    def approve_pr(self, repo: str, pr_number: int, message: str = "") -> dict:
        return self.post_review(repo, pr_number, {
            "body": message,
            "event": "APPROVE",
            "comments": []
        })

    def request_changes(self, repo: str, pr_number: int, message: str, inline_comments: list) -> dict:
        return self.post_review(repo, pr_number, {
            "body": message,
            "event": "REQUEST_CHANGES",
            "comments": inline_comments
        })

    def merge_pr(self, repo: str, pr_number: int, title: str, strategy: str = "squash") -> dict:
        """Merge the PR."""
        return self.put(
            f"{GITHUB_API}/repos/{repo}/pulls/{pr_number}/merge",
            payload={
                "commit_title": title,
                "merge_method": strategy,
            }
        )

    def close_pr(self, repo: str, pr_number: int, reason: str = "") -> dict:
        """Close (not merge) a PR."""
        if reason:
            try:
                self.post(
                    f"{GITHUB_API}/repos/{repo}/issues/{pr_number}/comments",
                    payload={"body": reason},
                )
            except Exception:
                pass
        resp = requests.patch(
            f"{GITHUB_API}/repos/{repo}/pulls/{pr_number}",
            headers=self.headers,
            json={"state": "closed"},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()

    def list_open_prs(self, repo: str) -> list:
        """List all open PRs in a repo."""
        return self.get(
            f"{GITHUB_API}/repos/{repo}/pulls",
            params={"state": "open", "per_page": 50}
        )

    def add_labels(self, repo: str, pr_number: int, labels: list) -> dict:
        return self.post(
            f"{GITHUB_API}/repos/{repo}/issues/{pr_number}/labels",
            payload={"labels": labels}
        )


# ── Step 1: PR Context Builder ────────────────────────────────────────────────

def build_pr_context(gh: GitHubClient, repo: str, pr_number: int, config: ReviewConfig) -> dict:
    """
    Fetches all PR data from GitHub and builds a structured context
    object that gets passed to the review agent.
    """
    print(f"\n{'='*60}")
    print(f"  STEP 1: Fetching PR #{pr_number} from {repo}")
    print(f"{'='*60}")

    pr       = gh.fetch_pr(repo, pr_number)
    files    = gh.fetch_pr_files(repo, pr_number)
    commits  = gh.fetch_pr_commits(repo, pr_number)
    comments = gh.fetch_pr_comments(repo, pr_number)

    # Build diff summary
    file_summaries = []
    total_additions = 0
    total_deletions = 0
    has_tests = False
    languages = set()

    for f in files:
        filename  = f.get("filename", "")
        status    = f.get("status", "modified")  # added/modified/removed/renamed
        additions = f.get("additions", 0)
        deletions = f.get("deletions", 0)
        patch     = f.get("patch", "")           # The actual diff

        total_additions += additions
        total_deletions += deletions

        # Detect test files
        if any(x in filename.lower() for x in ["test", "spec", "__test__", "_test.go"]):
            has_tests = True

        # Detect language
        ext = Path(filename).suffix.lower()
        lang_map = {".py": "Python", ".js": "JavaScript", ".ts": "TypeScript",
                    ".go": "Go", ".java": "Java", ".rs": "Rust", ".rb": "Ruby",
                    ".php": "PHP", ".cs": "C#", ".cpp": "C++", ".tf": "Terraform"}
        if ext in lang_map:
            languages.add(lang_map[ext])

        file_summaries.append({
            "filename":  filename,
            "status":    status,
            "additions": additions,
            "deletions": deletions,
            "patch":     patch[:4000] if patch else "",  # Cap large diffs
            "is_protected": filename in config.protected_files,
        })

    commit_messages = [c["commit"]["message"].split("\n")[0] for c in commits]

    context = {
        "repo":            repo,
        "pr_number":       pr_number,
        "title":           pr.get("title", ""),
        "description":     pr.get("body", "") or "(no description)",
        "author":          pr.get("user", {}).get("login", "unknown"),
        "base_branch":     pr.get("base", {}).get("ref", "main"),
        "head_branch":     pr.get("head", {}).get("ref", ""),
        "head_sha":        pr.get("head", {}).get("sha", ""),
        "total_additions": total_additions,
        "total_deletions": total_deletions,
        "files_changed":   len(files),
        "has_tests":       has_tests,
        "languages":       list(languages),
        "commit_messages": commit_messages,
        "files":           file_summaries,
        "existing_comments": len(comments),
        "config":          {
            "require_tests":       config.require_tests,
            "max_file_changes":    config.max_file_changes,
            "protected_files":     config.protected_files,
            "custom_rules":        config.custom_rules,
            "block_on_severity":   config.block_on_severity,
        },
    }

    print(f"  ✓ PR: '{pr.get('title', '')}'")
    print(f"  ✓ Author: {context['author']}")
    print(f"  ✓ Files changed: {len(files)} | +{total_additions} -{total_deletions} lines")
    print(f"  ✓ Languages: {', '.join(languages) or 'unknown'}")
    print(f"  ✓ Has tests: {has_tests}")

    return context


# ── Step 2: Code Review Agent ─────────────────────────────────────────────────

async def run_code_review(context: dict) -> dict:
    """
    The main review agent. Performs multi-lens analysis:
    - Correctness & Bugs
    - Security Vulnerabilities
    - Performance Issues
    - Code Style & Best Practices
    - Test Coverage
    - Documentation
    - Breaking Changes
    """
    print(f"\n{'='*60}")
    print(f"  STEP 2: Running Code Review ({len(context['files'])} files)")
    print(f"{'='*60}")

    files_text = json.dumps(context["files"], indent=2)
    config     = context["config"]

    prompt = f"""
You are a senior software engineer performing a thorough code review.

PR Information:
- Repo: {context['repo']}
- PR #{context['pr_number']}: "{context['title']}"
- Author: {context['author']}
- Branch: {context['head_branch']} → {context['base_branch']}
- Description: {context['description']}
- Languages: {', '.join(context['languages'])}
- Commits: {json.dumps(context['commit_messages'])}
- Files changed: {context['files_changed']} (+{context['total_additions']} -{context['total_deletions']} lines)
- Has test changes: {context['has_tests']}

Review Configuration:
- Require tests: {config['require_tests']}
- Max files per PR: {config['max_file_changes']}
- Protected files: {config['protected_files']}
- Custom rules: {config['custom_rules']}
- Block on severity: {config['block_on_severity']}

Changed Files & Diffs:
{files_text}

Perform a THOROUGH review across these lenses:

1. BUGS & CORRECTNESS
   - Logic errors, off-by-one, null pointer risks, unhandled exceptions
   - Race conditions, deadlocks, incorrect error handling
   - Wrong algorithm or data structure choices

2. SECURITY
   - SQL injection, XSS, CSRF risks
   - Hardcoded secrets, tokens, passwords
   - Insecure dependencies or imports
   - Missing authentication/authorization checks
   - Sensitive data exposure in logs

3. PERFORMANCE
   - N+1 queries, missing indexes
   - Inefficient loops or algorithms (O(n²) where O(n) works)
   - Memory leaks, large allocations in hot paths
   - Missing caching where beneficial

4. CODE QUALITY & STYLE
   - Naming conventions, readability
   - DRY violations (duplicated code)
   - Functions/classes too large or doing too much
   - Missing or incorrect comments/docstrings
   - Dead code, unused variables/imports

5. TESTS
   - Missing tests for new functionality
   - Test quality (are edge cases covered?)
   - Flaky test patterns

6. BREAKING CHANGES
   - API signature changes
   - Database schema changes without migrations
   - Config changes that need documentation

7. PR HYGIENE
   - Is the PR too large? (>{config['max_file_changes']} files)
   - Commit message quality
   - PR description quality
   - Are protected files changed: {config['protected_files']}

For EACH issue found, specify:
- Which file and line number (from the diff)
- Severity: critical | high | medium | low | info
- Category: bug | security | performance | style | test | breaking | hygiene
- Clear explanation of the problem
- A concrete suggested fix

Return ONLY this JSON:
{{
  "summary": "2-3 sentence overall assessment",
  "verdict": "approve | request_changes | block",
  "verdict_reason": "Why you made this verdict",
  "overall_score": 85,
  "pr_size": "small | medium | large | too_large",
  "issues": [
    {{
      "file": "path/to/file.py",
      "line": 42,
      "severity": "critical|high|medium|low|info",
      "category": "bug|security|performance|style|test|breaking|hygiene",
      "title": "Short issue title",
      "description": "Clear explanation of the problem",
      "suggestion": "Concrete code or approach to fix it",
      "code_snippet": "The problematic code (copied from diff)"
    }}
  ],
  "positives": ["Thing done well 1", "Thing done well 2"],
  "missing_tests": true,
  "has_security_issues": false,
  "breaking_changes": [],
  "approval_blockers": ["List of issues that MUST be fixed before merge"],
  "nice_to_have": ["Non-blocking suggestions"],
  "labels_to_add": ["bug", "needs-tests", "security", "performance", "ready-to-merge"]
}}
"""

    result = await _run_agent(prompt, max_turns=4)
    data = _extract_json(result)

    if data:
        issues = data.get("issues", [])
        critical = sum(1 for i in issues if i.get("severity") == "critical")
        high     = sum(1 for i in issues if i.get("severity") == "high")
        medium   = sum(1 for i in issues if i.get("severity") == "medium")

        print(f"  ✓ Verdict: {data.get('verdict', 'unknown').upper()}")
        print(f"  ✓ Score: {data.get('overall_score', 0)}/100")
        print(f"  ✓ Issues: {len(issues)} total — {critical} critical, {high} high, {medium} medium")
        print(f"  ✓ Blockers: {len(data.get('approval_blockers', []))}")
        if data.get("has_security_issues"):
            print(f"  ⚠ SECURITY ISSUES FOUND!")

    return data or {
        "verdict": "request_changes",
        "summary": "Review could not be parsed.",
        "issues": [],
        "overall_score": 0,
        "approval_blockers": [],
    }


# ── Step 3: Review Comment Formatter ─────────────────────────────────────────

async def format_review_comment(context: dict, review: dict) -> dict:
    """
    Takes the raw review JSON and formats it into:
    - A beautiful overall PR comment (markdown with tables, emoji)
    - Inline comments per file/line for GitHub's review API
    """
    print(f"\n{'='*60}")
    print(f"  STEP 3: Formatting Review Comments")
    print(f"{'='*60}")

    verdict = review.get("verdict", "request_changes")
    score = review.get("overall_score", 0)
    issues = review.get("issues", [])

    prompt = f"""
Write a concise GitHub PR review comment for PR #{context['pr_number']} ("{context['title']}") by @{context['author']}.

Verdict: {verdict} | Score: {score}/100
Issues: {json.dumps([{{"severity": i.get("severity"), "file": i.get("file"), "line": i.get("line"), "title": i.get("title"), "suggestion": i.get("suggestion")}} for i in issues], indent=2)}
Blockers: {json.dumps(review.get("approval_blockers", []))}
Positives: {json.dumps(review.get("positives", []))}
Summary: {review.get("summary", "")}

Rules:
- overall_comment must be SHORT — max 300 words, use bullet points not prose
- Header: verdict emoji + score badge only
- List only top 5 issues max (prioritise critical/high)
- For inline comments: only comment on lines that exist in the diff; keep body under 2 sentences

Return ONLY this JSON:
{{
  "overall_comment": "short markdown comment",
  "inline_comments": [{{"path": "file.py", "line": 42, "body": "short comment"}}]
}}
Severity emoji: 🔴 critical 🟠 high 🟡 medium 🔵 low
"""

    result = await _run_agent(prompt, max_turns=3)
    data = _extract_json(result)

    if data:
        print(f"  ✓ Overall comment: {len(data.get('overall_comment', ''))} chars")
        print(f"  ✓ Inline comments: {len(data.get('inline_comments', []))}")

    return data or {"overall_comment": review.get("summary", "Review complete."), "inline_comments": []}


# ── Step 4: Post to GitHub & Decide ──────────────────────────────────────────

def post_review_to_github(
    gh: GitHubClient,
    repo: str,
    pr_number: int,
    context: dict,
    review: dict,
    formatted: dict,
    config: ReviewConfig,
    dry_run: bool = False
) -> dict:
    """
    Posts the review to GitHub:
    - Inline comments on specific lines
    - Overall review with APPROVE / REQUEST_CHANGES / COMMENT
    - Labels
    - Optionally merges if approved
    """
    print(f"\n{'='*60}")
    print(f"  STEP 4: Posting Review to GitHub {'(DRY RUN)' if dry_run else ''}")
    print(f"{'='*60}")

    verdict         = review.get("verdict", "request_changes")
    blockers        = review.get("approval_blockers", [])
    has_security    = review.get("has_security_issues", False)
    overall_comment = formatted.get("overall_comment", "")
    inline_comments = formatted.get("inline_comments", [])

    # Determine GitHub review event
    block_severities = config.block_on_severity
    issues = review.get("issues", [])
    has_blocking_issue = any(i.get("severity") in block_severities for i in issues)

    if has_blocking_issue or has_security or blockers:
        github_event = "REQUEST_CHANGES"
    elif verdict == "approve":
        github_event = "APPROVE"
    else:
        github_event = "COMMENT"

    print(f"  GitHub event: {github_event}")
    print(f"  Inline comments to post: {len(inline_comments)}")

    if dry_run:
        print("\n  [DRY RUN] Would post this review:")
        print(f"  {overall_comment[:300]}...")
        print(f"\n  [DRY RUN] Would post {len(inline_comments)} inline comments")
        return {"dry_run": True, "event": github_event, "would_merge": False}

    # Filter inline comments to valid ones (GitHub requires line to exist in diff)
    valid_inline = [c for c in inline_comments if c.get("path") and c.get("line") and c.get("body")]

    # Post the review
    try:
        review_payload = {
            "body": overall_comment,
            "event": github_event,
            "comments": valid_inline[:20],  # GitHub caps at 20 per review
        }
        result = gh.post_review(repo, pr_number, review_payload)
        print(f"  ✓ Review posted (ID: {result.get('id', 'unknown')})")
    except Exception as e:
        print(f"  ✗ Review post failed: {e}")
        # Fallback: post as regular comment
        try:
            gh.post_pr_comment(repo, pr_number, overall_comment)
            print(f"  ✓ Fallback comment posted")
        except Exception as e2:
            print(f"  ✗ Fallback also failed: {e2}")

    # Add labels
    labels = review.get("labels_to_add", [])
    if labels:
        try:
            gh.add_labels(repo, pr_number, labels)
            print(f"  ✓ Labels added: {', '.join(labels)}")
        except Exception as e:
            print(f"  ⚠ Labels failed (may not exist in repo): {e}")

    # Auto-merge if approved and configured
    merged = False
    if config.auto_merge and github_event == "APPROVE":
        try:
            merge_title = f"{context['title']} (#{pr_number})"
            gh.merge_pr(repo, pr_number, merge_title, strategy=config.auto_merge_strategy)
            merged = True
            print(f"  ✓ PR AUTO-MERGED via {config.auto_merge_strategy}")
        except Exception as e:
            print(f"  ✗ Auto-merge failed: {e}")

    return {"event": github_event, "merged": merged, "labels": labels}


# ── Step 5: Save Review Report ────────────────────────────────────────────────

def save_review_report(context: dict, review: dict, formatted: dict, result: dict):
    """Saves a full review report locally for your records."""
    slug = f"pr{context['pr_number']}_{context['repo'].replace('/', '_')}"
    date = datetime.now().strftime("%Y-%m-%d_%H%M")

    report = {
        "reviewed_at": datetime.now().isoformat(),
        "repo": context["repo"],
        "pr_number": context["pr_number"],
        "pr_title": context["title"],
        "author": context["author"],
        "verdict": review.get("verdict"),
        "github_event": result.get("event"),
        "score": review.get("overall_score"),
        "merged": result.get("merged", False),
        "issues_count": len(review.get("issues", [])),
        "blockers": review.get("approval_blockers", []),
        "review": review,
        "formatted": formatted,
    }

    json_path = REVIEW_DIR / f"{date}_{slug}.json"
    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    # Also save the markdown comment for reference
    md_path = REVIEW_DIR / f"{date}_{slug}.md"
    md_path.write_text(formatted.get("overall_comment", ""), encoding="utf-8")

    print(f"\n  → Review JSON: {json_path}")
    print(f"  → Review MD:   {md_path}")
    return json_path, md_path


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _run_agent(prompt: str, tools: list = None, max_turns: int = 4) -> str:
    parts = []
    async for message in query(
        prompt=prompt,
        options=ClaudeAgentOptions(allowed_tools=tools or [], max_turns=max_turns)
    ):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    parts.append(block.text)
    return "\n".join(parts)


def _extract_json(text: str):
    for pattern in [r'\{[\s\S]*\}', r'\[[\s\S]*\]']:
        match = re.search(pattern, text)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                continue
    return None


# ── Main Pipeline ─────────────────────────────────────────────────────────────

async def review_pr(
    config: ReviewConfig,
    pr_number: int,
    gh: GitHubClient,
    notifier=None,
    dry_run: bool = False
):
    """Full PR review pipeline."""
    repo  = config.repo
    start = datetime.now()

    print(f"\n{'#'*60}")
    print(f"  PR REVIEW AGENT")
    print(f"  Repo      : {repo}")
    print(f"  PR        : #{pr_number}")
    print(f"  Auto-merge: {config.auto_merge}")
    print(f"  Email     : {'enabled' if notifier else 'disabled'}")
    print(f"  Dry run   : {dry_run}")
    print(f"  Started   : {start.strftime('%H:%M:%S')}")
    print(f"{'#'*60}")

    context   = build_pr_context(gh, repo, pr_number, config)
    review    = await run_code_review(context)
    formatted = await format_review_comment(context, review)
    result    = post_review_to_github(gh, repo, pr_number, context, review, formatted, config, dry_run)

    try:
        save_review_report(context, review, formatted, result)
    except Exception as e:
        print(f"  ⚠ Could not save report file: {e}")

    # ── Step 6: Email Notifications ───────────────────────────────────────────
    if notifier and not dry_run:
        print(f"\n{'='*60}")
        print(f"  STEP 6: Sending Email Notifications")
        print(f"{'='*60}")

        notifier.notify_review_complete(
            repo      = repo,
            pr_number = pr_number,
            pr_title  = context["title"],
            author    = context["author"],
            review    = review,
        )

        if result.get("merged"):
            notifier.notify_merge(
                repo      = repo,
                pr_number = pr_number,
                pr_title  = context["title"],
                author    = context["author"],
                strategy  = config.auto_merge_strategy,
            )

    elapsed = (datetime.now() - start).seconds
    print(f"\n{'#'*60}")
    print(f"  DONE in {elapsed}s")
    print(f"  Verdict   : {review.get('verdict', '?').upper()}")
    print(f"  Score     : {review.get('overall_score', 0)}/100")
    print(f"  Merged    : {result.get('merged', False)}")
    print(f"{'#'*60}\n")

    # Return flat dict that webhook_handler expects
    flat = {**review}
    flat["score"] = review.get("overall_score", review.get("score", 0))
    flat["merged"] = result.get("merged", False)
    return flat


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="GitHub PR Review Agent")
    parser.add_argument("--repo",         required=True, help="owner/repo")
    parser.add_argument("--pr",           required=True, type=int, help="PR number")
    parser.add_argument("--auto-merge",   action="store_true", help="Auto-merge if approved")
    parser.add_argument("--strategy",     default="squash", choices=["squash", "merge", "rebase"])
    parser.add_argument("--require-tests",action="store_true", default=True)
    parser.add_argument("--protected",    nargs="*", default=[], help="Protected file paths")
    parser.add_argument("--rules",        nargs="*", default=[], help="Custom review rules")
    parser.add_argument("--dry-run",      action="store_true", help="Don't post to GitHub")

    # ── Email arguments ────────────────────────────────────────────────────────
    parser.add_argument("--email-critical", nargs="*", default=[],
                        metavar="EMAIL",
                        help="Outlook addresses to alert on CRITICAL issues")
    parser.add_argument("--email-high",     nargs="*", default=[],
                        metavar="EMAIL",
                        help="Outlook addresses to alert on HIGH severity issues")
    parser.add_argument("--email-block",    nargs="*", default=[],
                        metavar="EMAIL",
                        help="Outlook addresses to alert when PR is blocked")
    parser.add_argument("--email-merge",    nargs="*", default=[],
                        metavar="EMAIL",
                        help="Outlook addresses to alert on auto-merge")
    parser.add_argument("--email-approve",  nargs="*", default=[],
                        metavar="EMAIL",
                        help="Outlook addresses to alert when PR is approved")
    parser.add_argument("--no-email",       action="store_true",
                        help="Disable all email notifications")

    args = parser.parse_args()

    review_config = ReviewConfig(
        repo=args.repo,
        auto_merge=args.auto_merge,
        auto_merge_strategy=args.strategy,
        require_tests=args.require_tests,
        protected_files=args.protected or [],
        custom_rules=args.rules or [],
    )

    email_config = EmailConfig(
        enabled            = not args.no_email,
        notify_on_critical = args.email_critical or [],
        notify_on_high     = args.email_high     or [],
        notify_on_block    = args.email_block    or [],
        notify_on_merge    = args.email_merge    or [],
        notify_on_approve  = args.email_approve  or [],
    )
    gh = GitHubClient(GITHUB_TOKEN)
    notifier = SmtpNotifier(email_config) if email_config.enabled else None
    asyncio.run(review_pr(review_config, args.pr, gh, notifier=notifier, dry_run=args.dry_run))
