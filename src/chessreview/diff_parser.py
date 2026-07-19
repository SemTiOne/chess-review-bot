"""Pure-text unified diff parsing. No git, no filesystem; testable standalone."""

from __future__ import annotations

import re
from dataclasses import dataclass

_DIFF_GIT_RE = re.compile(r"^diff --git a/(.*) b/(.*)$")
_HUNK_HEADER_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+\d+(?:,\d+)? @@")
_RENAME_FROM_RE = re.compile(r"^rename from (.*)$")
_RENAME_TO_RE = re.compile(r"^rename to (.*)$")

_TEST_PATH_SEGMENT_RE = re.compile(r"(?:^|/)(tests?|specs?)(?:/|$)", re.IGNORECASE)
_TEST_FILENAME_RE = re.compile(
    r"(^test_.*|.*_test\.[^/]+$|.*\.test\.[^/]+$|.*\.spec\.[^/]+$)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class DiffHunk:
    header: str
    added_lines: tuple[str, ...]
    removed_lines: tuple[str, ...]


@dataclass(frozen=True)
class DiffFile:
    path: str
    old_path: str | None
    is_new: bool
    is_deleted: bool
    is_renamed: bool
    is_binary: bool
    hunks: tuple[DiffHunk, ...]
    added_count: int
    removed_count: int


@dataclass(frozen=True)
class ParsedDiff:
    files: tuple[DiffFile, ...]


def is_test_file(path: str) -> bool:
    """Heuristic, case-insensitive, path-segment-aware test-file detector."""
    if not path:
        return False
    normalized = path.replace("\\", "/")
    filename = normalized.rsplit("/", 1)[-1]
    return bool(
        _TEST_PATH_SEGMENT_RE.search(normalized) or _TEST_FILENAME_RE.match(filename)
    )


class _FileBuilder:
    """Accumulates one file's diff block, finalized on the next `diff --git`
    line or end of input."""

    def __init__(self, new_path: str, old_path: str) -> None:
        self.new_path = new_path
        self.old_path = old_path
        self.is_new = False
        self.is_deleted = False
        self.is_renamed = False
        self.is_binary = False
        self.hunks: list[DiffHunk] = []
        self._current_header: str | None = None
        self._current_added: list[str] = []
        self._current_removed: list[str] = []

    def start_hunk(self, header: str) -> None:
        self._flush_hunk()
        self._current_header = header

    def add_line(self, line: str) -> None:
        if self._current_header is None:
            return  # content before any hunk header (shouldn't normally happen)
        self._current_added.append(line[1:])

    def remove_line(self, line: str) -> None:
        if self._current_header is None:
            return
        self._current_removed.append(line[1:])

    def _flush_hunk(self) -> None:
        if self._current_header is not None:
            self.hunks.append(
                DiffHunk(
                    header=self._current_header,
                    added_lines=tuple(self._current_added),
                    removed_lines=tuple(self._current_removed),
                )
            )
        self._current_header = None
        self._current_added = []
        self._current_removed = []

    def build(self) -> DiffFile:
        self._flush_hunk()
        added_count = sum(len(h.added_lines) for h in self.hunks)
        removed_count = sum(len(h.removed_lines) for h in self.hunks)
        display_path = self.new_path if not self.is_deleted else self.old_path
        old_path = (
            self.old_path
            if (self.is_renamed or self.old_path != self.new_path)
            else None
        )
        return DiffFile(
            path=display_path,
            old_path=old_path,
            is_new=self.is_new,
            is_deleted=self.is_deleted,
            is_renamed=self.is_renamed,
            is_binary=self.is_binary,
            hunks=tuple(self.hunks) if not self.is_binary else (),
            added_count=0 if self.is_binary else added_count,
            removed_count=0 if self.is_binary else removed_count,
        )


def parse_unified_diff(diff_text: str) -> ParsedDiff:
    """Parse unified diff text into a `ParsedDiff`.

    Never raises on malformed input. No `diff --git` lines -> `ParsedDiff(files=())`.
    """
    if not diff_text:
        return ParsedDiff(files=())

    files: list[DiffFile] = []
    builder: _FileBuilder | None = None

    lines = diff_text.splitlines()
    for line in lines:
        git_match = _DIFF_GIT_RE.match(line)
        if git_match:
            if builder is not None:
                files.append(builder.build())
            old_path, new_path = git_match.group(1), git_match.group(2)
            builder = _FileBuilder(new_path=new_path, old_path=old_path)
            continue

        if builder is None:
            # Content before the first `diff --git` line -- skip it.
            continue

        if line.startswith("new file mode"):
            builder.is_new = True
            continue
        if line.startswith("deleted file mode"):
            builder.is_deleted = True
            continue
        if _RENAME_FROM_RE.match(line) or _RENAME_TO_RE.match(line):
            builder.is_renamed = True
            continue
        if line.startswith("Binary files ") and line.endswith(" differ"):
            builder.is_binary = True
            continue
        if line.startswith("--- ") or line.startswith("+++ "):
            continue
        if _HUNK_HEADER_RE.match(line):
            builder.start_hunk(line)
            continue
        if builder.is_binary:
            continue
        if line.startswith("+"):
            builder.add_line(line)
        elif line.startswith("-"):
            builder.remove_line(line)
        # context lines and "\ No newline..." markers: ignored, no signal impact.

    if builder is not None:
        files.append(builder.build())

    return ParsedDiff(files=tuple(files))
