"""chess-review-bot: classifies git diffs using chess.com-style move categories.

Category is always decided by deterministic signals (classifier.py), never by
the LLM. commentary.py only phrases an already-decided category.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version


def _installed_version() -> str:
    try:
        return version("chess-review-bot")
    except PackageNotFoundError:
        return "0.0.0+local"


__version__ = _installed_version()
