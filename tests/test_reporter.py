from __future__ import annotations

import json

from chessreview.classifier import Category
from chessreview.reporter import (
    IDEMPOTENCY_MARKER,
    FileReport,
    RunReport,
    render,
    render_json,
    render_markdown,
    render_text,
)


def _report(**overrides) -> RunReport:
    files = overrides.pop("files", (
        FileReport(
            path="src/auth/session.py",
            category=Category.BLUNDER,
            reasons=("critical path, no tests, no description",),
            commentary="",
            lines_added=120,
            lines_removed=4,
        ),
        FileReport(
            path="src/utils/formatting.py",
            category=Category.BOOK,
            reasons=("routine dependency or formatting-only change",),
            commentary="",
            lines_added=3,
            lines_removed=3,
        ),
    ))
    defaults = dict(files=files, accuracy=42.0, diff_range="HEAD~1..HEAD")
    defaults.update(overrides)
    return RunReport(**defaults)


def test_blunder_count_property():
    report = _report()
    assert report.blunder_count == 1


def test_exit_code_nonzero_when_blunder_present():
    report = _report()
    assert report.exit_code == 1


def test_exit_code_zero_when_no_blunder():
    files = (
        FileReport("src/foo.py", Category.GOOD, (), "", 5, 2),
    )
    report = _report(files=files)
    assert report.exit_code == 0


def test_totals_sum_across_files():
    report = _report()
    assert report.total_added == 123
    assert report.total_removed == 7


# ---- text rendering ---------------------------------------------------------


def test_render_text_contains_file_paths_and_categories():
    report = _report()
    text = render_text(report, use_color=False)
    assert "src/auth/session.py" in text
    assert "Blunder??" in text
    assert "Book" in text
    assert "FAIL" in text


def test_render_text_no_color_has_no_ansi_codes():
    report = _report()
    text = render_text(report, use_color=False)
    assert "\033[" not in text


def test_render_text_color_has_ansi_codes():
    report = _report()
    text = render_text(report, use_color=True)
    assert "\033[" in text


def test_render_text_summary_only_is_short():
    report = _report()
    text = render_text(report, use_color=False, summary_only=True)
    assert "src/auth/session.py" not in text
    assert "FAIL" in text


# ---- JSON rendering -----------------------------------------------------------


def test_render_json_is_valid_and_matches_schema():
    report = _report()
    payload = json.loads(render_json(report))
    assert payload["blunder_count"] == 1
    assert payload["accuracy"] == 42.0
    assert len(payload["files"]) == 2
    assert payload["files"][0]["category"] == "Blunder??"
    assert "generated_at" in payload


# ---- Markdown rendering ---------------------------------------------------------


def test_render_markdown_contains_idempotency_marker_exactly_once():
    report = _report()
    md = render_markdown(report)
    assert md.count(IDEMPOTENCY_MARKER) == 1


def test_render_markdown_contains_table_rows():
    report = _report()
    md = render_markdown(report)
    assert "| `src/auth/session.py` | Blunder?? |" in md
    assert "| `src/utils/formatting.py` | Book |" in md


# ---- render() dispatcher -----------------------------------------------------


def test_render_dispatches_to_json():
    report = _report()
    out = render(report, output_format="json")
    json.loads(out)  # valid JSON, would raise otherwise


def test_render_dispatches_to_markdown():
    report = _report()
    out = render(report, output_format="markdown")
    assert IDEMPOTENCY_MARKER in out


def test_render_dispatches_to_text_by_default():
    report = _report()
    out = render(report, output_format="text")
    assert "src/auth/session.py" in out


def test_render_unknown_format_falls_back_to_text():
    report = _report()
    out = render(report, output_format="something-unrecognized")
    assert "src/auth/session.py" in out
