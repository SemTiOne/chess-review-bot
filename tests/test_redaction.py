from __future__ import annotations

from chessreview.redaction import (
    REDACTION_MARKER,
    contains_credential,
    redact_credentials,
    redact_lines,
    sanitize_text,
)


def test_contains_credential_true_cases():
    assert contains_credential("api_key=sk_live_abc123")
    assert contains_credential('password: "hunter2"')
    assert contains_credential("Authorization: Bearer abc.def.ghi")
    assert contains_credential("SECRET=topsecret")


def test_redact_credentials_bearer_header_full_redaction():
    text, redacted = redact_credentials("Authorization: Bearer sk-live-abc123xyz")
    assert redacted is True
    assert "sk-live-abc123xyz" not in text


def test_contains_credential_false_cases():
    assert not contains_credential("def foo(): return 1")
    assert not contains_credential("this is a normal comment about a key concept")


# ---- safe reference exclusions ------------


def test_env_lookup_not_flagged_as_credential():
    assert not contains_credential('api_key = os.environ["OPENAI_API_KEY"]')
    assert not contains_credential('api_key = os.getenv("OPENAI_API_KEY")')


def test_config_dict_lookup_not_flagged_as_credential():
    assert not contains_credential('api_key = config["OPENAI_API_KEY"]')


def test_settings_attribute_not_flagged_as_credential():
    assert not contains_credential("SECRET_KEY = settings.SECRET_KEY")


def test_actual_hardcoded_value_still_flagged_despite_safe_keyword():
    # Sanity check: the exclusion is prefix-specific, not a blanket pass for
    # any line containing "config" or "os" somewhere.
    assert contains_credential('api_key = "sk_live_abc123_hardcoded_for_real"')


def test_redact_credentials_replaces_full_content():
    text, redacted = redact_credentials("api_key=sk_live_abc123xyz")
    assert redacted is True
    assert text == REDACTION_MARKER
    assert "sk_live_abc123xyz" not in text


def test_redact_credentials_passthrough():
    text, redacted = redact_credentials("def foo(): return 1")
    assert redacted is False
    assert text == "def foo(): return 1"


def test_redact_credentials_empty_string():
    text, redacted = redact_credentials("")
    assert redacted is False
    assert text == ""


def test_redact_lines_counts_redactions():
    lines = ("normal line", "token=abc123", "another normal line", "password: xyz")
    redacted, count = redact_lines(lines)
    assert count == 2
    assert redacted[0] == "normal line"
    assert redacted[1] == REDACTION_MARKER
    assert redacted[3] == REDACTION_MARKER


def test_sanitize_text_strips_ansi():
    text = "\x1b[31mred text\x1b[0m"
    assert sanitize_text(text) == "red text"


def test_sanitize_text_strips_control_chars():
    text = "hello\x00world\x0bfoo"
    assert "\x00" not in sanitize_text(text)
    assert "\x0b" not in sanitize_text(text)


def test_sanitize_text_empty():
    assert sanitize_text("") == ""
