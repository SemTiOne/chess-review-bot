from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ACTION_DIR = Path(__file__).resolve().parent.parent / "action"


def _load_entrypoint(monkeypatch):
    monkeypatch.syspath_prepend(str(ACTION_DIR))
    spec = importlib.util.spec_from_file_location(
        "entrypoint_under_test", ACTION_DIR / "entrypoint.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _payload(path: Path) -> str:
    payload = {
        "action": "opened",
        "pull_request": {
            "number": 10,
            "base": {"sha": "a" * 40},
            "head": {"sha": "b" * 40},
        },
    }
    event = path / "event.json"
    event.write_text(json.dumps(payload), encoding="utf-8")
    return str(event)


def _offline_git(monkeypatch, entrypoint):
    monkeypatch.setattr(entrypoint, "get_diff", lambda *a, **k: "")
    monkeypatch.setattr(entrypoint, "get_commit_messages", lambda *a, **k: ("x",))
    monkeypatch.setattr(entrypoint, "get_repo_root", lambda *a, **k: None)


def test_env_bool_parsing(monkeypatch):
    entrypoint = _load_entrypoint(monkeypatch)
    assert entrypoint._env_bool("MISSING_VAR_XYZ", True) is True
    assert entrypoint._env_bool("MISSING_VAR_XYZ", False) is False
    monkeypatch.setenv("CHESSREVIEW_TMP_BOOL", "yes")
    assert entrypoint._env_bool("CHESSREVIEW_TMP_BOOL", False) is True


def test_env_int_falls_back_on_garbage(monkeypatch):
    entrypoint = _load_entrypoint(monkeypatch)
    monkeypatch.setenv("CHESSREVIEW_TMP_INT", "not-a-number")
    assert entrypoint._env_int("CHESSREVIEW_TMP_INT", 400) == 400


def test_revert_env_wires_to_git_context(monkeypatch, tmp_path, capsys):
    entrypoint = _load_entrypoint(monkeypatch)
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    monkeypatch.setenv("GITHUB_EVENT_PATH", _payload(tmp_path))
    monkeypatch.setenv("CHESSREVIEW_REVERT", "true")
    monkeypatch.setenv("CHESSREVIEW_POST_COMMENT", "false")
    _offline_git(monkeypatch, entrypoint)

    seen = {}
    real_extract = entrypoint.extract_pr_signals

    def _spy(diff, git_ctx, config, repo_root=None):
        seen["ctx"] = git_ctx
        return real_extract(diff, git_ctx, config, repo_root)

    monkeypatch.setattr(entrypoint, "extract_pr_signals", _spy)
    assert entrypoint.main() == entrypoint.EXIT_OK
    assert seen["ctx"].is_revert is True
    capsys.readouterr()


def test_revert_defaults_to_false(monkeypatch, tmp_path, capsys):
    entrypoint = _load_entrypoint(monkeypatch)
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    monkeypatch.setenv("GITHUB_EVENT_PATH", _payload(tmp_path))
    monkeypatch.delenv("CHESSREVIEW_REVERT", raising=False)
    monkeypatch.setenv("CHESSREVIEW_POST_COMMENT", "false")
    _offline_git(monkeypatch, entrypoint)

    seen = {}
    real_extract = entrypoint.extract_pr_signals

    def _spy(diff, git_ctx, config, repo_root=None):
        seen["ctx"] = git_ctx
        return real_extract(diff, git_ctx, config, repo_root)

    monkeypatch.setattr(entrypoint, "extract_pr_signals", _spy)
    assert entrypoint.main() == entrypoint.EXIT_OK
    assert seen["ctx"].is_revert is False
    capsys.readouterr()
