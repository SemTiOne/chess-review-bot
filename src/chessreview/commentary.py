"""Optional one-line commentary.

classifier.py always decides the category first; this module only phrases
it, never changes it. Any failure (disabled, no key, no SDK, timeout, empty
response) falls back to a deterministic string. Exit code never depends on
this succeeding.
"""

from __future__ import annotations

from chessreview.classifier import Category
from chessreview.config import Config
from chessreview.redaction import redact_credentials, sanitize_text
from chessreview.signals import FileSignals

MAX_COMMENTARY_WORDS = 25


class CommentaryBudget:
    """Caps Gemini calls per run so a huge PR can't blow up the bill."""

    def __init__(self, max_calls: int) -> None:
        self.max_calls = max_calls
        self.calls_made = 0
        self.capped = False

    def try_reserve(self) -> bool:
        if self.calls_made >= self.max_calls:
            self.capped = True
            return False
        self.calls_made += 1
        return True


def _fallback_commentary(category: Category, reasons: tuple[str, ...]) -> str:
    if reasons:
        return f"{category.value}: " + "; ".join(reasons)
    return category.value


def _build_prompt(
    category: Category, reasons: tuple[str, ...], file_signals: FileSignals
) -> str:
    reason_text = "; ".join(reasons) if reasons else "no notable signals"
    # Defense in depth: redact path before it hits a third-party prompt.
    safe_path, _ = redact_credentials(file_signals.path)
    return (
        "You are a chess.com-style commentator, but the 'move' you are describing "
        "is a code change, not a chess move. The category below is ALREADY DECIDED "
        "and fixed — do not suggest or imply a different one, and do not invent any "
        "fact about the code that is not listed here.\n"
        f"File: {safe_path}\n"
        f"Category: {category.value}\n"
        f"Reason(s): {reason_text}\n"
        f"Diff size: +{file_signals.lines_added}/-{file_signals.lines_removed} lines\n"
        f"Write exactly one sentence, under {MAX_COMMENTARY_WORDS} words, in a dry, "
        "deadpan chess-commentator tone. Do not use the words 'AI' or 'code review'. "
        "Do not restate the category name verbatim."
    )


def generate_commentary(
    category: Category,
    reasons: tuple[str, ...],
    file_signals: FileSignals,
    config: Config,
    budget: CommentaryBudget | None = None,
) -> str:
    """One-line commentary string. Never raises."""
    if not config.enable_commentary or not config.gemini_api_key:
        return _fallback_commentary(category, reasons)

    if budget is not None and not budget.try_reserve():
        return _fallback_commentary(category, reasons)

    try:
        from google import genai  # imported lazily: optional dependency
    except ImportError:
        return _fallback_commentary(category, reasons)

    prompt = _build_prompt(category, reasons, file_signals)

    try:
        client = genai.Client(api_key=config.gemini_api_key)
        response = client.models.generate_content(
            model=config.gemini_model,
            contents=prompt,
        )
        text = sanitize_text(getattr(response, "text", "") or "")
    except Exception:  # noqa: BLE001 - any SDK/network/timeout failure falls back safely
        return _fallback_commentary(category, reasons)

    if not text:
        return _fallback_commentary(category, reasons)

    redacted_text, _ = redact_credentials(text)
    return redacted_text
