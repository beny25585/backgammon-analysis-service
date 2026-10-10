from unittest.mock import patch

from django.test import TestCase

from analysis.models import (
    DecisionAnalysis,
    GameAnalysis,
    MatchAnalysis,
    PlayerGameAnalysis,
    PlayerMatchAnalysis,
)
from analysis.services.checker_processor import (
    process_game_checker_decisions,
)


class CheckerProcessorTests(TestCase):
    @patch("analysis.services.checker_processor.analyze_checker_decision")
    @patch("analysis.services.checker_processor.extract_checker_decisions")
    def test_persists_quality_policy_and_unclassified_exclusions(self, extract_mock, analyze_mock):
        meaningful = {"moves": [{"equity": 0.4}, {"equity": 0.1}]}
        cases = [
            ("0.019999", meaningful, "correct"),
            ("0.02", meaningful, "inaccuracy"),
            ("0.039999", meaningful, "inaccuracy"),
            ("0.04", meaningful, "error"),
            ("0.08", meaningful, "error"),
            ("0.080001", meaningful, "blunder"),
            ("0.0199999", meaningful, "inaccuracy"),
            ("0.0800004", meaningful, "error"),
            (None, meaningful, "unclassified"),
            ("0.5", {"moves": [{"equity": 0.4}]}, "unclassified"),
            ("0.5", {}, "unclassified"),
        ]
        extract_mock.return_value = [{} for _ in cases]
        analyze_mock.side_effect = [
            {"player": "white", "dice": [6, 3], "source_event_sequence": index,
             "equity_loss": loss, "raw_analysis": raw}
            for index, (loss, raw, _) in enumerate(cases, start=1)
        ]
        process_game_checker_decisions(game_analysis=self.game_analysis)
        self.assertEqual(
            list(self.white_game.decisions.values_list("classification", flat=True)),
            [expected for _, _, expected in cases],
        )

    def setUp(self):
        self.match_analysis = MatchAnalysis.objects.create(
            source_match_id="11111111-1111-1111-1111-111111111111",
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
        "analysis.services.checker_processor."
        "analyze_checker_decision"
    )
    @patch(
        "analysis.services.checker_processor."
        "extract_checker_decisions"
    )
    def test_persists_checker_decisions(
        self,
        extract_mock,
        analyze_mock,
    ):
        extract_mock.return_value = [
            {
                "player": "white",
                "start_sequence": 10,
                "end_sequence": 12,
            },
            {
                "player": "black",
                "start_sequence": 20,
                "end_sequence": 22,
            },
        ]

        analyze_mock.side_effect = [
            {
                "player": "white",
                "dice": [6, 3],
                "source_event_sequence": 12,
                "played_action": [{"from": 23, "to": 17}],
                "best_action": {"board": [1] * 26},
                "played_equity": 0.20,
                "best_equity": 0.30,
                "equity_loss": 0.10,
                "alternatives": [],
                "position_snapshot": {"turn": "white"},
                "raw_analysis": {"engine": "fake"},
            },
            {
                "player": "black",
                "dice": [5, 2],
                "source_event_sequence": 22,
                "played_action": [{"from": 0, "to": 5}],
                "best_action": {"board": [2] * 26},
                "played_equity": 0.15,
                "best_equity": 0.25,
                "equity_loss": 0.10,
                "alternatives": [],
                "position_snapshot": {"turn": "black"},
                "raw_analysis": {"engine": "fake"},
            },
        ]

        result = process_game_checker_decisions(
            game_analysis=self.game_analysis,
        )

        self.assertEqual(len(result), 2)
        self.assertEqual(
            DecisionAnalysis.objects.count(),
            2,
        )

        white = DecisionAnalysis.objects.get(
            player_game_analysis=self.white_game
        )

        black = DecisionAnalysis.objects.get(
            player_game_analysis=self.black_game
        )

        self.assertEqual(
            white.sequence_number,
            12,
        )
        self.assertEqual(
            black.sequence_number,
            22,
        )

        self.assertEqual(
            white.decision_type,
            DecisionAnalysis.DecisionType.CHECKER_MOVE,
        )

        self.assertEqual(
            white.classification,
            DecisionAnalysis.Classification.UNCLASSIFIED,
        )

        self.assertEqual(
            float(white.best_equity),
            0.30,
        )

        self.assertEqual(
            float(white.played_equity),
            0.20,
        )

        self.assertEqual(
            float(white.equity_loss),
            0.10,
        )

    @patch(
        "analysis.services.checker_processor."
        "analyze_checker_decision"
    )
    @patch(
        "analysis.services.checker_processor."
        "extract_checker_decisions"
    )
    def test_reprocessing_does_not_duplicate(
        self,
        extract_mock,
        analyze_mock,
    ):
        extract_mock.return_value = [
            {
                "player": "white",
                "start_sequence": 10,
                "end_sequence": 12,
            },
        ]

        analyze_mock.return_value = {
            "player": "white",
            "dice": [6, 3],
            "source_event_sequence": 12,
            "played_action": [],
            "best_action": {"board": [1] * 26},
            "played_equity": 0.20,
            "best_equity": 0.30,
            "equity_loss": 0.10,
            "alternatives": [],
            "position_snapshot": {},
            "raw_analysis": {},
        }

        process_game_checker_decisions(
            game_analysis=self.game_analysis,
        )

        process_game_checker_decisions(
            game_analysis=self.game_analysis,
        )

        self.assertEqual(
            DecisionAnalysis.objects.count(),
            1,
        )
