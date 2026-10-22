import uuid
from decimal import Decimal

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from analysis.models import MatchAnalysis


@override_settings(ANALYSIS_API_TOKEN="performance-test-token")
class PerformanceAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def add_analysis(self, *, decisions, loss, player=7, status="completed"):
        match = MatchAnalysis.objects.create(
            source_match_id=uuid.uuid4(), source_type="quick", status=status,
            input_payload={"players": {"white": {"name": "same-name"}}},
        )
        match.players.create(color="white", source_player_id=player,
                             pr=Decimal(loss) * 500 / decisions,
                             decisions_analyzed=decisions, equity_lost=loss)

    def test_pr_weights_decisions_and_excludes_unfinished_and_other_players(self):
        self.add_analysis(decisions=2, loss="0.04")
        self.add_analysis(decisions=18, loss="0.18")
        self.add_analysis(decisions=1, loss="0.9", status="processing")
        self.add_analysis(decisions=1, loss="0.8", player=9)
        self.client.credentials(HTTP_AUTHORIZATION="Bearer performance-test-token")
        response = self.client.get("/api/v1/internal/performance/", {"player": [7, 8]})
        self.assertEqual(response.status_code, 200)
        data = response.json()["players"]
        self.assertEqual(Decimal(data["7"]["pr"]), Decimal("5.5"))
        self.assertEqual((data["7"]["matches"], data["7"]["decisions"]), (2, 20))
        self.assertEqual(data["8"], {"pr": None, "matches": 0, "decisions": 0})
        self.assertNotIn("9", data)
        self.assertEqual(response["Cache-Control"], "private, no-store")

    def test_requires_trusted_token_and_bounded_player_ids(self):
        self.assertEqual(self.client.get("/api/v1/internal/performance/", {"player": 7}).status_code, 403)
        self.client.credentials(HTTP_AUTHORIZATION="Bearer performance-test-token")
        for ids in ([], [0], ["bad"], [1, 2, 3]):
            with self.subTest(ids=ids):
                self.assertEqual(self.client.get("/api/v1/internal/performance/", {"player": ids}).status_code, 400)
