"""Text, JSON, and Markdown (PR comment) rendering.

Consumes a `RunReport` built after classification/commentary already ran.
No renderer calls git, Gemini, or classifies anything.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone

from chessreview.classifier import Category

IDEMPOTENCY_MARKER = "<!-- chess-review-bot-managed-comment -->"

_ANSI_RESET = "\033[0m"
_CATEGORY_COLOR = {
    Category.BRILLIANT: "\033[96m",  # bright cyan
    Category.GREAT: "\033[92m",  # green
    Category.BEST: "\033[92m",
    Category.EXCELLENT: "\033[32m",
    Category.GOOD: "\033[37m",
    Category.BOOK: "\033[37m",
    Category.INACCURACY: "\033[93m",  # yellow
    Category.MISTAKE: "\033[33m",
    Category.MISS: "\033[33m",
    Category.BLUNDER: "\033[91m",  # red
}


@dataclass(frozen=True)
class FileReport:
    path: str
    category: Category
    reasons: tuple[str, ...]
    commentary: str
    lines_added: int
    lines_removed: int


@dataclass(frozen=True)
class RunReport:
    files: tuple[FileReport, ...]
    accuracy: float
    diff_range: str
    commentary_capped: bool = False

    @property
    def blunder_count(self) -> int:
        return sum(1 for f in self.files if f.category == Category.BLUNDER)

    @property
    def total_added(self) -> int:
        return sum(f.lines_added for f in self.files)

    @property
    def total_removed(self) -> int:
        return sum(f.lines_removed for f in self.files)

    @property
    def exit_code(self) -> int:
        return 1 if self.blunder_count > 0 else 0


def render_text(report: RunReport, use_color: bool = True, summary_only: bool = False) -> str:
    header = (
        f"chess-review-bot  {'-' * 44}\n"
        f"  Diff:        {report.diff_range}  ·  {len(report.files)} files"
        f"  ·  +{report.total_added} / -{report.total_removed} lines\n"
        f"  Accuracy:     {report.accuracy}/100\n"
        f"{'-' * 60}"
    )
    if summary_only:
        result_word = "FAIL" if report.exit_code else "PASS"
        return f"{header}\nResult: {result_word} ({report.blunder_count} Blunder)"

    lines = [header, ""]
    for f in report.files:
        color = _CATEGORY_COLOR.get(f.category, "") if use_color else ""
        reset = _ANSI_RESET if use_color else ""
        lines.append(f"  {f.path:<50} {color}{f.category.value}{reset}")
        for reason in f.reasons:
            lines.append(f"    -> {reason}")
        if f.commentary:
            lines.append(f'    -> "{f.commentary}"')
        lines.append("")

    lines.append("-" * 60)
    result_word = "FAIL" if report.exit_code else "PASS"
    lines.append(f"Result: {result_word} ({report.blunder_count} Blunder)  ·  Exit code: {report.exit_code}")
    if report.commentary_capped:
        lines.append("(commentary call limit reached for this run; remaining files use fallback text)")
    return "\n".join(lines)


def render_json(report: RunReport) -> str:
    payload = {
        "version": "1.0.0",
        "diff_range": report.diff_range,
        "accuracy": report.accuracy,
        "blunder_count": report.blunder_count,
        "total_files": len(report.files),
        "total_added": report.total_added,
        "total_removed": report.total_removed,
        "commentary_capped": report.commentary_capped,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "files": [
            {
                "path": f.path,
                "category": f.category.value,
                "reasons": list(f.reasons),
                "commentary": f.commentary,
                "lines_added": f.lines_added,
                "lines_removed": f.lines_removed,
            }
            for f in report.files
        ],
    }
    return json.dumps(payload, indent=2)


def render_markdown(report: RunReport) -> str:
    lines = [
        "### \u265f\ufe0f chess-review-bot \u2014 PR Game Review",
        "",
        f"**Accuracy: {report.accuracy}/100** \u00b7 {len(report.files)} files \u00b7 "
        f"+{report.total_added}/-{report.total_removed} \u00b7 {report.blunder_count} Blunder??",
        "",
        "| File | Category | Why |",
        "|---|---|---|",
    ]
    for f in report.files:
        why = f.reasons[0] if f.reasons else f.commentary or "\u2014"
        lines.append(f"| `{f.path}` | {f.category.value} | {why} |")

    lines.append("")
    lines.append(
        "_chess-review-bot scores diffs, not people. "
        "Run `chessreview --format text` locally for the full report._"
    )
    if report.commentary_capped:
        lines.append("")
        lines.append("_Commentary call limit reached for this run._")
    lines.append("")
    lines.append(IDEMPOTENCY_MARKER)
    return "\n".join(lines)


def render(report: RunReport, output_format: str, use_color: bool = True, summary_only: bool = False) -> str:
    if output_format == "json":
        return render_json(report)
    if output_format == "markdown":
        return render_markdown(report)
    return render_text(report, use_color=use_color, summary_only=summary_only)
