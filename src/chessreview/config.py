"""Config dataclass, built once in cli.py/entrypoint.py, threaded everywhere else."""

from __future__ import annotations

from dataclasses import dataclass, field

DEFAULT_CRITICAL_PATTERNS: tuple[str, ...] = (
    "*auth*",
    "*payment*",
    "*billing*",
    "*/migrations/*",
    "*.env*",
    "*secret*",
    "*/security/*",
    "*/settings/*prod*",
)
# api_key = "sk_live_FAKE_DEMO_KEY_DO_NOT_USE_123456"
DEFAULT_LOCKFILE_NAMES: tuple[str, ...] = (
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "poetry.lock",
    "Pipfile.lock",
    "Cargo.lock",
    "go.sum",
    "Gemfile.lock",
)

DEFAULT_MANIFEST_NAMES: tuple[str, ...] = (
    "package.json",
    "pyproject.toml",
    "Gemfile",
    "go.mod",
)

# Whole-message match (after stripping) -> "vague" regardless of length.
VAGUE_MESSAGE_DENYLIST: tuple[str, ...] = (
    "wip",
    "fix",
    "update",
    "updates",
    "stuff",
    "asdf",
    ".",
    "misc",
    "changes",
    "tmp",
)

# Substring markers -> "hostile". Blunt heuristic, not sentiment analysis.
# No "!!!": false-positives on enthusiastic-but-not-frustrated messages.
HOSTILE_MESSAGE_MARKERS: tuple[str, ...] = (
    "again",
    "ugh",
    "stupid",
    "wtf",
    "why is this",
    "hate this",
    "omg why",
)

DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"


@dataclass
class Config:
    """All tunables for a single chess-review-bot run."""

    critical_patterns: tuple[str, ...] = field(
        default_factory=lambda: DEFAULT_CRITICAL_PATTERNS
    )
    large_threshold: int = 400
    moderate_threshold: int = 100

    enable_commentary: bool = False
    gemini_api_key: str | None = None
    gemini_model: str = DEFAULT_GEMINI_MODEL
    max_commentary_calls_per_run: int = 30
    commentary_timeout_seconds: int = 10

    output_format: str = "text"  # "text" | "json" | "markdown"
    use_color: bool = True
    summary_only: bool = False
    debug: bool = False

    # For local CLI testing. Action mode derives these itself instead.
    force_pushed_override: bool = False
    revert_override: bool = False

    def __post_init__(self) -> None:
        if self.moderate_threshold < 0 or self.large_threshold < 0:
            raise ValueError("thresholds must be non-negative")
        if self.moderate_threshold > self.large_threshold:
            raise ValueError(
                "moderate_threshold must be <= large_threshold "
                f"(got moderate={self.moderate_threshold}, large={self.large_threshold})"
            )
        if self.max_commentary_calls_per_run < 0:
            raise ValueError("max_commentary_calls_per_run must be non-negative")
