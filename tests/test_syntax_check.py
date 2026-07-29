from __future__ import annotations

from chessreview.diff_parser import DiffFile
from chessreview.syntax_check import file_fails_to_parse


def _df(path="src/foo.py", is_binary=False, is_deleted=False) -> DiffFile:
    return DiffFile(
        path=path,
        old_path=None,
        is_new=False,
        is_deleted=is_deleted,
        is_renamed=False,
        is_binary=is_binary,
        hunks=(),
        added_count=1,
        removed_count=1,
    )


def test_valid_python_returns_false(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "foo.py").write_text("x = 1\n")

    assert file_fails_to_parse(_df(), str(tmp_path)) is False


def test_invalid_python_returns_true(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "foo.py").write_text(
        'parser.add_argument(\n    "--env", chess review bot\n)\n'
    )

    assert file_fails_to_parse(_df(), str(tmp_path)) is True


def test_non_python_file_is_not_checked(tmp_path):
    (tmp_path / "foo.js").write_text("this is not { valid javascript at all(")

    assert file_fails_to_parse(_df(path="foo.js"), str(tmp_path)) is None


def test_binary_file_is_not_checked(tmp_path):
    assert file_fails_to_parse(_df(is_binary=True), str(tmp_path)) is None


def test_deleted_file_is_not_checked(tmp_path):
    assert file_fails_to_parse(_df(is_deleted=True), str(tmp_path)) is None


def test_no_repo_root_is_not_checked():
    assert file_fails_to_parse(_df(), None) is None


def test_missing_file_on_disk_is_not_checked(tmp_path):
    assert file_fails_to_parse(_df(path="src/does_not_exist.py"), str(tmp_path)) is None
