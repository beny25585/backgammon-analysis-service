from decimal import Decimal
from types import SimpleNamespace

from django.test import SimpleTestCase

from analysis.models import DecisionAnalysis
from analysis.services.scoring import (
    BLUNDER_THRESHOLD,
    PR_MULTIPLIER,
    TRIVIAL_SPREAD,
    calculate_pr,
    is_blunder,
    is_scoreable_checker,
    is_scoreable_cube,
    is_scoreable_decision,
)


def decision(
    *,
    decision_type,
    equity_loss="0",
    raw_analysis=None,
):
    return SimpleNamespace(
        decision_type=decision_type,
        equity_loss=(
            None
            if equity_loss is None
            else Decimal(str(equity_loss))
        ),
        raw_analysis=raw_analysis or {},
    )


def checker_decision(
    equities,
    *,
    equity_loss="0",
):
    return decision(
        decision_type=DecisionAnalysis.DecisionType.CHECKER_MOVE,
        equity_loss=equity_loss,
        raw_analysis={
            "moves": [
                {
                    "equity": value,
                    "board": [index] * 26,
                }
                for index, value in enumerate(equities)
            ]
        },
    )


def cube_decision(
    decision_type,
    *,
    nd,
    dt,
    dp,
    equity_loss="0",
    is_beaver=False,
):
    return decision(
        decision_type=decision_type,
        equity_loss=equity_loss,
        raw_analysis={
            "equities": {
                "no_double": nd,
                "double_take": dt,
                "double_pass": dp,
            },
            "is_beaver": is_beaver,
        },
    )


class ScoringConstantsTests(SimpleTestCase):
    def test_constants_match_open_sage_pr_rules(self):
        self.assertEqual(
            TRIVIAL_SPREAD,
            Decimal("0.001"),
        )

        self.assertEqual(
            BLUNDER_THRESHOLD,
            Decimal("0.08"),
        )

        self.assertEqual(
            PR_MULTIPLIER,
            Decimal("500"),
        )


class CheckerScoringTests(SimpleTestCase):
    def test_checker_with_one_move_is_not_scoreable(self):
        d = checker_decision(
            [0.30],
            equity_loss="0",
        )

        self.assertFalse(
            is_scoreable_checker(d)
        )

    def test_checker_trivial_spread_is_not_scoreable(self):
        d = checker_decision(
            [
                0.3000,
                0.2995,
            ],
            equity_loss="0",
        )

        self.assertFalse(
            is_scoreable_checker(d)
        )

    def test_checker_meaningful_spread_is_scoreable(self):
        d = checker_decision(
            [
                0.30,
                0.25,
            ],
            equity_loss="0.05",
        )

        self.assertTrue(
            is_scoreable_checker(d)
        )

    def test_checker_exact_trivial_threshold_is_scoreable(self):
        d = checker_decision(
            [
                Decimal("0.301"),
                Decimal("0.300"),
            ],
            equity_loss="0.001",
        )

        self.assertTrue(
            is_scoreable_checker(d)
        )


class CubeScoringTests(SimpleTestCase):
    def test_no_double_trivial_position_not_scoreable(self):
        d = cube_decision(
            DecisionAnalysis.DecisionType.NO_DOUBLE,
            nd="0.1000",
            dt="0.1005",
            dp="1.0",
        )

        self.assertFalse(
            is_scoreable_cube(d)
        )

    def test_no_double_meaningful_position_scoreable(self):
        d = cube_decision(
            DecisionAnalysis.DecisionType.NO_DOUBLE,
            nd="0.10",
            dt="0.30",
            dp="1.0",
        )

        self.assertTrue(
            is_scoreable_cube(d)
        )

    def test_obvious_no_double_not_scoreable(self):
        d = cube_decision(
            DecisionAnalysis.DecisionType.NO_DOUBLE,
            nd="0.50",
            dt="0.20",
            dp="1.0",
        )

        self.assertFalse(
            is_scoreable_cube(d)
        )

    def test_hopeless_cube_position_not_scoreable(self):
        d = cube_decision(
            DecisionAnalysis.DecisionType.NO_DOUBLE,
            nd="-0.95",
            dt="-0.92",
            dp="1.0",
        )

        self.assertFalse(
            is_scoreable_cube(d)
        )

    def test_take_response_meaningful_gap_scoreable(self):
        d = cube_decision(
            DecisionAnalysis.DecisionType.TAKE,
            nd="0.10",
            dt="0.20",
            dp="1.0",
        )

        self.assertTrue(
            is_scoreable_cube(d)
        )

    def test_take_response_trivial_gap_not_scoreable(self):
        d = cube_decision(
            DecisionAnalysis.DecisionType.TAKE,
            nd="0.10",
            dt="0.2000",
            dp="0.2005",
        )

        self.assertFalse(
            is_scoreable_cube(d)
        )

    def test_beaver_response_is_scoreable_even_when_gap_is_small(self):
        d = cube_decision(
            DecisionAnalysis.DecisionType.TAKE,
            nd="0.10",
            dt="0.2000",
            dp="0.2005",
            is_beaver=True,
        )

        self.assertTrue(
            is_scoreable_cube(d)
        )

    def test_missing_cube_equities_not_scoreable(self):
        d = decision(
            decision_type=DecisionAnalysis.DecisionType.DOUBLE,
            equity_loss="0.10",
            raw_analysis={},
        )

        self.assertFalse(
            is_scoreable_cube(d)
        )


class BlunderTests(SimpleTestCase):
    def test_equity_loss_above_threshold_is_blunder(self):
        d = checker_decision(
            [0.30, 0.10],
            equity_loss="0.081",
        )

        self.assertTrue(
            is_blunder(d)
        )

    def test_exact_threshold_is_not_blunder(self):
        d = checker_decision(
            [0.30, 0.10],
            equity_loss="0.08",
        )

        self.assertFalse(
            is_blunder(d)
        )

    def test_trivial_decision_is_not_blunder(self):
        d = checker_decision(
            [0.3000, 0.2995],
            equity_loss="0.50",
        )

        self.assertFalse(
            is_blunder(d)
        )


class PRCalculationTests(SimpleTestCase):
    def test_pr_uses_only_scoreable_decisions(self):
        decisions = [
            checker_decision(
                [0.40, 0.20],
                equity_loss="0.10",
            ),
            checker_decision(
                [0.30, 0.10],
                equity_loss="0.05",
            ),
            checker_decision(
                [0.3000, 0.2995],
                equity_loss="0.90",
            ),
        ]

        pr = calculate_pr(decisions)

        # (0.10 + 0.05) / 2 * 500 = 37.5
        self.assertEqual(
            pr,
            Decimal("37.50"),
        )

    def test_pr_combines_checker_and_cube_decisions(self):
        decisions = [
            checker_decision(
                [0.40, 0.20],
                equity_loss="0.04",
            ),
            cube_decision(
                DecisionAnalysis.DecisionType.NO_DOUBLE,
                nd="0.10",
                dt="0.30",
                dp="1.0",
                equity_loss="0.06",
            ),
        ]

        pr = calculate_pr(decisions)

        # (0.04 + 0.06) / 2 * 500 = 25
        self.assertEqual(
            pr,
            Decimal("25.00"),
        )

    def test_no_scoreable_decisions_returns_zero(self):
        decisions = [
            checker_decision(
                [0.3000, 0.2995],
                equity_loss="0.50",
            )
        ]

        self.assertEqual(
            calculate_pr(decisions),
            Decimal("0"),
        )

    def test_missing_equity_loss_is_excluded(self):
        decisions = [
            checker_decision(
                [0.40, 0.20],
                equity_loss=None,
            ),
        ]

        self.assertEqual(
            calculate_pr(decisions),
            Decimal("0"),
        )

    def test_dispatcher_recognizes_checker_and_cube(self):
        checker = checker_decision(
            [0.40, 0.20],
        )

        cube = cube_decision(
            DecisionAnalysis.DecisionType.DOUBLE,
            nd="0.10",
            dt="0.30",
            dp="1.0",
        )

        self.assertTrue(
            is_scoreable_decision(checker)
        )

        self.assertTrue(
            is_scoreable_decision(cube)
        )
