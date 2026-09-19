from decimal import Decimal

from django.test import TestCase

from analysis.models import (
    DecisionAnalysis,
    GameAnalysis,
    MatchAnalysis,
    PlayerGameAnalysis,
    PlayerMatchAnalysis,
)
from analysis.services.player_summary import (
    update_player_game_summary,
)


class PlayerSummaryTests(TestCase):
    def setUp(self):
        self.match_analysis = MatchAnalysis.objects.create(
            source_match_id="55555555-5555-5555-5555-555555555555",
            source_type=MatchAnalysis.SourceType.PRIVATE,
            input_payload={},
        )

        self.game_analysis = GameAnalysis.objects.create(
            match_analysis=self.match_analysis,
            source_game_id="game-1",
            game_number=1,
            winner="white",
            win_type="single",
            points_awarded=1,
        )

        self.white_match = PlayerMatchAnalysis.objects.create(
            match_analysis=self.match_analysis,
            source_player_id=100,
            color="white",
        )

        self.white_game = PlayerGameAnalysis.objects.create(
            game_analysis=self.game_analysis,
            match_player_analysis=self.white_match,
        )

    def _checker_decision(
        self,
        *,
        sequence,
        equity_loss,
        best=0.40,
        second=0.20,
    ):
        return DecisionAnalysis.objects.create(
            player_game_analysis=self.white_game,
            sequence_number=sequence,
            source_event_sequence=sequence,
            decision_type=DecisionAnalysis.DecisionType.CHECKER_MOVE,
            dice=[6, 3],
            played_equity=Decimal(str(best - equity_loss)),
            best_equity=Decimal(str(best)),
            equity_loss=Decimal(str(equity_loss)),
            position_snapshot={},
            raw_analysis={
                "moves": [
                    {
                        "equity": best,
                        "board": [1] * 26,
                    },
                    {
                        "equity": second,
                        "board": [2] * 26,
                    },
                ],
            },
        )

    def _cube_decision(
        self,
        *,
        sequence,
        equity_loss,
        decision_type=DecisionAnalysis.DecisionType.NO_DOUBLE,
        nd=0.10,
        dt=0.30,
        dp=1.00,
    ):
        return DecisionAnalysis.objects.create(
            player_game_analysis=self.white_game,
            sequence_number=sequence,
            source_event_sequence=sequence,
            decision_type=decision_type,
            dice=[],
            played_equity=Decimal("0.10"),
            best_equity=Decimal("0.30"),
            equity_loss=Decimal(str(equity_loss)),
            position_snapshot={},
            raw_analysis={
                "equities": {
                    "no_double": nd,
                    "double_take": dt,
                    "double_pass": dp,
                },
                "is_beaver": False,
            },
        )

    def test_updates_player_game_summary(self):
        self._checker_decision(
            sequence=10,
            equity_loss=0.04,
        )

        self._checker_decision(
            sequence=20,
            equity_loss=0.10,
        )

        self._cube_decision(
            sequence=30,
            equity_loss=0.06,
        )

        result = update_player_game_summary(
            self.white_game
        )

        self.white_game.refresh_from_db()

        # Total error:
        # 0.04 + 0.10 + 0.06 = 0.20
        #
        # PR:
        # 0.20 / 3 * 500 = 33.333333...
        self.assertAlmostEqual(
            float(self.white_game.pr),
            33.333333,
            places=5,
        )

        # Checker:
        # (0.04 + 0.10) / 2 * 500 = 35
        self.assertEqual(
            self.white_game.checker_pr,
            Decimal("35"),
        )

        # Cube:
        # 0.06 / 1 * 500 = 30
        self.assertEqual(
            self.white_game.cube_pr,
            Decimal("30"),
        )

        self.assertEqual(
            self.white_game.equity_lost,
            Decimal("0.20"),
        )

        # 0.10 > 0.08 => one checker blunder
        self.assertEqual(
            self.white_game.checker_blunders,
            1,
        )

        self.assertEqual(
            self.white_game.cube_blunders,
            0,
        )

        self.assertEqual(
            self.white_game.blunders,
            1,
        )

        self.assertIsNone(
            self.white_game.checker_errors,
        )

        self.assertIsNone(
            self.white_game.cube_errors,
        )

        self.assertIsNone(
            self.white_game.errors,
        )

        self.assertEqual(
            result["decisions_analyzed"],
            3,
        )

        self.assertEqual(
            result["checker_decisions"],
            2,
        )

        self.assertEqual(
            result["cube_decisions"],
            1,
        )

    def test_trivial_decisions_do_not_affect_summary(self):
        # Checker spread = 0.0005 < 0.001
        self._checker_decision(
            sequence=10,
            equity_loss=0.50,
            best=0.3000,
            second=0.2995,
        )

        result = update_player_game_summary(
            self.white_game
        )

        self.white_game.refresh_from_db()

        self.assertEqual(
            self.white_game.pr,
            Decimal("0"),
        )

        self.assertEqual(
            self.white_game.equity_lost,
            Decimal("0"),
        )

        self.assertEqual(
            self.white_game.blunders,
            0,
        )

        self.assertEqual(
            result["decisions_analyzed"],
            0,
        )

    def test_no_decisions_produces_zero_summary(self):
        result = update_player_game_summary(
            self.white_game
        )

        self.white_game.refresh_from_db()

        self.assertEqual(
            self.white_game.pr,
            Decimal("0"),
        )

        self.assertEqual(
            self.white_game.checker_pr,
            Decimal("0"),
        )

        self.assertEqual(
            self.white_game.cube_pr,
            Decimal("0"),
        )

        self.assertEqual(
            self.white_game.equity_lost,
            Decimal("0"),
        )

        self.assertEqual(
            self.white_game.blunders,
            0,
        )

        self.assertEqual(
            result["decisions_analyzed"],
            0,
        )

    def test_cube_blunder_is_counted(self):
        self._cube_decision(
            sequence=10,
            equity_loss=0.09,
        )

        update_player_game_summary(
            self.white_game
        )

        self.white_game.refresh_from_db()

        self.assertEqual(
            self.white_game.cube_blunders,
            1,
        )

        self.assertEqual(
            self.white_game.blunders,
            1,
        )
