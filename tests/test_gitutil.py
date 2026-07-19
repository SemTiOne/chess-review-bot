from __future__ import annotations

import subprocess

import pytest

from chessreview.gitutil import (
    GitError,
    get_commit_messages,
    get_diff,
    is_ancestor,
    is_git_repository,
)


def _git(*args: str, cwd: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path):
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    cwd = str(repo_dir)
    _git("init", "-q", cwd=cwd)
    _git("config", "user.email", "test@example.com", cwd=cwd)
    _git("config", "user.name", "Test", cwd=cwd)
    (repo_dir / "file.txt").write_text("line1\n")
    _git("add", "-A", cwd=cwd)
    _git("commit", "-q", "-m", "Initial commit", cwd=cwd)
    return repo_dir


def _head_sha(cwd: str) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=cwd, check=True, capture_output=True, text=True
    )
    return result.stdout.strip()


# ---- is_git_repository -------------------------------------------------------


def test_is_git_repository_true(repo):
    assert is_git_repository(str(repo)) is True


def test_is_git_repository_false(tmp_path):
    not_a_repo = tmp_path / "plain_dir"
    not_a_repo.mkdir()
    assert is_git_repository(str(not_a_repo)) is False


# ---- get_diff ------------------------------------------------------------------


def test_get_diff_returns_unified_diff_text(repo):
    cwd = str(repo)
    before = _head_sha(cwd)
    (repo / "file.txt").write_text("line1\nline2\n")
    _git("commit", "-a", "-q", "-m", "Add line2", cwd=cwd)
    after = _head_sha(cwd)

    diff_text = get_diff(f"{before}..{after}", cwd=cwd)
    assert "diff --git" in diff_text
    assert "+line2" in diff_text


def test_get_diff_empty_range_returns_empty_string(repo):
    cwd = str(repo)
    sha = _head_sha(cwd)
    diff_text = get_diff(f"{sha}..{sha}", cwd=cwd)
    assert diff_text == ""


def test_get_diff_invalid_range_raises_git_error(repo):
    with pytest.raises(GitError):
        get_diff("not-a-real-ref..also-not-real", cwd=str(repo))


def test_get_diff_not_a_repo_raises_git_error(tmp_path):
    not_a_repo = tmp_path / "plain_dir"
    not_a_repo.mkdir()
    with pytest.raises(GitError):
        get_diff("HEAD~1..HEAD", cwd=str(not_a_repo))


# ---- get_commit_messages ---------------------------------------------------------


def test_get_commit_messages_returns_subjects(repo):
    cwd = str(repo)
    before = _head_sha(cwd)
    (repo / "file.txt").write_text("line1\nline2\n")
    _git("commit", "-a", "-q", "-m", "Add line2", cwd=cwd)
    after = _head_sha(cwd)

    messages = get_commit_messages(f"{before}..{after}", cwd=cwd)
    assert messages == ("Add line2",)


def test_get_commit_messages_invalid_range_returns_empty_tuple(repo):
    # get_commit_messages is intentionally lenient (returns () rather than
    # raising) since a missing commit-message history shouldn't crash the
    # whole run -- it just means commit-message-quality signals fall back
    # to "empty".
    messages = get_commit_messages("not-a-real-ref..also-not-real", cwd=str(repo))
    assert messages == ()


# ---- is_ancestor (force-push detection building block) --------------------------


def test_is_ancestor_true_for_fast_forward(repo):
    cwd = str(repo)
    before = _head_sha(cwd)
    (repo / "file.txt").write_text("line1\nline2\n")
    _git("commit", "-a", "-q", "-m", "Fast-forward commit", cwd=cwd)
    after = _head_sha(cwd)

    assert is_ancestor(before, after, cwd=cwd) is True


def test_is_ancestor_false_for_rewritten_history(repo):
    cwd = str(repo)
    before = _head_sha(cwd)

    # Simulate a force-push: amend the commit instead of adding on top of
    # it, producing a new SHA whose history does NOT contain `before`.
    (repo / "file.txt").write_text("completely different content\n")
    _git("add", "-A", cwd=cwd)
    _git("commit", "--amend", "-q", "-m", "Rewritten commit", cwd=cwd)
    after = _head_sha(cwd)

    assert before != after
    assert is_ancestor(before, after, cwd=cwd) is False


def test_is_ancestor_none_for_unknown_sha(repo):
    cwd = str(repo)
    head = _head_sha(cwd)
    result = is_ancestor("0" * 40, head, cwd=cwd)
    assert result is None


def test_is_ancestor_none_for_missing_shas(repo):
    assert is_ancestor("", "somesha", cwd=str(repo)) is None
    assert is_ancestor("somesha", "", cwd=str(repo)) is None
    assert is_ancestor("", "", cwd=str(repo)) is None


# ---- sensitive env vars never reach the git subprocess ---------------------------


def test_sensitive_env_vars_not_passed_to_git_subprocess(repo, monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "should-not-reach-git")
    monkeypatch.setenv("GEMINI_API_KEY", "should-not-reach-git-either")

    # git itself doesn't echo its environment back, so assert indirectly:
    # a call using GIT_TRACE=1 combined with a fake credential helper would
    # be the most direct test, but that's environment-fragile across CI
    # runners. Instead, assert against the module's own env-filtering
    # helper directly, which is what every subprocess.run call in this
    # module is built on.
    from chessreview.gitutil import _safe_env

    safe = _safe_env()
    assert "GITHUB_TOKEN" not in safe
    assert "GEMINI_API_KEY" not in safe

    # And confirm a real call still works with the filtered environment
    # (i.e. we didn't strip something git actually needs, like PATH/HOME).
    assert is_git_repository(str(repo)) is True


# ---- subprocess-level failures (git missing, git hangs) --------------------------


def test_git_not_found_raises_git_error(monkeypatch):
    import subprocess

    def fake_run(*args, **kwargs):
        raise FileNotFoundError("git not on PATH")

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(GitError, match="git executable not found"):
        is_git_repository(".")


def test_git_timeout_raises_git_error(monkeypatch):
    import subprocess

    def fake_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=["git"], timeout=30)

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(GitError, match="timed out"):
        get_diff("HEAD~1..HEAD", cwd=".")
