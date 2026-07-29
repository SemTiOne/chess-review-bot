"""Best-effort "does this file even parse" check.

Deliberately narrow and conservative: only checks languages we can verify
with the standard library alone (currently just Python, via ``ast.parse``),
against the actual post-change file content on disk in the local checkout
``gitutil.py`` already operates in.

Returns ``None`` ("unknown / not checked") rather than guessing whenever
we can't be confident: binary files, deleted files, unsupported languages,
or a missing/unreadable file on disk (e.g. when chess-review-bot is run
against a standalone diff file or stdin, outside of a real git checkout,
where there's nothing on disk to read at all). ``None`` must never be
treated as "fails to parse" by callers.
"""

from __future__ import annotations

import ast
import os

from chessreview.diff_parser import DiffFile

_PYTHON_EXTENSIONS = (".py", ".pyi")


def file_fails_to_parse(file: DiffFile, repo_root: str | None) -> bool | None:
    """Does ``file`` fail to parse as valid source, after this diff?

    Returns:
        True if the file is confirmed syntactically invalid.
        False if it's confirmed valid.
        None if we can't check it (see module docstring), never treat
        this as a pass or a fail.
    """
    if file.is_binary or file.is_deleted:
        return None
    if repo_root is None:
        return None
    if not file.path.lower().endswith(_PYTHON_EXTENSIONS):
        return None

    full_path = os.path.join(repo_root, file.path)
    try:
        with open(full_path, "r", encoding="utf-8", errors="replace") as fh:
            source = fh.read()
    except OSError:
        return None

    try:
        ast.parse(source, filename=file.path)
    except SyntaxError:
        return True
    return False
