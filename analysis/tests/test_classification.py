
from django.test import SimpleTestCase

from analysis.services.classification import classify_decision, classification_counts
from analysis.tests.test_scoring import checker_decision, cube_decision, decision


class ClassificationTests(SimpleTestCase):
    def test_boundaries_for_checker_and_all_cube_types(self):
        cases = [
            ("0", "correct"),
            ("0.019999", "correct"),
            ("0.02", "inaccuracy"),
            ("0.039999", "inaccuracy"),
            ("0.04", "error"),
            ("0.079999", "error"),
            ("0.08", "error"),
            ("0.080001", "blunder"),
        ]
        for loss, expected in cases:
            candidates = [checker_decision([0.4, 0.1], equity_loss=loss)]
            candidates.extend(
                cube_decision(kind, nd="0.1", dt="0.3", dp="1", equity_loss=loss)
                for kind in ("no_double", "double", "redouble", "take", "pass")
            )
            for candidate in candidates:
                with self.subTest(loss=loss, kind=candidate.decision_type):
                    self.assertEqual(classify_decision(candidate), expected)

    def test_missing_or_nonfinite_loss_is_unclassified(self):
        for loss in (None, "NaN", "sNaN", "Infinity", "-Infinity"):
            with self.subTest(loss=loss):
                candidate = checker_decision([0.4, 0.1], equity_loss=loss)
                self.assertEqual(classify_decision(candidate), "unclassified")

    def test_unscoreable_decisions_are_unclassified_even_with_large_loss(self):
        candidates = [
            checker_decision([0.4], equity_loss="0.5"),
            checker_decision([0.4, 0.3995], equity_loss="0.5"),
            decision(decision_type="checker_move", equity_loss="0.5"),
            decision(decision_type="double", equity_loss="0.5"),
            decision(decision_type="too_good", equity_loss="0.5"),
            cube_decision("no_double", nd="0.1", dt="0.1005", dp="1", equity_loss="0.5"),
            cube_decision("take", nd="0.1", dt="0.3", dp="0.3005", equity_loss="0.5"),
        ]
        for candidate in candidates:
            with self.subTest(candidate=candidate):
                self.assertEqual(classify_decision(candidate), "unclassified")

    def test_counts_exclude_inaccuracy_blunders_from_errors_and_unclassified(self):
        candidates = [
            checker_decision([0.4, 0.1], equity_loss=loss)
            for loss in ("0", "0.02", "0.04", "0.08", "0.080001", None, "NaN")
        ]
        candidates.append(checker_decision([0.4], equity_loss="0.5"))
        self.assertEqual(classification_counts(candidates), {"errors": 2, "blunders": 1})
        self.assertEqual(classification_counts([]), {"errors": 0, "blunders": 0})