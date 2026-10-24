import json
from unittest.mock import patch

from django.db import connection
from django.test import TransactionTestCase, override_settings
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from analysis.models import DecisionAnalysis, PlayerGameAnalysis, PlayerMatchAnalysis, RollLuckAnalysis
from analysis.services.game_processor import prepare_game_analysis, process_game_analysis
from analysis.services.match_processor import process_match_analysis
from analysis.tests import test_game_processor


class AnalysisPreparationTests(TransactionTestCase):
    setUp = test_game_processor.GameProcessorTests.setUp

    def snapshot(self):
        return {
            "decisions": list(DecisionAnalysis.objects.order_by("sequence_number").values(
                "sequence_number", "decision_type", "dice", "played_action", "best_action",
                "alternatives", "played_equity", "best_equity", "equity_loss", "classification",
                "position_snapshot", "raw_analysis",
            )),
            "luck": list(RollLuckAnalysis.objects.order_by("source_event_sequence").values(
                "source_event_sequence", "luck", "actual_equity", "average_equity", "ply", "raw_analysis",
            )),
            "players": list(PlayerGameAnalysis.objects.order_by("pk").values(
                "pr", "luck", "equity_lost", "errors", "blunders",
            )),
        }

    def test_preparation_has_no_writes_and_spooled_persistence_matches_existing_outputs(self):
        checker = {
            "player": "white", "source_event_sequence": 10, "dice": [6, 3],
            "played_equity": 0.1, "best_equity": 0.2, "equity_loss": 0.1,
            "raw_analysis": {"moves": [{"equity": 0.2}, {"equity": 0.1}]},
        }
        cube = {
            "player": "black", "source_event_sequence": 20, "decision_type": "no_double",
            "played_equity": 0.1, "best_equity": 0.3, "equity_loss": 0.2,
            "raw_analysis": {"equities": {"no_double": 0.1, "double_take": 0.3, "double_pass": 1}},
        }
        luck = {
            "player": "white", "source_event_sequence": 30, "dice": [5, 2],
            "is_opening_roll": False, "luck": 0.08, "actual_equity": 0.3,
            "average_equity": 0.22, "ply": 2, "level_label": "2-ply",
            "position_snapshot": {}, "raw_analysis": {},
        }
        patches = [
            patch("analysis.services.checker_processor.extract_checker_decisions", return_value=[{}]),
            patch("analysis.services.checker_processor.analyze_checker_decision", return_value=checker),
            patch("analysis.services.cube_processor.extract_cube_decisions", return_value=[{}]),
            patch("analysis.services.cube_processor.analyze_cube_decision", return_value=cube),
            patch("analysis.services.luck_processor.extract_luck_rolls", return_value=[{}]),
            patch("analysis.services.luck_processor.analyze_roll_luck", return_value=luck),
        ]
        mocks = [self.enterContext(mock) for mock in patches]
        process_game_analysis(game_analysis=self.game_analysis, engine=object())
        expected = self.snapshot()
        with CaptureQueriesContext(connection) as queries:
            prepared = prepare_game_analysis(game_analysis=self.game_analysis, engine=object())
        mutations = [query["sql"] for query in queries if query["sql"].lstrip().split(" ", 1)[0].upper()
                     in {"INSERT", "UPDATE", "DELETE"}]
        self.assertEqual(mutations, [])
        self.assertEqual(self.snapshot(), expected)
        for mock in (mocks[1], mocks[3], mocks[5]):
            self.assertEqual(mock.call_count, 2)
        # Match preparation uses the same JSON spool representation.
        result = process_game_analysis(
            game_analysis=self.game_analysis, prepared=json.loads(json.dumps(prepared)),
        )
        self.assertEqual(self.snapshot(), expected)
        self.assertEqual(result["decisions_created"], 2)
        self.assertEqual(result["rolls_analyzed"], 1)
        for mock in (mocks[1], mocks[3], mocks[5]):
            self.assertEqual(mock.call_count, 2, "Persistence must never rerun the engine")

    @override_settings(ANALYSIS_API_TOKEN="preparation-tests")
    def test_worker_evaluates_outside_atomic_and_allows_scope_writes_during_evaluation(self):
        client = APIClient()
        client.credentials(
            HTTP_AUTHORIZATION="Bearer preparation-tests", HTTP_X_ANALYSIS_SCOPE_BINDING="c" * 64,
        )
        def prepare(**kwargs):
            self.assertFalse(connection.in_atomic_block)
            # Listing a large library now needs this short scope write. It must
            # not run behind an analysis transaction held during engine work.
            response = client.post("/api/v1/internal/results/scopes/", {"room_count": 0}, format="json")
            self.assertEqual(response.status_code, 201)
            return {"checker": [], "cube": [], "luck": []}

        with patch("analysis.services.match_processor.prepare_game_analysis", side_effect=prepare) as evaluate, patch(
            "analysis.services.match_processor.OpenSageEngine",
        ), patch("analysis.services.match_processor.ProcessingHeartbeat"):
            process_match_analysis(match_analysis=self.match_analysis)
        evaluate.assert_called_once()
        self.match_analysis.refresh_from_db()
        self.assertEqual(self.match_analysis.status, "completed")
        self.assertEqual(PlayerMatchAnalysis.objects.filter(match_analysis=self.match_analysis).count(), 2)
