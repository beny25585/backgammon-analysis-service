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
    update_player_match_summary,
)


class PlayerMatchSummaryTests(TestCase):
    def setUp(self):
        self.match_analysis = MatchAnalysis.objects.create(
            source_match_id="66666666-6666-6666-6666-666666666666",
            source_type=MatchAnalysis.SourceType.PRIVATE,
            input_payload={},
        )

        self.white_match = PlayerMatchAnalysis.objects.create(
            match_analysis=self.match_analysis,
            source_player_id=100,
            color="white",
        )

        self.game1 = GameAnalysis.objects.create(
            match_analysis=self.match_analysis,
            source_game_id="game-1",
            game_number=1,
            winner="white",
            win_type="single",
            points_awarded=1,
        )

        self.game2 = GameAnalysis.objects.create(
            match_analysis=self.match_analysis,
            source_game_id="game-2",
            game_number=2,
            winner="black",
            win_type="single",
            points_awarded=1,
        )

        self.white_game1 = PlayerGameAnalysis.objects.create(
            game_analysis=self.game1,
            match_player_analysis=self.white_match,
        )

        self.white_game2 = PlayerGameAnalysis.objects.create(
            game_analysis=self.game2,
            match_player_analysis=self.white_match,
        )

    def _checker(
        self,
        player_game,
        *,
        sequence,
        equity_loss,
        best=0.40,
        second=0.20,
    ):
        return DecisionAnalysis.objects.create(
            player_game_analysis=player_game,
            sequence_number=sequence,
            source_event_sequence=sequence,
            decision_type=DecisionAnalysis.DecisionType.CHECKER_MOVE,
            dice=[6, 3],
            played_equity=Decimal(
                str(best - equity_loss)
            ),
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

    def _cube(
        self,
        player_game,
        *,
        sequence,
        equity_loss,
    ):
        return DecisionAnalysis.objects.create(
            player_game_analysis=player_game,
            sequence_number=sequence,
            source_event_sequence=sequence,
            decision_type=(
                DecisionAnalysis.DecisionType.NO_DOUBLE
            ),
            dice=[],
            played_equity=Decimal("0.10"),
            best_equity=Decimal("0.30"),
            equity_loss=Decimal(str(equity_loss)),
            position_snapshot={},
            raw_analysis={
                "equities": {
                    "no_double": 0.10,
                    "double_take": 0.30,
                    "double_pass": 1.00,
                },
                "is_beaver": False,
            },
        )

    def test_aggregates_multiple_games(self):
        # Game 1
        self._checker(
            self.white_game1,
            sequence=10,
            equity_loss=0.04,
        )

        self._cube(
            self.white_game1,
            sequence=20,
            equity_loss=0.06,
        )

        # Game 2
        self._checker(
            self.white_game2,
            sequence=30,
            equity_loss=0.10,
        )

        self._cube(
            self.white_game2,
            sequence=40,
            equity_loss=0.00,
        )
        self.white_game1.luck = Decimal("0.12")

        self.white_game1.save(
            update_fields=["luck"]
        )

        self.white_game2.luck = Decimal("-0.04")
        self.white_game2.save(
            update_fields=["luck"]
        )

        result = update_player_match_summary(
            self.white_match
        )

        self.white_match.refresh_from_db()

        self.assertEqual(
            self.white_match.luck,
            Decimal("0.08"),
        )

        self.assertEqual(
            result["luck"],
            Decimal("0.08"),
        )

        # Total:
        # 0.04 + 0.06 + 0.10 + 0.00 = 0.20
        #
        # PR:
        # 0.20 / 4 * 500 = 25
        self.assertEqual(
            self.white_match.pr,
            Decimal("25"),
        )

        # Checker:
        # 0.04 + 0.10 = 0.14
        # 0.14 / 2 * 500 = 35
        self.assertEqual(
            self.white_match.checker_pr,
            Decimal("35"),
        )

        # Cube:
        # 0.06 / 2 * 500 = 15
        self.assertEqual(
            self.white_match.cube_pr,
            Decimal("15"),
        )

        self.assertEqual(
            self.white_match.equity_lost,
            Decimal("0.20"),
        )

        self.assertEqual(
            self.white_match.checker_equity_lost,
            Decimal("0.14"),
        )

        self.assertEqual(
            self.white_match.cube_equity_lost,
            Decimal("0.06"),
        )

        self.assertEqual(
            self.white_match.decisions_analyzed,
            4,
        )

        # 0.10 > 0.08
        self.assertEqual(
            self.white_match.checker_blunders,
            1,
        )

        self.assertEqual(
            self.white_match.cube_blunders,
            0,
        )

        self.assertEqual(
            self.white_match.blunders,
            1,
        )

        self.assertEqual(
            result["checker_decisions"],
            2,
        )

        self.assertEqual(
            result["cube_decisions"],
            2,
        )

        self.assertEqual(
            result["decisions_analyzed"],
            4,
        )

    def test_trivial_decision_is_excluded(self):
        # Spread = 0.0005, below 0.001.
        self._checker(
            self.white_game1,
            sequence=10,
            equity_loss=0.50,
            best=0.3000,
            second=0.2995,
        )

        result = update_player_match_summary(
            self.white_match
        )

        self.white_match.refresh_from_db()

        self.assertEqual(
            self.white_match.pr,
            Decimal("0"),
        )

        self.assertEqual(
            self.white_match.equity_lost,
            Decimal("0"),
        )

        self.assertEqual(
            self.white_match.decisions_analyzed,
            0,
        )

        self.assertEqual(
            self.white_match.blunders,
            0,
        )

        self.assertEqual(
            result["decisions_analyzed"],
            0,
        )

    def test_empty_match_summary_is_zero(self):
        result = update_player_match_summary(
            self.white_match
        )

        self.white_match.refresh_from_db()

        self.assertEqual(
            self.white_match.pr,
            Decimal("0"),
        )

        self.assertEqual(
            self.white_match.checker_pr,
            Decimal("0"),
        )

        self.assertEqual(
            self.white_match.cube_pr,
            Decimal("0"),
        )

        self.assertEqual(
            self.white_match.equity_lost,
            Decimal("0"),
        )

        self.assertEqual(
            self.white_match.checker_equity_lost,
            Decimal("0"),
        )

        self.assertEqual(
            self.white_match.cube_equity_lost,
            Decimal("0"),
        )

        self.assertEqual(
            self.white_match.decisions_analyzed,
            0,
        )

        self.assertEqual(
            result["decisions_analyzed"],
            0,
        )
        self.assertEqual(
            self.white_match.luck,
            Decimal("0"),
        )

        self.assertEqual(
            result["luck"],
            Decimal("0"),
        )
