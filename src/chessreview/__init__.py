"""chess-review-bot: classifies git diffs using chess.com-style move categories.

Category is always decided by deterministic signals (classifier.py), never by
the LLM. commentary.py only phrases an already-decided category.
"""

from __future__ import annotations

__version__ = "0.1.0"
