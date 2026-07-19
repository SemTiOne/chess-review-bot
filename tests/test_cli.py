from __future__ import annotations

import json

import pytest

from chessreview.cli import EXIT_BLUNDER, EXIT_ERROR, EXIT_OK, main

GOOD_DIFF = """\
diff --git a/tests/test_foo.py b/tests/test_foo.py
index abc123..def456 100644
--- a/tests/test_foo.py
+++ b/tests/test_foo.py
@@ -1,2 +1,3 @@
 def test_foo():
     assert foo() == 1
+    assert foo() == 1
"""

SECRET_DIFF = """\
diff --git a/src/config.py b/src/config.py
index abc123..def456 100644
--- a/src/config.py
+++ b/src/config.py
@@ -1,1 +1,2 @@
 x = 1
+api_key = "sk_live_abcdefgh12345"
"""


def _write_diff(tmp_path, text: str, name: str = "change.diff"):
    diff_path = tmp_path / name
    diff_path.write_text(text, encoding="utf-8")
    return str(diff_path)


def test_cli_exit_ok_for_clean_diff(tmp_path, capsys):
    diff_file = _write_diff(tmp_path, GOOD_DIFF)
    exit_code = main([diff_file, "--format", "text"])
    assert exit_code == EXIT_OK
    out = capsys.readouterr().out
    assert "PASS" in out


def test_cli_exit_blunder_for_secret_diff(tmp_path, capsys):
    diff_file = _write_diff(tmp_path, SECRET_DIFF)
    exit_code = main([diff_file, "--format", "text"])
    assert exit_code == EXIT_BLUNDER
    out = capsys.readouterr().out
    assert "Blunder??" in out


def test_cli_format_json_is_valid(tmp_path, capsys):
    diff_file = _write_diff(tmp_path, GOOD_DIFF)
    main([diff_file, "--format", "json"])
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert "accuracy" in payload
    assert isinstance(payload["files"], list)


def test_cli_format_markdown_contains_marker(tmp_path, capsys):
    diff_file = _write_diff(tmp_path, GOOD_DIFF)
    main([diff_file, "--format", "markdown"])
    out = capsys.readouterr().out
    assert "chess-review-bot-managed-comment" in out


def test_cli_stdin_mode(tmp_path, capsys, monkeypatch):
    import io

    monkeypatch.setattr("sys.stdin", io.StringIO(GOOD_DIFF))
    exit_code = main(["-", "--format", "text"])
    assert exit_code == EXIT_OK


def test_cli_invalid_threshold_config_exits_error(tmp_path, capsys):
    diff_file = _write_diff(tmp_path, GOOD_DIFF)
    exit_code = main(
        [diff_file, "--large-threshold", "10", "--moderate-threshold", "500"]
    )
    assert exit_code == EXIT_ERROR
    err = capsys.readouterr().err
    assert "invalid configuration" in err


def test_cli_missing_diff_file_and_not_a_repo_exits_error(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)  # tmp_path is not a git repo
    exit_code = main(["/nonexistent/path/does-not-exist.diff"])
    assert exit_code == EXIT_ERROR
    err = capsys.readouterr().err
    assert "chessreview:" in err


def test_cli_version_flag(capsys):
    exit_code = main(["--version"])
    assert exit_code == EXIT_OK
    out = capsys.readouterr().out
    assert "chessreview" in out


def test_cli_gemini_key_never_appears_in_output(tmp_path, capsys):
    diff_file = _write_diff(tmp_path, GOOD_DIFF)
    secret_key = "sk-super-secret-gemini-key-98765"
    main([diff_file, "--gemini-key", secret_key, "--format", "json"])
    captured = capsys.readouterr()
    assert secret_key not in captured.out
    assert secret_key not in captured.err


def test_cli_critical_override_flags_file_as_blunder(tmp_path, capsys):
    diff_text = """\
diff --git a/src/utils/formatting.py b/src/utils/formatting.py
index abc123..def456 100644
--- a/src/utils/formatting.py
+++ b/src/utils/formatting.py
@@ -1,1 +1,2 @@
 x = 1
+y = 2
"""
    diff_file = _write_diff(tmp_path, diff_text)
    exit_code = main(
        [diff_file, "--only-critical", "*formatting*", "--format", "text"]
    )
    # Critical path, zero tests changed anywhere, and no commit message
    # (diff-file mode has no commit messages) -> empty quality -> Blunder.
    assert exit_code == EXIT_BLUNDER


def test_cli_debug_flag_prints_signal_dump_to_stderr(tmp_path, capsys):
    diff_file = _write_diff(tmp_path, GOOD_DIFF)
    main([diff_file, "--format", "text", "--debug"])
    err = capsys.readouterr().err
    assert "[debug]" in err
    assert "tests/test_foo.py" in err
