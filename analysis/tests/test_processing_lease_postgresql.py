"""Run against an explicitly configured disposable PostgreSQL test database.

The memory-only review runner skips these tests. Barriers/events coordinate
independent connections; these do not use a timing sleep to induce a race.
"""
from datetime import timedelta
from queue import Queue
from threading import Barrier, Event, Thread
from unittest import skipUnless
from unittest.mock import patch
import uuid

from django.db import close_old_connections, connection, connections, transaction
from django.test import TransactionTestCase
from django.utils import timezone

from analysis.models import DecisionAnalysis, GameAnalysis, MatchAnalysis, PlayerGameAnalysis, PlayerMatchAnalysis
from analysis.services.match_processor import MatchProcessingError, process_match_analysis
from analysis.services.processing_lease import LeaseLost, claim_analysis, renew_analysis


@skipUnless(connection.vendor == "postgresql", "Requires a disposable PostgreSQL test database")
class PostgreSQLProcessingLeaseTests(TransactionTestCase):
    def setUp(self):
        self.match = MatchAnalysis.objects.create(source_match_id=uuid.uuid4(), source_type="quick", input_payload={})
        self.game = GameAnalysis.objects.create(
            match_analysis=self.match, source_game_id="concurrent-game", game_number=1,
            winner="white", win_type="single",
        )
        player = PlayerMatchAnalysis.objects.create(match_analysis=self.match, source_player_id=7, color="white")
        self.player_game = PlayerGameAnalysis.objects.create(game_analysis=self.game, match_player_analysis=player)

    def test_two_independent_workers_have_one_durable_claim(self):
        barrier = Barrier(3)
        outcomes = Queue()
        def worker():
            close_old_connections()
            try:
                match = MatchAnalysis.objects.get(pk=self.match.pk)
                barrier.wait(timeout=10)
                try:
                    outcomes.put(("claimed", claim_analysis(match)))
                except LeaseLost:
                    outcomes.put(("lost", None))
            except BaseException as exc:
                outcomes.put(("error", exc))
            finally:
                connections["default"].close()
        workers = [Thread(target=worker, daemon=True) for _ in range(2)]
        for worker_thread in workers:
            worker_thread.start()
        barrier.wait(timeout=10)
        for worker_thread in workers:
            worker_thread.join(timeout=10)
            self.assertFalse(worker_thread.is_alive())
        results = [outcomes.get_nowait() for _ in range(2)]
        self.assertEqual(sorted(item[0] for item in results), ["claimed", "lost"])
        self.match.refresh_from_db()
        self.assertEqual(self.match.processing_token, next(value for kind, value in results if kind == "claimed"))

    def test_independent_renewal_succeeds_without_processing_parent_lock(self):
        token = claim_analysis(self.match)
        ready = Event()
        outcomes = Queue()
        def heartbeat_connection():
            close_old_connections()
            try:
                outcomes.put(renew_analysis(self.match.pk, token))
            except BaseException as exc:
                outcomes.put(exc)
            finally:
                ready.set()
                connections["default"].close()
        # Even this ordinary read transaction must not prevent a separate
        # connection from renewing ownership. Engine preparation has no atomic
        # block, and is therefore less restrictive than this control.
        with transaction.atomic():
            MatchAnalysis.objects.get(pk=self.match.pk)
            worker = Thread(target=heartbeat_connection, daemon=True)
            worker.start()
            self.assertTrue(ready.wait(timeout=10))
            self.assertEqual(outcomes.get_nowait(), 1)
        worker.join(timeout=10)
        self.assertFalse(worker.is_alive())

    def test_reclaimed_owner_fences_and_rolls_back_in_flight_derived_writes(self):
        derived_written, replacement_ready = Event(), Event()
        outcomes = Queue()
        player_game_id = self.player_game.pk
        def derived(**kwargs):
            DecisionAnalysis.objects.create(
                player_game_analysis_id=player_game_id, sequence_number=1, decision_type="checker_move",
            )
            derived_written.set()
            if not replacement_ready.wait(timeout=10):
                raise RuntimeError("Replacement worker did not claim the expired lease")
            return {"checker_decisions": [], "cube_decisions": [], "decisions_created": 1}
        def stale_worker():
            close_old_connections()
            try:
                process_match_analysis(match_analysis=MatchAnalysis.objects.get(pk=self.match.pk))
                outcomes.put("unexpected completion")
            except MatchProcessingError:
                outcomes.put("fenced")
            except BaseException as exc:
                outcomes.put(exc)
            finally:
                connections["default"].close()
        with patch("analysis.services.match_processor.OpenSageEngine"), patch(
            "analysis.services.match_processor.prepare_game_analysis", return_value={"checker": [], "cube": [], "luck": []},
        ), patch("analysis.services.match_processor.process_game_analysis", side_effect=derived), patch(
            "analysis.services.match_processor.ProcessingHeartbeat",
        ):
            worker = Thread(target=stale_worker, daemon=True)
            worker.start()
            try:
                self.assertTrue(derived_written.wait(timeout=10))
                MatchAnalysis.objects.filter(pk=self.match.pk).update(lease_expires_at=timezone.now() - timedelta(seconds=1))
                replacement = MatchAnalysis.objects.get(pk=self.match.pk)
                token = claim_analysis(replacement)
                MatchAnalysis.objects.filter(pk=self.match.pk, processing_token=token).update(raw_response={"replacement": True})
            finally:
                replacement_ready.set()
                worker.join(timeout=10)
            self.assertFalse(worker.is_alive())
        self.assertEqual(outcomes.get_nowait(), "fenced")
        self.match.refresh_from_db()
        self.assertEqual(self.match.processing_token, token)
        self.assertEqual(self.match.raw_response, {"replacement": True})
        self.assertEqual(self.match.status, "processing")
        self.assertFalse(self.player_game.decisions.exists())
