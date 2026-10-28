from copy import deepcopy
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.db import connection
from rest_framework.test import APIClient

from analysis.models import MatchAnalysis


@override_settings(ANALYSIS_API_TOKEN="test-record-token")
class MatchRecordTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.room_id = "11111111-1111-1111-1111-111111111111"
        self.payload = {
            "players": {
                "white": {"name": "דנה", "player_id": 7},
                "black": {"name": "Opponent", "player_id": 8},
            },
            "rules": {"format": "match", "target_points": 5, "internal": "private"},
            "result": {"winner": "black", "white_score": 1, "black_score": 5},
            "games": [{
                "game_id": "game-1", "game_number": 1,
                "winner": "black", "win_type": "single", "points_awarded": 1,
                "score_before": {"white": 0, "black": 0},
                "score_after": {"white": 0, "black": 1}, "is_crawford": False,
                "events": [
                    {"sequence": 2, "event_type": "roll", "player_color": "white",
                     "created_at": "2026-10-28T09:00:00Z",
                     "payload": {"phase": "moving", "turn": "white", "dice": [6, 1]}},
                    {"sequence": 4, "event_type": "move", "player_color": "white",
                     "payload": {"lastMove": [{"from": 23, "to": 17, "debug": "private"}],
                                 "remaining": [1], "points": [0] * 24,
                                 "bar": {"white": 0, "black": 0, "private": 9}}},
                    {"sequence": 5, "event_type": "undo", "player_color": "white",
                     "payload": {"lastMove": [], "remaining": [6, 1]}},
                    # A partial turn must survive even without an end_turn event.
                    {"sequence": 6, "event_type": "move", "player_color": "white",
                     "payload": {"lastMove": [{"from": 23, "to": 22}], "remaining": [6]}},
                    {"sequence": 8, "event_type": "resign", "player_color": "white",
                     "payload": {"phase": "game_over", "winner": "black",
                                 "gameEndReason": "give_up", "gameEndPoints": 1,
                                 "clock": {"white": 42}, "moveHistory": [{"private": "data"}]}}
                ],
            }],
        }
        self.match = MatchAnalysis.objects.create(
            source_match_id="44444444-4444-4444-4444-444444444444",
            source_room_id=self.room_id, source_type="quick", status="failed",
            input_payload=self.payload, raw_response={"private": "engine response"},
        )
        self.url = f"/api/v1/internal/results/{self.match.pk}/record/"

    def authorize(self):
        self.client.credentials(HTTP_AUTHORIZATION="Bearer test-record-token")

    def test_record_preserves_source_events_without_analysis_or_private_fields(self):
        self.authorize()
        original = deepcopy(self.payload)
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get(self.url, {"room": self.room_id})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(queries), 1)
        self.assertNotIn("raw_response", queries[0]["sql"])
        self.assertIn("source_room_id", queries[0]["sql"])
        data = response.json()
        self.assertEqual(data["match_id"], str(self.match.source_match_id))
        self.assertEqual(data["players"], {"white": {"name": "דנה"}, "black": {"name": "Opponent"}})
        self.assertEqual(data["rules"], {"format": "match", "target_points": 5})
        game = data["games"][0]
        self.assertEqual(game["score_after"], {"white": 0, "black": 1})
        self.assertEqual((game["winner"], game["points_awarded"]), ("black", 1))
        self.assertEqual([event["sequence"] for event in game["events"]], [2, 4, 5, 6, 8])
        self.assertEqual([event["event_type"] for event in game["events"]],
                         ["roll", "move", "undo", "move", "resign"])
        self.assertEqual(game["events"][1]["payload"]["lastMove"], [{"from": 23, "to": 17}])
        self.assertEqual(game["events"][2]["payload"]["lastMove"], [])
        self.assertEqual(game["events"][3]["payload"]["remaining"], [6])
        self.assertEqual(game["events"][4]["payload"]["gameEndReason"], "give_up")
        self.assertNotIn("private", str(data))
        self.assertNotIn("player_id", str(data))
        self.assertNotIn("clock", str(data))
        self.assertNotIn("moveHistory", str(data))
        self.assertEqual(response["Cache-Control"], "private, no-store")
        self.match.refresh_from_db()
        self.assertEqual(self.match.input_payload, original)
        self.assertEqual(self.match.status, "failed")

    def test_auto_ending_board_and_cube_events_are_preserved(self):
        self.authorize()
        events = self.payload["games"][0]["events"]
        events.extend([
            {"sequence": 9, "event_type": "move", "player_color": "black",
             "payload": {"lastMove": None, "points": [-1] + [0] * 23,
                         "bar": {"white": 1, "black": 0}, "home": {"white": 0, "black": 1}}},
            {"sequence": 10, "event_type": "double", "player_color": "black",
             "payload": {"cube": 2, "cubeOwner": "black", "doubleOfferedBy": "black"}},
            {"sequence": 11, "event_type": "double_response", "player_color": "white",
             "payload": {"cube": 4, "cubeOwner": "white", "phase": "rolling"}},
        ])
        self.match.input_payload = self.payload
        self.match.save(update_fields=["input_payload"])
        data = self.client.get(self.url, {"room": self.room_id}).json()
        returned = data["games"][0]["events"]
        self.assertIsNone(returned[-3]["payload"]["lastMove"])
        self.assertEqual(returned[-3]["payload"]["points"], [-1] + [0] * 23)
        self.assertEqual(returned[-2:], events[-2:])

    def test_authentication_and_room_scope_are_required(self):
        self.assertEqual(self.client.get(self.url, {"room": self.room_id}).status_code, 403)
        self.authorize()
        for params in ({}, {"room": "bad"}, {"room": "22222222-2222-2222-2222-222222222222"}):
            with patch("analysis.api.match_record.source_record") as serialize:
                response = self.client.get(self.url, params)
            self.assertEqual(response.status_code, 404)
            self.assertEqual(response["Cache-Control"], "private, no-store")
            serialize.assert_not_called()

    def test_trusted_staff_read_and_missing_record(self):
        self.authorize()
        self.assertEqual(self.client.get(self.url, {"staff": "1"}).status_code, 200)
        self.assertEqual(self.client.get(
            "/api/v1/internal/results/99999999-9999-9999-9999-999999999999/record/",
            {"room": self.room_id},
        ).status_code, 404)
        self.assertEqual(self.client.post(self.url, {"room": self.room_id}).status_code, 405)
