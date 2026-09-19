import copy
import uuid

from django.test import TestCase
from rest_framework.test import APIClient

from analysis.models import (
    DecisionAnalysis,
    GameAnalysis,
    MatchAnalysis,
    PlayerGameAnalysis,
    PlayerMatchAnalysis,
)

MATCHES_URL = "/api/v1/internal/matches/"


def make_payload(**overrides):
    payload = {
        "schema_version": 1,
        "match_id": str(uuid.uuid4()),
        "room_id": str(uuid.uuid4()),
        "source": {"type": "quick"},
        "players": {
            "white": {"player_id": 10},
            "black": {"player_id": 20},
        },
        "rules": {
            "format": "match",
            "target_points": 5,
            "time_control": "none",
            "doubling_enabled": True,
            "max_cube_value": 8,
            "jacoby": False,
            "beaver": False,
        },
        "result": {
            "winner": "white",
            "white_score": 5,
            "black_score": 3,
        },
        "games": [
            {
                "game_id": "game-1",
                "game_number": 1,
                "winner": "white",
                "win_type": "normal",
                "points_awarded": 1,
                "score_before": {"white": 0, "black": 0},
                "score_after": {"white": 1, "black": 0},
                "is_crawford": False,
                "events": [
                    {
                        "sequence": 0,
                        "event_type": "game_start",
                        "payload": {"game": 1},
                    },
                    {
                        "sequence": 1,
                        "event_type": "roll",
                        "player_color": "white",
                        "payload": {"dice": [3, 1]},
                    },
                ],
            },
            {
                "game_id": "game-2",
                "game_number": 2,
                "winner": "black",
                "win_type": "gammon",
                "points_awarded": 2,
                "score_before": {"white": 1, "black": 0},
                "score_after": {"white": 1, "black": 2},
                "is_crawford": False,
                "events": [
                    {
                        "sequence": 0,
                        "event_type": "game_start",
                        "payload": {"game": 2},
                    },
                    {
                        "sequence": 1,
                        "event_type": "roll",
                        "player_color": "black",
                        "payload": {"dice": [6, 6]},
                    },
                ],
            },
        ],
    }
    payload.update(overrides)
    return payload


def assert_no_rows(testcase):
    testcase.assertEqual(MatchAnalysis.objects.count(), 0)
    testcase.assertEqual(PlayerMatchAnalysis.objects.count(), 0)
    testcase.assertEqual(GameAnalysis.objects.count(), 0)
    testcase.assertEqual(PlayerGameAnalysis.objects.count(), 0)
    testcase.assertEqual(DecisionAnalysis.objects.count(), 0)


class ReceiveMatchTests(TestCase):
    def test_ai_opponent_is_ingested_without_a_fake_user_and_retry_is_idempotent(self):
        payload = make_payload(source={"type": "ai"}, players={
            "white": {"player_id": 10, "name": "Human"},
            "black": {"player_id": None, "kind": "ai", "name": "Open Sage"},
        })
        client = APIClient()
        self.assertEqual(client.post(MATCHES_URL, payload, format="json").status_code, 202)
        self.assertEqual(client.post(MATCHES_URL, payload, format="json").status_code, 200)
        bot = PlayerMatchAnalysis.objects.get(color="black")
        self.assertIsNone(bot.source_player_id)
        self.assertEqual(PlayerGameAnalysis.objects.filter(match_player_analysis=bot).count(), 2)

    def test_missing_human_identity_and_ai_in_normal_match_are_rejected(self):
        for source, black in [
            ("private", {"player_id": None}),
            ("private", {"player_id": None, "kind": "ai"}),
            ("ai", {"player_id": 20}),
            ("ai", {"player_id": 20, "kind": "ai"}),
        ]:
            with self.subTest(source=source, black=black):
                payload = make_payload(source={"type": source}, players={
                    "white": {"player_id": 10}, "black": black,
                })
                self.assertEqual(APIClient().post(MATCHES_URL, payload, format="json").status_code, 400)
        assert_no_rows(self)

    def setUp(self):
        self.client = APIClient()

    def test_successful_ingestion(self):
        payload = make_payload()
        response = self.client.post(MATCHES_URL, payload, format="json")

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.data["status"], "accepted")
        self.assertEqual(response.data["match_id"], payload["match_id"])
        self.assertIn("analysis_id", response.data)

        self.assertEqual(MatchAnalysis.objects.count(), 1)
        self.assertEqual(PlayerMatchAnalysis.objects.count(), 2)
        self.assertEqual(GameAnalysis.objects.count(), 2)
        self.assertEqual(PlayerGameAnalysis.objects.count(), 4)
        self.assertEqual(DecisionAnalysis.objects.count(), 0)

        analysis = MatchAnalysis.objects.get()
        self.assertEqual(str(analysis.source_match_id), payload["match_id"])
        self.assertEqual(analysis.status, "pending")

        white_pm = PlayerMatchAnalysis.objects.get(
            match_analysis=analysis, color="white"
        )
        black_pm = PlayerMatchAnalysis.objects.get(
            match_analysis=analysis, color="black"
        )
        self.assertEqual(white_pm.source_player_id, 10)
        self.assertEqual(black_pm.source_player_id, 20)

        for game in GameAnalysis.objects.all():
            links = list(
                PlayerGameAnalysis.objects.filter(
                    game_analysis=game
                ).select_related("match_player_analysis")
            )
            self.assertEqual(len(links), 2)
            colors = sorted(
                link.match_player_analysis.color for link in links
            )
            self.assertEqual(colors, ["black", "white"])
            by_color = {
                link.match_player_analysis.color: link for link in links
            }
            self.assertEqual(
                by_color["white"].match_player_analysis_id, white_pm.id
            )
            self.assertEqual(
                by_color["black"].match_player_analysis_id, black_pm.id
            )

    def test_game_event_isolation(self):
        payload = make_payload()
        response = self.client.post(MATCHES_URL, payload, format="json")
        self.assertEqual(response.status_code, 202)

        analysis = MatchAnalysis.objects.get()
        game1 = GameAnalysis.objects.get(
            match_analysis=analysis, source_game_id="game-1"
        )
        game2 = GameAnalysis.objects.get(
            match_analysis=analysis, source_game_id="game-2"
        )

        self.assertEqual(game1.input_events, payload["games"][0]["events"])
        self.assertEqual(game2.input_events, payload["games"][1]["events"])
        self.assertNotEqual(game1.input_events, game2.input_events)
        # Game 2 payload must not leak into game 1 and vice versa.
        game1_dice = [
            event["payload"].get("dice")
            for event in game1.input_events
            if isinstance(event.get("payload"), dict) and "dice" in event["payload"]
        ]
        game2_dice = [
            event["payload"].get("dice")
            for event in game2.input_events
            if isinstance(event.get("payload"), dict) and "dice" in event["payload"]
        ]
        self.assertEqual(game1_dice, [[3, 1]])
        self.assertEqual(game2_dice, [[6, 6]])

    def test_identical_retry(self):
        payload = make_payload()
        first = self.client.post(MATCHES_URL, payload, format="json")
        self.assertEqual(first.status_code, 202)

        second = self.client.post(MATCHES_URL, payload, format="json")
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.data["status"], "already_exists")
        self.assertEqual(second.data["analysis_id"], first.data["analysis_id"])
        self.assertEqual(second.data["match_id"], first.data["match_id"])

        self.assertEqual(MatchAnalysis.objects.count(), 1)
        self.assertEqual(PlayerMatchAnalysis.objects.count(), 2)
        self.assertEqual(GameAnalysis.objects.count(), 2)
        self.assertEqual(PlayerGameAnalysis.objects.count(), 4)
        self.assertEqual(DecisionAnalysis.objects.count(), 0)

    def test_conflicting_retry(self):
        payload = make_payload()
        first = self.client.post(MATCHES_URL, payload, format="json")
        self.assertEqual(first.status_code, 202)

        original_payload = MatchAnalysis.objects.get().input_payload

        conflicting = copy.deepcopy(payload)
        conflicting["result"] = {
            "winner": "black",
            "white_score": 1,
            "black_score": 5,
        }

        response = self.client.post(MATCHES_URL, conflicting, format="json")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["status"], "conflict")
        self.assertEqual(response.data["code"], "match_payload_conflict")
        self.assertEqual(response.data["match_id"], payload["match_id"])

        # Original stored payload must remain unchanged.
        analysis = MatchAnalysis.objects.get()
        self.assertEqual(analysis.input_payload, original_payload)
        self.assertEqual(MatchAnalysis.objects.count(), 1)
        self.assertEqual(GameAnalysis.objects.count(), 2)

    def test_unsupported_schema_version(self):
        payload = make_payload(schema_version=2)
        response = self.client.post(MATCHES_URL, payload, format="json")
        self.assertEqual(response.status_code, 400)
        assert_no_rows(self)

    def test_duplicate_game_id(self):
        payload = make_payload()
        payload["games"][1]["game_id"] = payload["games"][0]["game_id"]
        response = self.client.post(MATCHES_URL, payload, format="json")
        self.assertEqual(response.status_code, 400)
        assert_no_rows(self)

    def test_duplicate_game_number(self):
        payload = make_payload()
        payload["games"][1]["game_number"] = payload["games"][0]["game_number"]
        response = self.client.post(MATCHES_URL, payload, format="json")
        self.assertEqual(response.status_code, 400)
        assert_no_rows(self)

    def test_unlimited_max_cube_value_succeeds(self):
        payload = make_payload()
        payload["rules"]["max_cube_value"] = 0
        response = self.client.post(MATCHES_URL, payload, format="json")
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.data["status"], "accepted")

    def test_invalid_max_cube_value_rejected(self):
        payload = make_payload()
        payload["rules"]["max_cube_value"] = 6
        response = self.client.post(MATCHES_URL, payload, format="json")
        self.assertEqual(response.status_code, 400)
        assert_no_rows(self)

    def test_same_player_on_both_colors(self):
        payload = make_payload()
        payload["players"] = {
            "white": {"player_id": 10},
            "black": {"player_id": 10},
        }
        response = self.client.post(MATCHES_URL, payload, format="json")
        self.assertEqual(response.status_code, 400)
        assert_no_rows(self)
