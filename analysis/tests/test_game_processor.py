from unittest.mock import patch

from django.test import TestCase

from analysis.models import (
    GameAnalysis,
    MatchAnalysis,
    PlayerGameAnalysis,
    PlayerMatchAnalysis,
)
from analysis.services.game_processor import (
    process_game_analysis,
)


class GameProcessorTests(TestCase):
    def setUp(self):
        self.match_analysis = MatchAnalysis.objects.create(
            source_match_id=(
                "33333333-3333-3333-3333-333333333333"
            ),
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

        self.black_match = PlayerMatchAnalysis.objects.create(
            match_analysis=self.match_analysis,
            source_player_id=200,
            color="black",
        )

        PlayerGameAnalysis.objects.create(
            game_analysis=self.game_analysis,
            match_player_analysis=self.white_match,
        )

        PlayerGameAnalysis.objects.create(
            game_analysis=self.game_analysis,
            match_player_analysis=self.black_match,
        )

    @patch(
        "analysis.services.game_processor."
        "process_game_luck"
    )
    @patch(
        "analysis.services.game_processor."
        "process_game_cube_decisions"
    )
    @patch(
        "analysis.services.game_processor."
        "process_game_checker_decisions"
    )
    def test_processes_checker_cube_and_luck(
        self,
        checker_mock,
        cube_mock,
        luck_mock,
    ):
        checker_mock.return_value = [
            object(),
            object(),
            object(),
        ]

        cube_mock.return_value = [
            object(),
            object(),
        ]

        luck_mock.return_value = {
            "rolls": [],
            "rolls_analyzed": 4,
            "white": {
                "luck": 0.10,
                "rolls": 2,
            },
            "black": {
                "luck": -0.10,
                "rolls": 2,
            },
        }

        result = process_game_analysis(
            game_analysis=self.game_analysis,
        )

        self.assertEqual(
            len(result["checker_decisions"]),
            3,
        )

        self.assertEqual(
            len(result["cube_decisions"]),
            2,
        )

        self.assertEqual(
            result["decisions_created"],
            5,
        )

        self.assertEqual(
            result["rolls_analyzed"],
            4,
        )

        self.assertEqual(
            result["luck"]["white"]["luck"],
            0.10,
        )

        self.assertEqual(
            result["luck"]["black"]["luck"],
            -0.10,
        )

        checker_mock.assert_called_once()
        cube_mock.assert_called_once()
        luck_mock.assert_called_once()

        checker_call = (
            checker_mock.call_args.kwargs
        )

        cube_call = (
            cube_mock.call_args.kwargs
        )

        luck_call = (
            luck_mock.call_args.kwargs
        )

        self.assertEqual(
            checker_call["game_analysis"],
            self.game_analysis,
        )

        self.assertEqual(
            cube_call["game_analysis"],
            self.game_analysis,
        )

        self.assertEqual(
            luck_call["game_analysis"],
            self.game_analysis,
        )

        # The same OpenSageEngine instance
        # must be reused by all processors.
        self.assertIs(
            checker_call["engine"],
            cube_call["engine"],
        )

        self.assertIs(
            checker_call["engine"],
            luck_call["engine"],
        )

        self.assertIs(
            cube_call["engine"],
            luck_call["engine"],
        )

        self.assertIn(
            "player_summaries",
            result,
        )

        self.assertIn(
            "white",
            result["player_summaries"],
        )

        self.assertIn(
            "black",
            result["player_summaries"],
        )
