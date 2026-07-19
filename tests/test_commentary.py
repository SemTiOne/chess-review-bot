from __future__ import annotations

import builtins
import sys
import types
from unittest.mock import MagicMock

from chessreview.classifier import Category
from chessreview.commentary import CommentaryBudget, _build_prompt, generate_commentary
from chessreview.config import Config
from chessreview.signals import FileSignals


def _fs(**overrides) -> FileSignals:
    defaults = dict(
        path="src/foo.py",
        lines_added=5,
        lines_removed=2,
        net_lines=3,
        is_test_file=False,
        is_critical=False,
        secrets_detected=0,
        disables_tests=False,
        todo_fixme_added=0,
        is_dependency_lockfile=False,
        is_formatting_only=False,
    )
    defaults.update(overrides)
    return FileSignals(**defaults)


def _install_fake_genai(monkeypatch, response_text: str | None, raise_on_call: Exception | None = None):
    """Install a fake `google.genai` module tree into sys.modules and return
    the mock client class so call arguments can be inspected.
    """
    mock_response = MagicMock()
    mock_response.text = response_text

    mock_models = MagicMock()
    if raise_on_call is not None:
        mock_models.generate_content.side_effect = raise_on_call
    else:
        mock_models.generate_content.return_value = mock_response

    mock_client_instance = MagicMock()
    mock_client_instance.models = mock_models

    mock_client_class = MagicMock(return_value=mock_client_instance)

    fake_genai_module = types.ModuleType("google.genai")
    fake_genai_module.Client = mock_client_class

    fake_google_module = types.ModuleType("google")
    fake_google_module.genai = fake_genai_module

    monkeypatch.setitem(sys.modules, "google", fake_google_module)
    monkeypatch.setitem(sys.modules, "google.genai", fake_genai_module)
    return mock_client_class


# ---- disabled / no key / no SDK --------------------------------------------


def test_commentary_disabled_returns_fallback():
    config = Config(enable_commentary=False)
    text = generate_commentary(Category.BLUNDER, ("bad thing",), _fs(), config)
    assert text == "Blunder??: bad thing"


def test_commentary_no_key_returns_fallback():
    config = Config(enable_commentary=True, gemini_api_key=None)
    text = generate_commentary(Category.GOOD, (), _fs(), config)
    assert text == "Good"


def test_commentary_sdk_not_installed_falls_back(monkeypatch):
    real_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "google":
            raise ImportError("no genai installed")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    config = Config(enable_commentary=True, gemini_api_key="fake-key")
    text = generate_commentary(Category.MISTAKE, ("reason a",), _fs(), config)
    assert text == "Mistake?: reason a"


# ---- budget ------------------------------------------------------------------


def test_commentary_budget_exhausted_skips_call(monkeypatch):
    mock_client_class = _install_fake_genai(monkeypatch, response_text="should not be used")
    config = Config(enable_commentary=True, gemini_api_key="fake-key")
    budget = CommentaryBudget(max_calls=0)
    text = generate_commentary(Category.GOOD, ("ok",), _fs(), config, budget=budget)
    assert text == "Good: ok"
    mock_client_class.assert_not_called()
    assert budget.capped is True


# ---- success path -------------------------------------------------------------


def test_commentary_success_returns_model_text(monkeypatch):
    _install_fake_genai(monkeypatch, response_text="A quiet, correct little deletion.")
    config = Config(
        enable_commentary=True,
        gemini_api_key="fake-key",
        gemini_model="gemini-2.5-flash",
    )
    text = generate_commentary(Category.BRILLIANT, ("net deletion",), _fs(), config)
    assert text == "A quiet, correct little deletion."


def test_commentary_client_called_with_configured_model(monkeypatch):
    mock_client_class = _install_fake_genai(monkeypatch, response_text="Fine.")
    config = Config(enable_commentary=True, gemini_api_key="fake-key", gemini_model="gemini-3.5-flash")
    generate_commentary(Category.GOOD, (), _fs(), config)
    mock_client_class.assert_called_once_with(api_key="fake-key")
    instance = mock_client_class.return_value
    _, kwargs = instance.models.generate_content.call_args
    assert kwargs["model"] == "gemini-3.5-flash"


# ---- failure paths always fall back, never raise -------------------------------


def test_commentary_empty_response_falls_back(monkeypatch):
    _install_fake_genai(monkeypatch, response_text="")
    config = Config(enable_commentary=True, gemini_api_key="fake-key")
    text = generate_commentary(Category.INACCURACY, ("no context",), _fs(), config)
    assert text == "Inaccuracy?!: no context"


def test_commentary_none_response_falls_back(monkeypatch):
    _install_fake_genai(monkeypatch, response_text=None)
    config = Config(enable_commentary=True, gemini_api_key="fake-key")
    text = generate_commentary(Category.INACCURACY, ("no context",), _fs(), config)
    assert text == "Inaccuracy?!: no context"


def test_commentary_api_exception_falls_back(monkeypatch):
    _install_fake_genai(monkeypatch, response_text=None, raise_on_call=TimeoutError("slow"))
    config = Config(enable_commentary=True, gemini_api_key="fake-key")
    text = generate_commentary(Category.BLUNDER, ("secret detected",), _fs(), config)
    assert text == "Blunder??: secret detected"


# ---- prompt construction never leaks raw credentials ---------------------------


def test_prompt_redacts_credential_shaped_path():
    fs = _fs(path="config/api_key=sk_live_abc123.py")
    prompt = _build_prompt(Category.BLUNDER, ("credential detected",), fs)
    assert "sk_live_abc123" not in prompt
    assert "redacted" in prompt.lower()


def test_prompt_states_category_as_fixed_and_asks_for_one_sentence():
    fs = _fs()
    prompt = _build_prompt(Category.BOOK, ("routine change",), fs)
    assert "Book" in prompt
    assert "one sentence" in prompt
