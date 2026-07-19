"""CLI entry point: `chessreview` / `python -m chessreview`.

diff -> parse -> signals -> classify -> commentary (optional) -> render -> exit code.
Only module besides entrypoint.py that reads argv/env directly.
"""

from __future__ import annotations

import argparse
import os
import sys

from chessreview import __version__
from chessreview.classifier import classify_file, compute_accuracy
from chessreview.commentary import CommentaryBudget, generate_commentary
from chessreview.config import DEFAULT_CRITICAL_PATTERNS, DEFAULT_GEMINI_MODEL, Config
from chessreview.diff_parser import parse_unified_diff
from chessreview.gitutil import GitError, get_commit_messages, get_diff, is_git_repository
from chessreview.reporter import FileReport, RunReport, render
from chessreview.signals import GitContext, extract_pr_signals

EXIT_OK = 0
EXIT_BLUNDER = 1
EXIT_ERROR = 2


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="chessreview",
        description="Classify a git diff using chess.com-style move categories.",
    )
    parser.add_argument(
        "diff_source",
        nargs="?",
        default="HEAD~1..HEAD",
        help='Git ref range (e.g. "HEAD~1..HEAD"), a path to a diff file, or '
        '"-" to read a diff from stdin. Default: "HEAD~1..HEAD".',
    )
    parser.add_argument("--critical", action="append", default=[], metavar="PATTERN")
    parser.add_argument("--only-critical", action="append", default=[], metavar="PATTERN")
    parser.add_argument("--large-threshold", type=int, default=400)
    parser.add_argument("--moderate-threshold", type=int, default=100)
    parser.add_argument("--force-pushed", action="store_true")
    parser.add_argument("--revert", action="store_true")
    parser.add_argument("--enable-commentary", action="store_true")
    parser.add_argument("--gemini-key", default=None)
    parser.add_argument("--gemini-model", default=DEFAULT_GEMINI_MODEL)
    parser.add_argument("--max-commentary-calls", type=int, default=30)
    parser.add_argument(
        "--format", choices=["text", "json", "markdown"], default="text"
    )
    parser.add_argument("--no-color", action="store_true")
    parser.add_argument("--summary", action="store_true")
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--version", action="store_true")
    return parser


def _read_diff_text(diff_source: str) -> tuple[str, tuple[str, ...]]:
    """Return (diff_text, commit_messages). Raises GitError/OSError on failure."""
    if diff_source == "-":
        return sys.stdin.read(), ()
    if os.path.isfile(diff_source):
        with open(diff_source, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read(), ()
    # Otherwise treat it as a git ref range.
    if not is_git_repository():
        raise GitError(
            f"{diff_source!r} is not a file and this is not a git repository"
        )
    diff_text = get_diff(diff_source)
    messages = get_commit_messages(diff_source)
    return diff_text, messages


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    if args.version:
        print(f"chessreview {__version__}")
        return EXIT_OK

    try:
        config = Config(
            critical_patterns=tuple(args.only_critical)
            if args.only_critical
            else tuple(args.critical) or DEFAULT_CRITICAL_PATTERNS,
            large_threshold=args.large_threshold,
            moderate_threshold=args.moderate_threshold,
            enable_commentary=args.enable_commentary,
            gemini_api_key=args.gemini_key or os.environ.get("GEMINI_API_KEY"),
            gemini_model=args.gemini_model,
            max_commentary_calls_per_run=args.max_commentary_calls,
            output_format=args.format,
            use_color=not args.no_color,
            summary_only=args.summary,
            debug=args.debug,
            force_pushed_override=args.force_pushed,
            revert_override=args.revert,
        )
    except ValueError as exc:
        print(f"chessreview: invalid configuration: {exc}", file=sys.stderr)
        return EXIT_ERROR

    try:
        diff_text, commit_messages = _read_diff_text(args.diff_source)
    except (GitError, OSError) as exc:
        print(f"chessreview: {exc}", file=sys.stderr)
        return EXIT_ERROR

    parsed = parse_unified_diff(diff_text)
    git_ctx = GitContext(
        commit_messages=commit_messages,
        force_pushed=config.force_pushed_override,
        is_revert=config.revert_override,
    )
    pr_signals = extract_pr_signals(parsed, git_ctx, config)

    budget = CommentaryBudget(config.max_commentary_calls_per_run)
    file_reports: list[FileReport] = []
    line_weights: list[int] = []
    classifications = []

    for file_signals in pr_signals.files:
        classification = classify_file(file_signals, pr_signals, config)
        classifications.append(classification)
        commentary = generate_commentary(
            classification.category,
            classification.reasons,
            file_signals,
            config,
            budget=budget,
        )
        file_reports.append(
            FileReport(
                path=file_signals.path,
                category=classification.category,
                reasons=classification.reasons,
                commentary=commentary if config.enable_commentary else "",
                lines_added=file_signals.lines_added,
                lines_removed=file_signals.lines_removed,
            )
        )
        line_weights.append(file_signals.lines_added + file_signals.lines_removed)

    accuracy = compute_accuracy(classifications, line_weights)
    report = RunReport(
        files=tuple(file_reports),
        accuracy=accuracy,
        diff_range=args.diff_source,
        commentary_capped=budget.capped,
    )

    output = render(
        report,
        output_format=config.output_format,
        use_color=config.use_color,
        summary_only=config.summary_only,
    )
    print(output)

    if args.debug:
        for fs, cls in zip(pr_signals.files, classifications):
            print(f"[debug] {fs.path}: {fs} -> {cls}", file=sys.stderr)

    return report.exit_code


if __name__ == "__main__":
    sys.exit(main())
