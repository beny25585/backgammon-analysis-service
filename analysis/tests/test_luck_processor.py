from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase

from analysis.models import (
    GameAnalysis,
    MatchAnalysis,
    PlayerGameAnalysis,
    PlayerMatchAnalysis,
    RollLuckAnalysis,
)
from analysis.services.luck_processor import (
    process_game_luck,
)


class LuckProcessorTests(TestCase):
    def setUp(self):
        self.match_analysis = MatchAnalysis.objects.create(
            source_match_id=(
                "77777777-7777-7777-7777-777777777777"
            ),
            source_type=MatchAnalysis.SourceType.PRIVATE,
            input_payload={
                "rules": {
                    "format": "match",
                    "target_points": 5,
                    "jacoby": True,
                    "max_cube_value": 0,
                }
            },
        )

        self.game_analysis = GameAnalysis.objects.create(
            match_analysis=self.match_analysis,
            source_game_id="game-1",
            game_number=1,
            winner="white",
            win_type="single",
            points_awarded=1,
            white_score_before=0,
            black_score_before=0,
            white_score_after=1,
            black_score_after=0,
            is_crawford=False,
            input_events=[],
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

        self.white_game = PlayerGameAnalysis.objects.create(
            game_analysis=self.game_analysis,
            match_player_analysis=self.white_match,
        )

        self.black_game = PlayerGameAnalysis.objects.create(
            game_analysis=self.game_analysis,
            match_player_analysis=self.black_match,
        )

    @patch(
        "analysis.services.luck_processor."
        "analyze_roll_luck"
    )
    @patch(
        "analysis.services.luck_processor."
        "extract_luck_rolls"
    )
    def test_persists_rolls_and_updates_player_luck(
        self,
        extract_mock,
        analyze_mock,
    ):
        extract_mock.return_value = [
            {
                "source_event_sequence": 10,
                "player": "white",
                "dice": [6, 3],
                "state": {},
                "is_opening_roll": False,
            },
            {
                "source_event_sequence": 20,
                "player": "black",
                "dice": [4, 2],
                "state": {},
                "is_opening_roll": False,
            },
            {
                "source_event_sequence": 30,
                "player": "white",
                "dice": [5, 1],
                "state": {},
                "is_opening_roll": False,
            },
        ]

        analyze_mock.side_effect = [
            {
                "player": "white",
                "dice": [6, 3],
                "source_event_sequence": 10,
                "is_opening_roll": False,
                "luck": 0.08,
                "actual_equity": 0.30,
                "average_equity": 0.22,
                "ply": 1,
                "level_label": "1-ply",
                "position_snapshot": {},
                "raw_analysis": {},
            },
            {
                "player": "black",
                "dice": [4, 2],
                "source_event_sequence": 20,
                "is_opening_roll": False,
                "luck": -0.04,
                "actual_equity": 0.10,
                "average_equity": 0.14,
                "ply": 1,
                "level_label": "1-ply",
                "position_snapshot": {},
                "raw_analysis": {},
            },
            {
                "player": "white",
                "dice": [5, 1],
                "source_event_sequence": 30,
                "is_opening_roll": False,
                "luck": 0.02,
                "actual_equity": 0.25,
                "average_equity": 0.23,
                "ply": 1,
                "level_label": "1-ply",
                "position_snapshot": {},
                "raw_analysis": {},
            },
        ]

        result = process_game_luck(
            game_analysis=self.game_analysis,
        )

        self.white_game.refresh_from_db()
        self.black_game.refresh_from_db()

        self.assertEqual(
            RollLuckAnalysis.objects.count(),
            3,
        )

        self.assertEqual(
            self.white_game.luck,
            Decimal("0.10"),
        )

        self.assertEqual(
            self.black_game.luck,
            Decimal("-0.04"),
        )

        self.assertEqual(
            result["rolls_analyzed"],
            3,
        )

        self.assertEqual(
            result["white"]["luck"],
            Decimal("0.10"),
        )

        self.assertEqual(
            result["white"]["rolls"],
            2,
        )

        self.assertEqual(
            result["black"]["luck"],
            Decimal("-0.04"),
        )

        self.assertEqual(
            result["black"]["rolls"],
            1,
        )

    @patch(
        "analysis.services.luck_processor."
        "analyze_roll_luck"
    )
    @patch(
        "analysis.services.luck_processor."
        "extract_luck_rolls"
    )
    def test_reprocessing_does_not_duplicate_rolls(
        self,
        extract_mock,
        analyze_mock,
    ):
        extract_mock.return_value = [
            {
                "source_event_sequence": 10,
                "player": "white",
                "dice": [6, 3],
                "state": {},
                "is_opening_roll": False,
            },
        ]

        analyze_mock.return_value = {
            "player": "white",
            "dice": [6, 3],
            "source_event_sequence": 10,
            "is_opening_roll": False,
            "luck": 0.05,
            "actual_equity": 0.30,
            "average_equity": 0.25,
            "ply": 1,
            "level_label": "1-ply",
            "position_snapshot": {},
            "raw_analysis": {},
        }

        process_game_luck(
            game_analysis=self.game_analysis,
        )

        process_game_luck(
            game_analysis=self.game_analysis,
        )

        self.assertEqual(
            RollLuckAnalysis.objects.count(),
            1,
        )

        self.white_game.refresh_from_db()

        self.assertEqual(
            self.white_game.luck,
            Decimal("0.05"),
        )

    @patch(
        "analysis.services.luck_processor."
        "extract_luck_rolls"
    )
    def test_no_rolls_sets_both_players_to_zero(
        self,
        extract_mock,
    ):
        extract_mock.return_value = []

        self.white_game.luck = Decimal("0.50")
        self.white_game.save(
            update_fields=["luck"]
        )

        self.black_game.luck = Decimal("-0.25")
        self.black_game.save(
            update_fields=["luck"]
        )

        result = process_game_luck(
            game_analysis=self.game_analysis,
        )

        self.white_game.refresh_from_db()
        self.black_game.refresh_from_db()

        self.assertEqual(
            self.white_game.luck,
            Decimal("0"),
        )

        self.assertEqual(
            self.black_game.luck,
            Decimal("0"),
        )

        self.assertEqual(
            result["rolls_analyzed"],
            0,
        )

        self.assertEqual(
            RollLuckAnalysis.objects.count(),
            0,
        )
