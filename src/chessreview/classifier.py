"""Fixed, ordered rule table -> chess.com-style category.

Pure function of FileSignals + PRSignals. No LLM call here, ever.
commentary.py may only phrase a Category already decided here, never change
one. test_classifier.py must pass with commentary.py deleted.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from chessreview.config import Config
from chessreview.signals import FileSignals, PRSignals


class Category(str, Enum):
    BRILLIANT = "Brilliant!!"
    GREAT = "Great!"
    BEST = "Best"
    EXCELLENT = "Excellent"
    GOOD = "Good"
    BOOK = "Book"
    INACCURACY = "Inaccuracy?!"
    MISTAKE = "Mistake?"
    BLUNDER = "Blunder??"
    MISS = "Miss"


CATEGORY_WEIGHT: dict[Category, int] = {
    Category.BRILLIANT: 100,
    Category.GREAT: 95,
    Category.BEST: 90,
    Category.EXCELLENT: 85,
    Category.GOOD: 75,
    Category.BOOK: 70,
    Category.INACCURACY: 55,
    Category.MISTAKE: 35,
    Category.MISS: 20,
    Category.BLUNDER: 10,
}


@dataclass(frozen=True)
class ClassificationResult:
    category: Category
    reasons: tuple[str, ...]
    weight: int


def classify_file(
    file_signals: FileSignals, pr_signals: PRSignals, config: Config
) -> ClassificationResult:
    """First matching rule wins -- order is the spec."""

    def result(category: Category, *reasons: str) -> ClassificationResult:
        return ClassificationResult(
            category=category, reasons=reasons, weight=CATEGORY_WEIGHT[category]
        )

    fs, pr = file_signals, pr_signals
    total_lines = fs.lines_added + fs.lines_removed

    # 1. Credential leak -- always worst outcome, no exceptions.
    if fs.secrets_detected > 0:
        return result(
            Category.BLUNDER,
            f"{fs.secrets_detected} possible credential(s) detected in diff",
        )

    # 2. Force-push (Action mode only; CLI needs explicit --force-pushed).
    if pr.force_pushed and not fs.is_dependency_lockfile:
        return result(Category.BLUNDER, "force-push detected over existing history")

    # 3. Critical path, zero tests in PR, no description at all.
    if fs.is_critical and pr.test_files_changed == 0 and pr.commit_message_quality == "empty":
        return result(
            Category.BLUNDER,
            "touches a critical path with no tests and no description",
        )

    # 4. Revert -- the original commit missed something.
    if pr.is_revert:
        return result(
            Category.MISS,
            "reverts a recent commit — the original change missed something",
        )

    # 5. Disables/skips an existing test.
    if fs.disables_tests:
        return result(Category.MISTAKE, "disables or skips an existing test")

    # 6. Rushed/frustrated commit message.
    if pr.commit_message_quality == "hostile":
        return result(
            Category.MISTAKE, "commit message signals a rushed or frustrated fix"
        )

    # 7. Large diff, zero test changes in PR.
    if total_lines >= config.large_threshold and pr.test_files_changed == 0:
        return result(Category.MISTAKE, "large diff with zero test changes")

    # 8. Critical path, zero test changes in PR.
    if fs.is_critical and pr.test_files_changed == 0:
        return result(
            Category.INACCURACY,
            "touches a critical path without matching test changes",
        )

    # 9. TODO/FIXME added with no context.
    if fs.todo_fixme_added > 0 and pr.commit_message_quality in ("vague", "empty"):
        return result(Category.INACCURACY, "adds TODO/FIXME with no context")

    # 10. Routine: dependency bump or pure reformatting.
    if fs.is_dependency_lockfile or fs.is_formatting_only:
        return result(Category.BOOK, "routine dependency or formatting-only change")

    # 11. Net code reduction, tests maintained, not critical.
    if fs.net_lines <= -50 and pr.test_files_changed > 0 and not fs.is_critical:
        return result(
            Category.BRILLIANT,
            "net code reduction with maintained test coverage",
        )

    # 12. This specific file has a plausibly-corresponding test file also
    #     changed in the PR (not just "some test changed somewhere").
    if (
        fs.has_matching_test
        and pr.commit_message_quality == "good"
        and not fs.is_critical
    ):
        return result(Category.GREAT, "has a matching test file changed alongside it")

    # 13. Small, single-file, single-purpose change.
    if pr.total_files == 1 and total_lines <= config.moderate_threshold:
        return result(Category.BEST, "small, focused, single-file change")

    # 14. Moderate size, nothing flagged.
    if total_lines <= config.large_threshold:
        return result(Category.EXCELLENT, "moderate change, no risk signals")

    # 15. Default.
    return result(Category.GOOD, "no notable risk or quality signals")


def compute_accuracy(results: list[ClassificationResult], line_weights: list[int]) -> float:
    """Weighted avg of category weight by lines-changed per file.
    Zero-line files (pure renames) get a floor weight of 1."""
    if not results:
        return 0.0
    floored_weights = [max(w, 1) for w in line_weights]
    total_weight = sum(floored_weights)
    if total_weight == 0:
        return 0.0
    weighted_sum = sum(r.weight * w for r, w in zip(results, floored_weights))
    return round(weighted_sum / total_weight, 1)
