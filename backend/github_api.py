import requests
from fastapi import HTTPException


class GitHubWebhookManager:
    BASE = "https://api.github.com"

    def _headers(self, token: str) -> dict:
        return {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def verify_token(self, token: str) -> dict:
        resp = requests.get(
            f"{self.BASE}/user",
            headers=self._headers(token),
            timeout=10,
        )
        if resp.status_code == 401:
            raise HTTPException(status_code=400, detail="GitHub token is invalid or expired")
        resp.raise_for_status()
        return resp.json()

    def register_webhook(
        self,
        owner: str,
        repo: str,
        token: str,
        secret: str,
        payload_url: str,
    ) -> int:
        resp = requests.post(
            f"{self.BASE}/repos/{owner}/{repo}/hooks",
            headers=self._headers(token),
            json={
                "name": "web",
                "active": True,
                "events": ["pull_request"],
                "config": {
                    "url": payload_url,
                    "content_type": "json",
                    "secret": secret,
                    "insecure_ssl": "0",
                },
            },
            timeout=15,
        )
        if resp.status_code == 422:
            existing = self._find_existing_hook(owner, repo, token, payload_url)
            if existing:
                return existing
            raise HTTPException(
                status_code=422,
                detail=resp.json().get("message", "Webhook already exists with a different URL"),
            )
        if resp.status_code == 403:
            raise HTTPException(
                status_code=400,
                detail="Token lacks 'admin:repo_hook' scope — please regenerate with that permission",
            )
        if resp.status_code == 404:
            raise HTTPException(
                status_code=404,
                detail=f"Repository '{owner}/{repo}' not found or token has no access",
            )
        resp.raise_for_status()
        return resp.json()["id"]

    def _find_existing_hook(self, owner: str, repo: str, token: str, payload_url: str) -> int | None:
        resp = requests.get(
            f"{self.BASE}/repos/{owner}/{repo}/hooks",
            headers=self._headers(token),
            timeout=15,
        )
        if not resp.ok:
            return None
        for hook in resp.json():
            if hook.get("config", {}).get("url") == payload_url:
                return hook["id"]
        return None

    def delete_webhook(self, owner: str, repo: str, token: str, hook_id: int) -> bool:
        resp = requests.delete(
            f"{self.BASE}/repos/{owner}/{repo}/hooks/{hook_id}",
            headers=self._headers(token),
            timeout=15,
        )
        return resp.ok

    def ping_webhook(self, owner: str, repo: str, token: str, hook_id: int) -> bool:
        resp = requests.post(
            f"{self.BASE}/repos/{owner}/{repo}/hooks/{hook_id}/pings",
            headers=self._headers(token),
            timeout=15,
        )
        return resp.ok


github_manager = GitHubWebhookManager()
