from unittest.mock import patch

from django.test import TestCase

from analysis.models import (
    GameAnalysis,
    MatchAnalysis,
    PlayerGameAnalysis,
    PlayerMatchAnalysis,
)
from analysis.services.match_processor import (
    MatchProcessingError,
    process_match_analysis,
)


class MatchProcessorTests(TestCase):
    @patch('analysis.services.match_processor.OpenSageEngine', side_effect=RuntimeError('engine unavailable'))
    def test_selected_depth_reaches_engine_and_initialization_failure_is_recorded(self, engine):
        self.match_analysis.eval_level = '3ply'
        self.match_analysis.save()
        with self.assertRaises(RuntimeError):
            process_match_analysis(match_analysis=self.match_analysis)
        engine.assert_called_once_with(eval_level='3ply')
        self.match_analysis.refresh_from_db()
        self.assertEqual(self.match_analysis.status, 'failed')

    def setUp(self):
        self.match_analysis = MatchAnalysis.objects.create(
            source_match_id="44444444-4444-4444-4444-444444444444",
            source_type=MatchAnalysis.SourceType.PRIVATE,
            input_payload={},
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

        for game in (self.game1, self.game2):
            PlayerGameAnalysis.objects.create(
                game_analysis=game,
                match_player_analysis=self.white_match,
            )

            PlayerGameAnalysis.objects.create(
                game_analysis=game,
                match_player_analysis=self.black_match,
            )

    @patch(
        "analysis.services.match_processor.process_game_analysis"
    )
    def test_processes_all_games_and_completes_match(
        self,
        process_game_mock,
    ):
        process_game_mock.side_effect = [
            {
                "checker_decisions": [object(), object()],
                "cube_decisions": [object()],
                "decisions_created": 3,
            },
            {
                "checker_decisions": [object()],
                "cube_decisions": [object(), object()],
                "decisions_created": 3,
            },
        ]

        result = process_match_analysis(
            match_analysis=self.match_analysis,
        )

        self.match_analysis.refresh_from_db()

        self.assertEqual(
            self.match_analysis.status,
            MatchAnalysis.Status.COMPLETED,
        )

        self.assertIsNotNone(
            self.match_analysis.started_at,
        )

        self.assertIsNotNone(
            self.match_analysis.completed_at,
        )

        self.assertIsNone(
            self.match_analysis.failed_at,
        )

        self.assertEqual(
            self.match_analysis.error_message,
            "",
        )

        self.assertEqual(
            process_game_mock.call_count,
            2,
        )

        self.assertEqual(
            self.match_analysis.raw_response[
                "games_analyzed"
            ],
            2,
        )

        self.assertEqual(
            self.match_analysis.raw_response[
                "decisions_analyzed"
            ],
            6,
        )

        self.assertEqual(
            len(
                self.match_analysis.raw_response[
                    "games"
                ]
            ),
            2,
        )

        self.assertEqual(
            result.pk,
            self.match_analysis.pk,
        )

    @patch(
        "analysis.services.match_processor.process_game_analysis"
    )
    def test_failure_marks_match_failed(
        self,
        process_game_mock,
    ):
        process_game_mock.side_effect = RuntimeError(
            "engine exploded"
        )

        with self.assertRaises(RuntimeError):
            process_match_analysis(
                match_analysis=self.match_analysis,
            )

        self.match_analysis.refresh_from_db()

        self.assertEqual(
            self.match_analysis.status,
            MatchAnalysis.Status.FAILED,
        )

        self.assertIsNotNone(
            self.match_analysis.failed_at,
        )

        self.assertIn(
            "engine exploded",
            self.match_analysis.error_message,
        )

    def test_already_processing_rejected(self):
        self.match_analysis.status = (
            MatchAnalysis.Status.PROCESSING
        )
        self.match_analysis.save(
            update_fields=["status"]
        )

        with self.assertRaises(
            MatchProcessingError
        ):
            process_match_analysis(
                match_analysis=self.match_analysis,
            )
