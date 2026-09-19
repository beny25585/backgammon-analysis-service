from unittest.mock import patch

from django.test import TestCase

from analysis.models import (
    DecisionAnalysis,
    GameAnalysis,
    MatchAnalysis,
    PlayerGameAnalysis,
    PlayerMatchAnalysis,
)
from analysis.services.cube_processor import (
    process_game_cube_decisions,
)


class CubeProcessorTests(TestCase):
    def setUp(self):
        self.match_analysis = MatchAnalysis.objects.create(
            source_match_id="22222222-2222-2222-2222-222222222222",
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

        self.white_game = PlayerGameAnalysis.objects.create(
            game_analysis=self.game_analysis,
            match_player_analysis=self.white_match,
        )

        self.black_game = PlayerGameAnalysis.objects.create(
            game_analysis=self.game_analysis,
            match_player_analysis=self.black_match,
        )

    @patch(
        "analysis.services.cube_processor.analyze_cube_decision"
    )
    @patch(
        "analysis.services.cube_processor.extract_cube_decisions"
    )
    def test_persists_cube_decisions(
        self,
        extract_mock,
        analyze_mock,
    ):
        extract_mock.return_value = [
            {
                "player": "white",
                "decision_type": "no_double",
                "source_event_sequence": 10,
            },
            {
                "player": "black",
                "decision_type": "take",
                "source_event_sequence": 21,
            },
        ]

        analyze_mock.side_effect = [
            {
                "player": "white",
                "decision_type": "no_double",
                "source_event_sequence": 10,
                "played_action": {
                    "action": "no_double",
                },
                "best_action": {
                    "action": "double",
                    "response": "take",
                },
                "played_equity": 0.10,
                "best_equity": 0.30,
                "equity_loss": 0.20,
                "alternatives": {
                    "no_double": 0.10,
                    "double_take": 0.30,
                    "double_pass": 1.00,
                },
                "position_snapshot": {
                    "turn": "white",
                },
                "raw_analysis": {
                    "engine": "fake",
                },
            },
            {
                "player": "black",
                "decision_type": "take",
                "source_event_sequence": 21,
                "played_action": {
                    "action": "take",
                },
                "best_action": {
                    "action": "take",
                },
                "played_equity": -0.20,
                "best_equity": -0.20,
                "equity_loss": 0.0,
                "alternatives": {
                    "no_double": 0.10,
                    "double_take": 0.20,
                    "double_pass": 1.00,
                },
                "position_snapshot": {
                    "turn": "white",
                },
                "raw_analysis": {
                    "engine": "fake",
                },
            },
        ]

        created = process_game_cube_decisions(
            game_analysis=self.game_analysis,
        )

        self.assertEqual(len(created), 2)
        self.assertEqual(
            DecisionAnalysis.objects.count(),
            2,
        )

        no_double = DecisionAnalysis.objects.get(
            decision_type=DecisionAnalysis.DecisionType.NO_DOUBLE
        )

        take = DecisionAnalysis.objects.get(
            decision_type=DecisionAnalysis.DecisionType.TAKE
        )

        self.assertEqual(
            no_double.player_game_analysis,
            self.white_game,
        )

        self.assertEqual(
            take.player_game_analysis,
            self.black_game,
        )

        self.assertEqual(
            no_double.sequence_number,
            10,
        )

        self.assertEqual(
            take.sequence_number,
            21,
        )

        self.assertEqual(
            float(no_double.played_equity),
            0.10,
        )

        self.assertEqual(
            float(no_double.best_equity),
            0.30,
        )

        self.assertEqual(
            float(no_double.equity_loss),
            0.20,
        )

        self.assertEqual(
            no_double.classification,
            DecisionAnalysis.Classification.UNCLASSIFIED,
        )

    @patch(
        "analysis.services.cube_processor.analyze_cube_decision"
    )
    @patch(
        "analysis.services.cube_processor.extract_cube_decisions"
    )
    def test_reprocessing_does_not_duplicate(
        self,
        extract_mock,
        analyze_mock,
    ):
        extract_mock.return_value = [
            {
                "player": "white",
                "decision_type": "double",
                "source_event_sequence": 30,
            },
        ]

        analyze_mock.return_value = {
            "player": "white",
            "decision_type": "double",
            "source_event_sequence": 30,
            "played_action": {
                "action": "double",
            },
            "best_action": {
                "action": "double",
                "response": "take",
            },
            "played_equity": 0.30,
            "best_equity": 0.30,
            "equity_loss": 0.0,
            "alternatives": {},
            "position_snapshot": {},
            "raw_analysis": {},
        }

        process_game_cube_decisions(
            game_analysis=self.game_analysis,
        )

        process_game_cube_decisions(
            game_analysis=self.game_analysis,
        )

        self.assertEqual(
            DecisionAnalysis.objects.count(),
            1,
        )
