"""Idempotent GitHub PR comment posting.

Zero third-party dependencies: uses `urllib.request` only. Never logs the
token. All calls target `api.github.com` only, with a 15-second timeout.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

API_ROOT = "https://api.github.com"
TIMEOUT_SECONDS = 15
MAX_COMMENT_PAGES = 10
MAX_RETRIES = 2
RETRY_BACKOFF_SECONDS = 1.0


class GitHubApiError(RuntimeError):
    pass


def _sleep(seconds: float) -> None:
    time.sleep(seconds)


def _request(method: str, url: str, token: str, body: dict | None = None) -> dict | list:
    if not url.startswith(API_ROOT + "/"):
        raise GitHubApiError(f"refusing to call non-GitHub-API URL: {url}")

    data = json.dumps(body).encode("utf-8") if body is not None else None
    last_error: Exception | None = None

    for attempt in range(MAX_RETRIES + 1):
        req = urllib.request.Request(
            url,
            data=data,
            method=method,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "Content-Type": "application/json",
                "User-Agent": "chess-review-bot",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            retryable = exc.code == 429 or exc.code >= 500
            last_error = exc
            if retryable and attempt < MAX_RETRIES:
                retry_after = exc.headers.get("Retry-After") if exc.headers else None
                try:
                    delay = float(retry_after) if retry_after else RETRY_BACKOFF_SECONDS * (2**attempt)
                except ValueError:
                    delay = RETRY_BACKOFF_SECONDS * (2**attempt)
                _sleep(delay)
                continue
            raise GitHubApiError(f"GitHub API {method} {url} failed: HTTP {exc.code}") from exc
        except urllib.error.URLError as exc:
            last_error = exc
            if attempt < MAX_RETRIES:
                _sleep(RETRY_BACKOFF_SECONDS * (2**attempt))
                continue
            raise GitHubApiError(f"GitHub API {method} {url} failed: {exc.reason}") from exc

    raise GitHubApiError(f"GitHub API {method} {url} failed: {last_error}")


def find_existing_comment(
    owner: str, repo: str, pr_number: int, token: str, marker: str
) -> int | None:
    """Comment id of an existing chess-review-bot comment, or None.

    Paginates: chess-review-bot posts only one comment, but other
    participants can push it past page 1 on a busy PR.
    """
    for page in range(1, MAX_COMMENT_PAGES + 1):
        url = (
            f"{API_ROOT}/repos/{owner}/{repo}/issues/{pr_number}/comments"
            f"?per_page=100&page={page}"
        )
        comments = _request("GET", url, token)
        if not isinstance(comments, list) or not comments:
            return None
        for comment in comments:
            if marker in comment.get("body", ""):
                return comment.get("id")
        if len(comments) < 100:
            return None  # last page
    return None


def upsert_comment(
    owner: str, repo: str, pr_number: int, token: str, marker: str, body: str
) -> None:
    """Create or update the PR comment. Never posts more than one per PR."""
    existing_id = find_existing_comment(owner, repo, pr_number, token, marker)
    if existing_id is not None:
        url = f"{API_ROOT}/repos/{owner}/{repo}/issues/comments/{existing_id}"
        _request("PATCH", url, token, body={"body": body})
    else:
        url = f"{API_ROOT}/repos/{owner}/{repo}/issues/{pr_number}/comments"
        _request("POST", url, token, body={"body": body})
