"""Safe subprocess wrappers around `git`.

`shell=False`, explicit arg lists, no string-built commands. Only module
that shells out to git, everything downstream is pure/testable.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass

GIT_TIMEOUT_SECONDS = 30

# Never let a git child process see these (defense in depth; a compromised
# hook in a checked-out repo shouldn't be able to read them).
_SENSITIVE_ENV_VARS = ("GITHUB_TOKEN", "GEMINI_API_KEY")


class GitError(RuntimeError):
    """Raised when a required git call fails."""


@dataclass(frozen=True)
class GitCallResult:
    returncode: int
    stdout: str
    stderr: str


def _safe_env() -> dict[str, str]:
    return {k: v for k, v in os.environ.items() if k not in _SENSITIVE_ENV_VARS}


def _run_git(args: list[str], cwd: str | None = None) -> GitCallResult:
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=cwd,
            shell=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=GIT_TIMEOUT_SECONDS,
            env=_safe_env(),
        )
    except FileNotFoundError as exc:
        raise GitError("git executable not found on PATH") from exc
    except subprocess.TimeoutExpired as exc:
        raise GitError(f"git call timed out after {GIT_TIMEOUT_SECONDS}s: {args}") from exc
    return GitCallResult(
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def is_git_repository(path: str | None = None) -> bool:
    result = _run_git(["rev-parse", "--git-dir"], cwd=path)
    return result.returncode == 0


def get_diff(ref_range: str, cwd: str | None = None) -> str:
    """Unified diff text for `ref_range`. Raises GitError on failure;
    empty string for a valid no-op range is not an error."""
    result = _run_git(["diff", "--unified=3", ref_range], cwd=cwd)
    if result.returncode != 0:
        raise GitError(f"git diff failed for range {ref_range!r}: {result.stderr.strip()}")
    return result.stdout


def get_commit_messages(ref_range: str, cwd: str | None = None) -> tuple[str, ...]:
    """Commit subject lines (first line only) for `ref_range`."""
    result = _run_git(["log", "--pretty=format:%s", ref_range], cwd=cwd)
    if result.returncode != 0:
        return ()
    return tuple(line for line in result.stdout.splitlines() if line.strip())


def is_ancestor(ancestor_sha: str, descendant_sha: str, cwd: str | None = None) -> bool | None:
    """Is `ancestor_sha` an ancestor of `descendant_sha`?

    Force-push detection for `pull_request` `synchronize` events: compare
    the payload's `before`/`after` SHAs. Fast-forward keeps `before` an
    ancestor of `after`; force-push doesn't. (There's no `forced` field on
    this payload, that's a `push`-event-only field.)

    Returns None if undeterminable (shallow clone, unknown SHA), callers
    must NOT treat None as force-push. A false accusation costs more trust
    than an occasional missed one.
    """
    if not ancestor_sha or not descendant_sha:
        return None
    result = _run_git(["merge-base", "--is-ancestor", ancestor_sha, descendant_sha], cwd=cwd)
    if result.returncode == 0:
        return True
    if result.returncode == 1:
        return False
    return None  # unknown revision / missing history
