from __future__ import annotations

from chessreview.config import Config
from chessreview.diff_parser import DiffFile, DiffHunk, ParsedDiff
from chessreview.signals import (
    GitContext,
    classify_commit_message_quality,
    extract_file_signals,
    extract_pr_signals,
)


def _file(path: str, hunks: tuple[DiffHunk, ...] = (), **overrides) -> DiffFile:
    added = sum(len(h.added_lines) for h in hunks)
    removed = sum(len(h.removed_lines) for h in hunks)
    defaults = dict(
        path=path,
        old_path=None,
        is_new=False,
        is_deleted=False,
        is_renamed=False,
        is_binary=False,
        hunks=hunks,
        added_count=added,
        removed_count=removed,
    )
    defaults.update(overrides)
    return DiffFile(**defaults)


def _hunk(added: tuple[str, ...] = (), removed: tuple[str, ...] = ()) -> DiffHunk:
    return DiffHunk(header="@@ -1,1 +1,1 @@", added_lines=added, removed_lines=removed)


# ---- commit message quality ----------------------------------------------


def test_commit_message_empty():
    assert classify_commit_message_quality(()) == "empty"
    assert classify_commit_message_quality(("   ",)) == "empty"


def test_commit_message_vague_short():
    assert classify_commit_message_quality(("fix",)) == "vague"
    assert classify_commit_message_quality(("wip",)) == "vague"


def test_commit_message_hostile():
    assert classify_commit_message_quality(("fix stupid bug AGAIN",)) == "hostile"
    assert classify_commit_message_quality(("ugh, why is this broken",)) == "hostile"


def test_commit_message_good():
    assert (
        classify_commit_message_quality(
            ("Add session refresh handling for expired tokens",)
        )
        == "good"
    )


# ---- critical path matching ------------------------------------------------


def test_critical_path_matches_auth():
    config = Config()
    f = _file("src/auth/session.py")
    signals = extract_file_signals(f, config)
    assert signals.is_critical is True


def test_critical_path_does_not_match_unrelated_file():
    config = Config()
    f = _file("src/utils/formatting.py")
    signals = extract_file_signals(f, config)
    assert signals.is_critical is False


def test_critical_path_binary_file_never_critical():
    config = Config()
    f = _file("secrets/keyfile.bin", is_binary=True)
    signals = extract_file_signals(f, config)
    assert signals.is_critical is False


# ---- dependency lockfile detection -----------------------------------------


def test_lockfile_detected_by_name():
    config = Config()
    f = _file("package-lock.json", hunks=(_hunk(added=('"foo": "1.2.3"',)),))
    signals = extract_file_signals(f, config)
    assert signals.is_dependency_lockfile is True


def test_manifest_with_only_version_lines_detected_as_lockfile():
    config = Config()
    f = _file(
        "package.json",
        hunks=(
            _hunk(
                added=('  "lodash": "^4.17.21"',),
                removed=('  "lodash": "^4.17.20"',),
            ),
        ),
    )
    signals = extract_file_signals(f, config)
    assert signals.is_dependency_lockfile is True


def test_manifest_with_non_version_changes_not_lockfile():
    config = Config()
    f = _file(
        "package.json",
        hunks=(_hunk(added=('  "scripts": { "start": "node index.js" }',)),),
    )
    signals = extract_file_signals(f, config)
    assert signals.is_dependency_lockfile is False


# ---- formatting-only detection ---------------------------------------------


def test_formatting_only_true_when_content_matches_after_stripping():
    config = Config()
    f = _file(
        "src/foo.py",
        hunks=(
            _hunk(
                added=("    return 1",),
                removed=("return 1",),
            ),
        ),
    )
    signals = extract_file_signals(f, config)
    assert signals.is_formatting_only is True


def test_formatting_only_false_when_content_actually_changes():
    config = Config()
    f = _file(
        "src/foo.py",
        hunks=(_hunk(added=("return 2",), removed=("return 1",)),),
    )
    signals = extract_file_signals(f, config)
    assert signals.is_formatting_only is False


def test_formatting_only_false_when_no_hunks():
    config = Config()
    f = _file("src/foo.py", is_renamed=True)
    signals = extract_file_signals(f, config)
    assert signals.is_formatting_only is False


# ---- secrets and TODO/FIXME detection --------------------------------------


def test_secrets_detected_counts_added_lines_only():
    config = Config()
    f = _file(
        "src/config.py",
        hunks=(
            _hunk(
                added=("api_key='sk_live_abc'", "normal_line = 1"),
                removed=("password='old_removed_value'",),
            ),
        ),
    )
    signals = extract_file_signals(f, config)
    assert signals.secrets_detected == 1  # only the added line counts


def test_todo_fixme_counted():
    config = Config()
    f = _file(
        "src/foo.py",
        hunks=(_hunk(added=("# TODO: handle edge case", "# FIXME: this is broken")),),
    )
    signals = extract_file_signals(f, config)
    assert signals.todo_fixme_added == 2


# ---- test-disable detection -------------------------------------------------


def test_disables_tests_detects_skip_decorator():
    config = Config()
    f = _file(
        "tests/test_foo.py",
        hunks=(_hunk(added=("@pytest.mark.skip(reason='flaky')",)),),
    )
    signals = extract_file_signals(f, config)
    assert signals.disables_tests is True


def test_disables_tests_detects_commented_assert():
    config = Config()
    f = _file(
        "tests/test_foo.py",
        hunks=(_hunk(added=("# assert result == expected",)),),
    )
    signals = extract_file_signals(f, config)
    assert signals.disables_tests is True


def test_disables_tests_false_when_no_markers():
    config = Config()
    f = _file(
        "tests/test_foo.py",
        hunks=(_hunk(added=("assert result == expected",)),),
    )
    signals = extract_file_signals(f, config)
    assert signals.disables_tests is False


# ---- PR-level aggregation ---------------------------------------------------


def test_extract_pr_signals_aggregates_correctly():
    config = Config()
    diff = ParsedDiff(
        files=(
            _file("src/auth/session.py", hunks=(_hunk(added=("x = 1",)),)),
            _file("tests/test_session.py", hunks=(_hunk(added=("def test_x(): pass",)),)),
        )
    )
    git_ctx = GitContext(commit_messages=("Add session refresh handling",))
    pr_signals = extract_pr_signals(diff, git_ctx, config)
    assert pr_signals.total_files == 2
    assert pr_signals.test_files_changed == 1
    assert pr_signals.non_test_files_changed == 1
    assert pr_signals.commit_message_quality == "good"
    assert pr_signals.force_pushed is False
    assert pr_signals.is_revert is False


def test_extract_pr_signals_detects_revert_from_commit_message():
    config = Config()
    diff = ParsedDiff(files=(_file("src/foo.py", hunks=(_hunk(added=("x = 1",)),)),))
    git_ctx = GitContext(commit_messages=('Revert "Add risky feature"',))
    pr_signals = extract_pr_signals(diff, git_ctx, config)
    assert pr_signals.is_revert is True
