from __future__ import annotations

from chessreview.classifier import CATEGORY_WEIGHT, Category, classify_file, compute_accuracy
from chessreview.config import Config
from chessreview.signals import FileSignals, PRSignals


def _fs(**overrides) -> FileSignals:
    defaults = dict(
        path="src/foo.py",
        lines_added=5,
        lines_removed=2,
        net_lines=3,
        is_test_file=False,
        is_critical=False,
        secrets_detected=0,
        disables_tests=False,
        todo_fixme_added=0,
        is_dependency_lockfile=False,
        is_formatting_only=False,
    )
    defaults.update(overrides)
    return FileSignals(**defaults)


def _pr(files=(), **overrides) -> PRSignals:
    defaults = dict(
        files=files,
        total_files=max(len(files), 1),
        total_added=0,
        total_removed=0,
        test_files_changed=1,
        non_test_files_changed=0,
        commit_message_quality="good",
        force_pushed=False,
        is_revert=False,
    )
    defaults.update(overrides)
    return PRSignals(**defaults)


CONFIG = Config()


# ---- Rule 1: secrets --------------------------------------------------------


def test_rule_secrets_is_blunder():
    fs = _fs(secrets_detected=1)
    pr = _pr()
    result = classify_file(fs, pr, CONFIG)
    assert result.category == Category.BLUNDER
    assert "credential" in result.reasons[0]


# ---- Rule 2: force-push ------------------------------------------------------


def test_rule_force_push_is_blunder():
    fs = _fs()
    pr = _pr(force_pushed=True)
    result = classify_file(fs, pr, CONFIG)
    assert result.category == Category.BLUNDER


def test_rule_force_push_exempted_for_lockfiles():
    fs = _fs(is_dependency_lockfile=True)
    pr = _pr(force_pushed=True, test_files_changed=0)
    result = classify_file(fs, pr, CONFIG)
    # Should fall through to the Book rule instead of Blunder.
    assert result.category == Category.BOOK


# ---- Rule 3: critical + zero tests + empty message --------------------------


def test_rule_critical_no_tests_no_message_is_blunder():
    fs = _fs(is_critical=True)
    pr = _pr(test_files_changed=0, commit_message_quality="empty")
    result = classify_file(fs, pr, CONFIG)
    assert result.category == Category.BLUNDER


# ---- Rule 4: revert ----------------------------------------------------------


def test_rule_revert_is_miss():
    fs = _fs()
    pr = _pr(is_revert=True)
    result = classify_file(fs, pr, CONFIG)
    assert result.category == Category.MISS


# ---- Rule 5: disables tests ---------------------------------------------------


def test_rule_disables_tests_is_mistake():
    fs = _fs(disables_tests=True)
    pr = _pr()
    result = classify_file(fs, pr, CONFIG)
    assert result.category == Category.MISTAKE


# ---- Rule 6: hostile commit message -------------------------------------------


def test_rule_hostile_message_is_mistake():
    fs = _fs()
    pr = _pr(commit_message_quality="hostile")
    result = classify_file(fs, pr, CONFIG)
    assert result.category == Category.MISTAKE


# ---- Rule 7: large diff, zero tests --------------------------------------------


def test_rule_large_diff_no_tests_is_mistake():
    fs = _fs(lines_added=300, lines_removed=200)  # 500 total >= default 400
    pr = _pr(test_files_changed=0)
    result = classify_file(fs, pr, CONFIG)
    assert result.category == Category.MISTAKE


# ---- Rule 8: critical, zero tests (but message not empty) ----------------------


def test_rule_critical_no_tests_with_message_is_inaccuracy():
    fs = _fs(is_critical=True)
    pr = _pr(test_files_changed=0, commit_message_quality="vague")
    result = classify_file(fs, pr, CONFIG)
    assert result.category == Category.INACCURACY


# ---- Rule 9: TODO/FIXME with vague/empty message -------------------------------


def test_rule_todo_fixme_vague_message_is_inaccuracy():
    fs = _fs(todo_fixme_added=1)
    pr = _pr(commit_message_quality="vague")
    result = classify_file(fs, pr, CONFIG)
    assert result.category == Category.INACCURACY


def test_rule_todo_fixme_good_message_does_not_trigger_inaccuracy():
    fs = _fs(todo_fixme_added=1)
    pr = _pr(commit_message_quality="good")
    result = classify_file(fs, pr, CONFIG)
    assert result.category != Category.INACCURACY


# ---- Rule 10: dependency/formatting-only is Book -------------------------------


def test_rule_dependency_lockfile_is_book():
    fs = _fs(is_dependency_lockfile=True)
    pr = _pr()
    result = classify_file(fs, pr, CONFIG)
    assert result.category == Category.BOOK


def test_rule_formatting_only_is_book():
    fs = _fs(is_formatting_only=True)
    pr = _pr()
    result = classify_file(fs, pr, CONFIG)
    assert result.category == Category.BOOK


# ---- Rule 11: brilliant deletion ------------------------------------------------


def test_rule_brilliant_net_deletion_with_tests():
    fs = _fs(lines_added=0, lines_removed=80, net_lines=-80)
    pr = _pr(test_files_changed=1)
    result = classify_file(fs, pr, CONFIG)
    assert result.category == Category.BRILLIANT


def test_rule_brilliant_excluded_for_critical_paths():
    fs = _fs(lines_added=0, lines_removed=80, net_lines=-80, is_critical=True)
    pr = _pr(test_files_changed=1)
    result = classify_file(fs, pr, CONFIG)
    assert result.category != Category.BRILLIANT


# ---- Rule 12: great -------------------------------------------------------------


def test_rule_great_tests_added_good_message():
    fs = _fs(net_lines=10, has_matching_test=True)
    pr = _pr(test_files_changed=1, commit_message_quality="good")
    result = classify_file(fs, pr, CONFIG)
    assert result.category == Category.GREAT


def test_rule_great_requires_matching_test_not_just_any_test_in_pr():
    fs = _fs(net_lines=10, has_matching_test=False)
    pr = _pr(test_files_changed=1, commit_message_quality="good")
    result = classify_file(fs, pr, CONFIG)
    assert result.category != Category.GREAT


# ---- Rule 13/14/15: best / excellent / good defaults ----------------------------


def test_rule_best_single_small_file():
    fs = _fs(lines_added=5, lines_removed=2)
    pr = _pr(files=(fs,), total_files=1, test_files_changed=0, commit_message_quality="vague")
    result = classify_file(fs, pr, CONFIG)
    assert result.category == Category.BEST


def test_rule_excellent_moderate_multi_file():
    fs = _fs(lines_added=150, lines_removed=50)
    pr = _pr(total_files=3, test_files_changed=0, commit_message_quality="vague")
    result = classify_file(fs, pr, CONFIG)
    assert result.category == Category.EXCELLENT


def test_rule_good_default_when_nothing_flagged_and_large():
    fs = _fs(lines_added=300, lines_removed=200)
    pr = _pr(total_files=3, test_files_changed=1, commit_message_quality="vague")
    result = classify_file(fs, pr, CONFIG)
    assert result.category == Category.GOOD


# ---- Precedence: earlier rules must win over later-matching ones ---------------


def test_precedence_secrets_beats_book():
    # Both a Blunder condition (secret) and a Book condition (lockfile) are true.
    fs = _fs(secrets_detected=1, is_dependency_lockfile=True)
    pr = _pr()
    result = classify_file(fs, pr, CONFIG)
    assert result.category == Category.BLUNDER


def test_precedence_mistake_beats_inaccuracy():
    # Hostile message (Mistake, rule 6) AND todo/fixme with vague message would be
    # rule 9 (Inaccuracy) if evaluated alone -- Mistake must win since it's earlier.
    fs = _fs(todo_fixme_added=1)
    pr = _pr(commit_message_quality="hostile")
    result = classify_file(fs, pr, CONFIG)
    assert result.category == Category.MISTAKE


def test_precedence_disables_tests_beats_book():
    fs = _fs(disables_tests=True, is_dependency_lockfile=True)
    pr = _pr()
    result = classify_file(fs, pr, CONFIG)
    assert result.category == Category.MISTAKE


# ---- Weight lookup and accuracy computation -------------------------------------


def test_every_category_has_a_weight():
    for category in Category:
        assert category in CATEGORY_WEIGHT


def test_compute_accuracy_weighted_average():
    from chessreview.classifier import ClassificationResult

    results = [
        ClassificationResult(Category.BLUNDER, ("x",), CATEGORY_WEIGHT[Category.BLUNDER]),
        ClassificationResult(Category.BOOK, ("y",), CATEGORY_WEIGHT[Category.BOOK]),
    ]
    # Blunder file is 300 lines, Book file is 1 line -- Blunder should dominate.
    accuracy = compute_accuracy(results, [300, 1])
    expected = round((10 * 300 + 70 * 1) / 301, 1)
    assert accuracy == expected
    assert accuracy < 20  # dominated by the large Blunder file


def test_compute_accuracy_empty_results():
    assert compute_accuracy([], []) == 0.0


def test_compute_accuracy_zero_line_files_get_floor_weight():
    from chessreview.classifier import ClassificationResult

    results = [ClassificationResult(Category.BOOK, (), CATEGORY_WEIGHT[Category.BOOK])]
    # A pure rename has 0 lines changed -- must not divide-by-zero.
    accuracy = compute_accuracy(results, [0])
    assert accuracy == 70.0
