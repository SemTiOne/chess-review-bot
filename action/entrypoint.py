"""GitHub Action entrypoint for chess-review-bot.

Reads event payload + env from `action.yml`, runs the same pipeline as the
CLI, posts/updates one PR comment, writes outputs, exits with status.

Force-push detection: `synchronize` events carry top-level `before`/`after`
SHAs (no `forced` field -- that's `push`-event only). Ancestry check via
`gitutil.is_ancestor`. Needs `fetch-depth: 0` in the caller's checkout.
"""

from __future__ import annotations

import json
import os
import sys

# Run directly (python action/entrypoint.py) against a checked-out source
# tree without pip-installing first.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from comment import GitHubApiError, upsert_comment  # noqa: E402

from chessreview.classifier import classify_file, compute_accuracy  # noqa: E402
from chessreview.commentary import CommentaryBudget, generate_commentary  # noqa: E402
from chessreview.config import DEFAULT_CRITICAL_PATTERNS, Config  # noqa: E402
from chessreview.diff_parser import parse_unified_diff  # noqa: E402
from chessreview.gitutil import (  # noqa: E402
    GitError,
    get_commit_messages,
    get_diff,
    is_ancestor,
)
from chessreview.reporter import (  # noqa: E402
    IDEMPOTENCY_MARKER,
    FileReport,
    RunReport,
    render_json,
    render_markdown,
)
from chessreview.signals import GitContext, extract_pr_signals  # noqa: E402

EXIT_OK = 0
EXIT_BLUNDER = 1
EXIT_ERROR = 2


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None or value == "":
        return default
    return value.strip().lower() in ("true", "1", "yes")


def _env_int(name: str, default: int) -> int:
    value = os.environ.get(name)
    if value is None or value == "":
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _load_event_payload() -> dict:
    event_path = os.environ.get("GITHUB_EVENT_PATH")
    if not event_path or not os.path.isfile(event_path):
        return {}
    with open(event_path, "r", encoding="utf-8", errors="replace") as fh:
        try:
            return json.load(fh)
        except json.JSONDecodeError:
            return {}


def _write_outputs(accuracy: float, blunder_count: int, result: str) -> None:
    output_path = os.environ.get("GITHUB_OUTPUT")
    if not output_path:
        return
    with open(output_path, "a", encoding="utf-8") as fh:
        fh.write(f"accuracy={accuracy}\n")
        fh.write(f"blunder-count={blunder_count}\n")
        fh.write(f"result={result}\n")


def main() -> int:
    token = os.environ.get("GITHUB_TOKEN")
    gemini_key = os.environ.get("GEMINI_API_KEY") or None
    critical_raw = os.environ.get("CHESSREVIEW_CRITICAL", "")
    only_critical_raw = os.environ.get("CHESSREVIEW_ONLY_CRITICAL", "")
    added_critical = tuple(p for p in critical_raw.splitlines() if p.strip())
    only_critical = tuple(p for p in only_critical_raw.splitlines() if p.strip())
    large_threshold = _env_int("CHESSREVIEW_LARGE_THRESHOLD", 400)
    moderate_threshold = _env_int("CHESSREVIEW_MODERATE_THRESHOLD", 100)
    fail_on_blunder = _env_bool("CHESSREVIEW_FAIL_ON_BLUNDER", True)
    post_comment = _env_bool("CHESSREVIEW_POST_COMMENT", True)

    if not token:
        print("chess-review-bot: GITHUB_TOKEN is required", file=sys.stderr)
        return EXIT_ERROR

    # only_critical replaces the defaults entirely; added_critical extends
    # them. Matches the CLI's --only-critical vs --critical split.
    if only_critical:
        critical_patterns = only_critical
    elif added_critical:
        critical_patterns = DEFAULT_CRITICAL_PATTERNS + added_critical
    else:
        critical_patterns = DEFAULT_CRITICAL_PATTERNS

    try:
        config = Config(
            critical_patterns=critical_patterns,
            large_threshold=large_threshold,
            moderate_threshold=moderate_threshold,
            enable_commentary=bool(gemini_key),
            gemini_api_key=gemini_key,
        )
    except ValueError as exc:
        print(f"chess-review-bot: invalid configuration: {exc}", file=sys.stderr)
        return EXIT_ERROR

    payload = _load_event_payload()
    pull_request = payload.get("pull_request") or {}
    pr_number = pull_request.get("number")
    base_sha = (pull_request.get("base") or {}).get("sha")
    head_sha = (pull_request.get("head") or {}).get("sha")

    # Force-push: before-still-ancestor-of-after == fast-forward. is_ancestor
    # returns None when undeterminable, which never counts as force-push.
    forced = False
    if payload.get("action") == "synchronize":
        before_sha = payload.get("before")
        after_sha = payload.get("after")
        ancestry = is_ancestor(before_sha, after_sha) if (before_sha and after_sha) else None
        forced = ancestry is False

    repository = os.environ.get("GITHUB_REPOSITORY", "")
    owner_repo = repository.split("/", 1) if "/" in repository else (None, None)
    owner, repo = owner_repo if len(owner_repo) == 2 else (None, None)

    if not (base_sha and head_sha):
        print(
            "chess-review-bot: could not determine base/head SHA from the event "
            "payload; is this running on a pull_request event?",
            file=sys.stderr,
        )
        return EXIT_ERROR

    ref_range = f"{base_sha}...{head_sha}"
    try:
        diff_text = get_diff(ref_range)
        commit_messages = get_commit_messages(ref_range)
    except GitError as exc:
        print(f"chess-review-bot: {exc}", file=sys.stderr)
        return EXIT_ERROR

    parsed = parse_unified_diff(diff_text)
    git_ctx = GitContext(
        commit_messages=commit_messages, force_pushed=forced, is_revert=False
    )
    pr_signals = extract_pr_signals(parsed, git_ctx, config)

    budget = CommentaryBudget(config.max_commentary_calls_per_run)
    file_reports = []
    line_weights = []
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
        diff_range=ref_range,
        commentary_capped=budget.capped,
    )

    print(render_json(report))

    result = "blunder" if report.blunder_count > 0 else "clean"
    _write_outputs(accuracy=accuracy, blunder_count=report.blunder_count, result=result)

    if post_comment and pr_number and owner and repo:
        try:
            upsert_comment(
                owner=owner,
                repo=repo,
                pr_number=pr_number,
                token=token,
                marker=IDEMPOTENCY_MARKER,
                body=render_markdown(report),
            )
        except GitHubApiError as exc:
            print(f"chess-review-bot: failed to post PR comment: {exc}", file=sys.stderr)

    if fail_on_blunder and report.blunder_count > 0:
        return EXIT_BLUNDER
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
