"""Deterministic signal extraction. No LLM calls, no network ever.
classifier.py consumes only these signals, never the raw diff.
"""

from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass, field

from chessreview.config import (
    DEFAULT_LOCKFILE_NAMES,
    DEFAULT_MANIFEST_NAMES,
    HOSTILE_MESSAGE_MARKERS,
    VAGUE_MESSAGE_DENYLIST,
    Config,
)
from chessreview.diff_parser import DiffFile, ParsedDiff, is_test_file
from chessreview.redaction import contains_credential

_TODO_FIXME_RE = re.compile(r"\b(TODO|FIXME|XXX|HACK)\b")
_VERSION_LINE_RE = re.compile(r'^\s*"?[\w.@/-]+"?\s*[:=]\s*"?[\^~]?\d+\.\d+')
_TEST_DISABLE_RE = re.compile(
    r"(\.skip\(|@skip\b|xfail\b|it\.skip\(|describe\.skip\()"
)
# Note: `@pytest.mark.skip(...)` and `it.skip(`/`describe.skip(` all already
# contain the literal `.skip(` substring, so the first alternative alone
# covers them; `it\.skip\(`/`describe\.skip\(` are kept only as
# self-documenting anchors for JS test frameworks, not because they add
# matching power `\.skip\(` doesn't already have.
_COMMENTED_ASSERT_RE = re.compile(r"^\s*(#|//)\s*(assert|expect)\b")
_REVERT_COMMIT_RE = re.compile(r'^Revert\s+"', re.IGNORECASE)


@dataclass(frozen=True)
class GitContext:
    """Facts not derivable from the diff text alone."""

    commit_messages: tuple[str, ...] = ()
    force_pushed: bool = False
    is_revert: bool = False


@dataclass(frozen=True)
class FileSignals:
    path: str
    lines_added: int
    lines_removed: int
    net_lines: int
    is_test_file: bool
    is_critical: bool
    secrets_detected: int
    disables_tests: bool
    todo_fixme_added: int
    is_dependency_lockfile: bool
    is_formatting_only: bool


@dataclass(frozen=True)
class PRSignals:
    files: tuple[FileSignals, ...]
    total_files: int
    total_added: int
    total_removed: int
    test_files_changed: int
    non_test_files_changed: int
    commit_message_quality: str  # "good" | "vague" | "hostile" | "empty"
    force_pushed: bool
    is_revert: bool


def _matches_any(path: str, patterns: tuple[str, ...]) -> bool:
    return any(fnmatch.fnmatch(path, pattern) for pattern in patterns)


def _is_dependency_lockfile(file: DiffFile) -> bool:
    basename = file.path.replace("\\", "/").rsplit("/", 1)[-1]
    if basename in DEFAULT_LOCKFILE_NAMES:
        return True
    if basename in DEFAULT_MANIFEST_NAMES:
        all_lines = [
            line
            for hunk in file.hunks
            for line in (*hunk.added_lines, *hunk.removed_lines)
            if line.strip()
        ]
        if not all_lines:
            return False
        return all(_VERSION_LINE_RE.match(line) for line in all_lines)
    return False


def _is_formatting_only(file: DiffFile) -> bool:
    if not file.hunks:
        return False
    for hunk in file.hunks:
        if len(hunk.added_lines) != len(hunk.removed_lines):
            return False
        added_stripped = sorted(line.strip() for line in hunk.added_lines)
        removed_stripped = sorted(line.strip() for line in hunk.removed_lines)
        if added_stripped != removed_stripped:
            return False
    return True


def _count_secrets(file: DiffFile) -> int:
    return sum(
        1
        for hunk in file.hunks
        for line in hunk.added_lines
        if contains_credential(line)
    )


def _count_todo_fixme(file: DiffFile) -> int:
    return sum(
        1
        for hunk in file.hunks
        for line in hunk.added_lines
        if _TODO_FIXME_RE.search(line)
    )


def _disables_tests(file: DiffFile) -> bool:
    for hunk in file.hunks:
        for line in hunk.added_lines:
            if _TEST_DISABLE_RE.search(line):
                return True
            if _COMMENTED_ASSERT_RE.match(line):
                return True
    return False


def classify_commit_message_quality(messages: tuple[str, ...]) -> str:
    """"good" | "vague" | "hostile" | "empty". Denylist heuristic, not sentiment analysis."""
    joined = " ".join(m.strip() for m in messages if m.strip())
    if not joined:
        return "empty"
    lowered = joined.lower()
    for marker in HOSTILE_MESSAGE_MARKERS:
        if marker in lowered:
            return "hostile"
    stripped = joined.strip().rstrip(".!").lower()
    if len(joined.strip()) < 10 or stripped in VAGUE_MESSAGE_DENYLIST:
        return "vague"
    return "good"


def _is_revert_message(messages: tuple[str, ...]) -> bool:
    return any(_REVERT_COMMIT_RE.match(m) for m in messages)


def extract_file_signals(file: DiffFile, config: Config) -> FileSignals:
    """Deterministic signals for one file in the diff."""
    net_lines = file.added_count - file.removed_count
    return FileSignals(
        path=file.path,
        lines_added=file.added_count,
        lines_removed=file.removed_count,
        net_lines=net_lines,
        is_test_file=is_test_file(file.path),
        is_critical=_matches_any(file.path, config.critical_patterns) and not file.is_binary,
        secrets_detected=0 if file.is_binary else _count_secrets(file),
        disables_tests=False if file.is_binary else _disables_tests(file),
        todo_fixme_added=0 if file.is_binary else _count_todo_fixme(file),
        is_dependency_lockfile=_is_dependency_lockfile(file) if not file.is_binary else False,
        is_formatting_only=_is_formatting_only(file) if not file.is_binary else False,
    )


def extract_pr_signals(
    diff: ParsedDiff, git_ctx: GitContext, config: Config
) -> PRSignals:
    """Per-file signals + PR-level aggregates, one pass."""
    file_signals = tuple(extract_file_signals(f, config) for f in diff.files)

    test_files_changed = sum(1 for fs in file_signals if fs.is_test_file)
    non_test_files_changed = len(file_signals) - test_files_changed
    total_added = sum(fs.lines_added for fs in file_signals)
    total_removed = sum(fs.lines_removed for fs in file_signals)

    message_quality = classify_commit_message_quality(git_ctx.commit_messages)
    is_revert = git_ctx.is_revert or _is_revert_message(git_ctx.commit_messages)

    return PRSignals(
        files=file_signals,
        total_files=len(file_signals),
        total_added=total_added,
        total_removed=total_removed,
        test_files_changed=test_files_changed,
        non_test_files_changed=non_test_files_changed,
        commit_message_quality=message_quality,
        force_pushed=git_ctx.force_pushed,
        is_revert=is_revert,
    )
