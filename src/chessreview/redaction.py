"""Credential redaction and text sanitizing.

Same pattern family as the author's other tools (env-var auditors, stale-
annotation scanners); a credential redacted in one is redacted in all.
Every string from diff content, file content, or commit messages must pass
through `redact_credentials` before hitting terminal, JSON, Markdown, or an
LLM prompt.
"""

from __future__ import annotations

import re
import unicodedata

REDACTION_MARKER = "[content redacted: possible credential detected]"

_CREDENTIAL_PATTERN = re.compile(
    r"(?:key|token|password|secret|api_key|auth|bearer|credentials)\s*[=:]\s*(\S+)"
    r"|\bbearer\s+(\S+)",
    re.IGNORECASE,
)

_SAFE_REFERENCE_RE = re.compile(
    r"^(os\.environ|os\.getenv\(|getenv\(|process\.env|config\[|config\.get\(|settings\.)",
    re.IGNORECASE,
)

_ANSI_PATTERN = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")
_CONTROL_CHAR_PATTERN = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def _matches_credential(text: str) -> bool:
    for match in _CREDENTIAL_PATTERN.finditer(text):
        value = match.group(1) or match.group(2) or ""
        if not _SAFE_REFERENCE_RE.match(value):
            return True
    return False


def contains_credential(text: str) -> bool:
    """True if `text` matches a credential-shaped pattern."""
    return _matches_credential(text)


def redact_credentials(text: str) -> tuple[str, bool]:
    """Redact `text` if credential-shaped. Returns (text, was_redacted)."""
    if not text:
        return text, False
    if _matches_credential(text):
        return REDACTION_MARKER, True
    return text, False


def redact_lines(lines: tuple[str, ...]) -> tuple[tuple[str, ...], int]:
    """Redact each line. Returns (redacted lines, count redacted)."""
    redacted: list[str] = []
    count = 0
    for line in lines:
        new_line, was_redacted = redact_credentials(line)
        redacted.append(new_line)
        if was_redacted:
            count += 1
    return tuple(redacted), count


def sanitize_text(text: str) -> str:
    """Strip ANSI/control chars, normalize Unicode."""
    if not text:
        return ""
    text = _ANSI_PATTERN.sub("", text)
    text = _CONTROL_CHAR_PATTERN.sub("", text)
    text = unicodedata.normalize("NFC", text)
    return text.strip()
