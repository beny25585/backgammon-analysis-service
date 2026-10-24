from datetime import timedelta
from io import StringIO
from unittest.mock import patch
import uuid

from django.core.management import call_command
from django.test import TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from analysis.models import GameAnalysis, MatchAnalysis, PlayerGameAnalysis, PlayerMatchAnalysis
from analysis.services.match_processor import MatchProcessingError, process_match_analysis
from analysis.services.processing_lease import LeaseLost, claim_analysis, renew_analysis


class ProcessingLeaseTests(TransactionTestCase):
    def setUp(self):
        # Worker commands refresh their database connections, so run outside
        # TestCase's surrounding transaction, as the real worker does.
        self.enterContext(patch("analysis.services.match_processor.ProcessingHeartbeat"))
        self.match = MatchAnalysis.objects.create(
            source_match_id=uuid.uuid4(), source_room_id=uuid.uuid4(),
            source_type="quick", input_payload={},
        )
        self.game = GameAnalysis.objects.create(
            match_analysis=self.match, source_game_id="lease-game", game_number=1,
            winner="white", win_type="single", points_awarded=1,
        )
        self.player = PlayerMatchAnalysis.objects.create(match_analysis=self.match, source_player_id=7, color="white")
        self.player_game = PlayerGameAnalysis.objects.create(game_analysis=self.game, match_player_analysis=self.player)

    @patch("analysis.services.match_processor.OpenSageEngine")
    @patch("analysis.services.match_processor.process_game_analysis", return_value={
        "checker_decisions": [], "cube_decisions": [], "decisions_created": 0,
    })
    def test_worker_reclaims_expired_claim_and_finishes(self, game, engine):
        old_token = claim_analysis(self.match)
        MatchAnalysis.objects.filter(pk=self.match.pk).update(lease_expires_at=timezone.now() - timedelta(seconds=1))
        call_command("process_analyses", once=True, stderr=StringIO())
        self.match.refresh_from_db()
        self.assertEqual(self.match.status, "completed")
        self.assertIsNone(self.match.processing_token)
        self.assertIsNone(self.match.lease_expires_at)
        self.assertNotEqual(old_token, self.match.processing_token)
        game.assert_called_once()

    def test_atomic_claim_has_timing_metadata_and_rejects_duplicate_or_active_claim(self):
        token = claim_analysis(self.match)
        with self.assertRaises(LeaseLost):
            claim_analysis(self.match)
        self.match.refresh_from_db()
        self.assertEqual(self.match.processing_token, token)
        self.assertEqual(self.match.status, "processing")
        self.assertIsNotNone(self.match.started_at)
        self.assertGreater(self.match.lease_expires_at, timezone.now())
        with self.assertRaises(LeaseLost):
            claim_analysis(self.match)

    def test_heartbeat_renews_only_current_owner(self):
        token = claim_analysis(self.match)
        past = timezone.now() - timedelta(seconds=1)
        MatchAnalysis.objects.filter(pk=self.match.pk).update(lease_expires_at=past)
        self.assertEqual(renew_analysis(self.match.pk, uuid.uuid4()), 0)
        self.match.refresh_from_db()
        self.assertEqual(self.match.lease_expires_at, past)
        self.assertEqual(renew_analysis(self.match.pk, token), 1)
        self.match.refresh_from_db()
        self.assertGreater(self.match.lease_expires_at, timezone.now())

    @patch("analysis.management.commands.process_analyses.process_match_analysis")
    def test_worker_skips_active_lease(self, process):
        claim_analysis(self.match)
        call_command("process_analyses", once=True, stderr=StringIO())
        process.assert_not_called()

    def test_legacy_interrupted_processing_is_recoverable(self):
        MatchAnalysis.objects.filter(pk=self.match.pk).update(
            status="processing", started_at=timezone.now() - timedelta(hours=1),
        )
        self.match.refresh_from_db()
        token = claim_analysis(self.match)
        self.match.refresh_from_db()
        self.assertEqual(self.match.processing_token, token)

    def test_hard_interruption_after_claim_retains_recoverable_lease(self):
        with patch.object(self.match, "refresh_from_db", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                process_match_analysis(match_analysis=self.match)
        self.match.refresh_from_db()
        self.assertEqual(self.match.status, "processing")
        self.assertIsNotNone(self.match.processing_token)
        self.assertIsNotNone(self.match.lease_expires_at)

    def _replace_owner(self, **kwargs):
        self.replacement_token = uuid.uuid4()
        MatchAnalysis.objects.filter(pk=self.match.pk).update(
            processing_token=self.replacement_token, raw_response={"replacement": True},
        )
        return object()

    def test_stale_completion_rolls_back_child_writes_and_preserves_replacement(self):
        original_errors = self.player.errors
        def derived_writes(**kwargs):
            self.player_game.decisions.create(sequence_number=1, decision_type="checker_move")
            PlayerMatchAnalysis.objects.filter(pk=self.player.pk).update(errors=99)
            PlayerGameAnalysis.objects.filter(pk=self.player_game.pk).update(luck=99)
            return {"checker_decisions": [], "cube_decisions": [], "decisions_created": 1}

        with patch("analysis.services.match_processor.OpenSageEngine", side_effect=self._replace_owner), patch(
            "analysis.services.match_processor.process_game_analysis", side_effect=derived_writes,
        ):
            with self.assertRaises(MatchProcessingError):
                process_match_analysis(match_analysis=self.match)
        self.match.refresh_from_db()
        self.player.refresh_from_db()
        self.player_game.refresh_from_db()
        self.assertEqual(self.match.processing_token, self.replacement_token)
        self.assertEqual(self.match.raw_response, {"replacement": True})
        self.assertEqual(self.match.status, "processing")
        self.assertEqual(self.player.errors, original_errors)
        self.assertNotEqual(self.player_game.luck, 99)
        self.assertFalse(self.player_game.decisions.exists())

    def test_stale_failure_does_not_overwrite_replacement(self):
        def replacement_then_error(**kwargs):
            self._replace_owner()
            raise RuntimeError("old worker failed")

        with patch("analysis.services.match_processor.OpenSageEngine", side_effect=replacement_then_error):
            with self.assertRaises(RuntimeError):
                process_match_analysis(match_analysis=self.match)
        self.match.refresh_from_db()
        self.assertEqual(self.match.processing_token, self.replacement_token)
        self.assertEqual(self.match.raw_response, {"replacement": True})
        self.assertEqual(self.match.status, "processing")
        self.assertEqual(self.match.error_message, "")

    @override_settings(ANALYSIS_API_TOKEN="lease-tests")
    def test_reanalysis_recovers_expired_but_rejects_active_ownership(self):
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION="Bearer lease-tests")
        claim_analysis(self.match)
        path = f"/api/v1/internal/results/{self.match.pk}/"
        self.assertEqual(client.post(path, {"eval_level": "3ply"}, format="json").status_code, 409)
        MatchAnalysis.objects.filter(pk=self.match.pk).update(lease_expires_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(client.post(path, {"eval_level": "3ply"}, format="json").status_code, 202)
        self.match.refresh_from_db()
        self.assertEqual(self.match.status, "pending")
        self.assertIsNone(self.match.processing_token)
        self.assertEqual(self.match.eval_level, "3ply")
