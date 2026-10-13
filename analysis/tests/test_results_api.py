from unittest.mock import patch

from django.test import TestCase, override_settings
from rest_framework.test import APIClient
from analysis.models import GameAnalysis, MatchAnalysis, PlayerGameAnalysis


@override_settings(ANALYSIS_API_TOKEN="test-results-token")
class ResultsAPITests(TestCase):
    @patch("analysis.engines.open_sage.OpenSageEngine.analyze_checker_play", side_effect=AssertionError("No engine rerun"))
    @patch("analysis.engines.open_sage.OpenSageEngine.analyze_cube_action", side_effect=AssertionError("No engine rerun"))
    def test_legacy_labels_and_counts_are_derived_on_read_without_writes(self, cube_mock, checker_mock):
        self.authorize()
        player = self.match.players.create(color="white", source_player_id=7, errors=99, blunders=99)
        game = GameAnalysis.objects.create(
            match_analysis=self.match, source_game_id="classification", game_number=1,
            winner="white", win_type="single",
        )
        player_game = PlayerGameAnalysis.objects.create(game_analysis=game, match_player_analysis=player)
        meaningful = {"equities": {"no_double": 0.1, "double_take": 0.3, "double_pass": 1}}
        cases = [
            ("0", meaningful, "correct"),
            ("0.019999", meaningful, "correct"),
            ("0.02", meaningful, "inaccuracy"),
            ("0.039999", meaningful, "inaccuracy"),
            ("0.04", meaningful, "error"),
            ("0.079999", meaningful, "error"),
            ("0.08", meaningful, "error"),
            ("0.080001", meaningful, "blunder"),
            (None, meaningful, "unclassified"),
            ("0.5", {}, "unclassified"),
        ]
        snapshot = {"points": [0] * 24, "bar": {"white": 0, "black": 0},
                    "home": {"white": 15, "black": 15}}
        for index, (loss, raw, _) in enumerate(cases, start=1):
            player_game.decisions.create(
                sequence_number=index, decision_type="no_double", equity_loss=loss,
                classification="blunder" if loss is None else "unclassified",
                raw_analysis=raw, position_snapshot=snapshot,
            )
        data = self.client.get(f'/api/v1/internal/results/{self.match.id}/').json()
        self.assertEqual([d["classification"] for d in data["games"][0]["decisions"]],
                         [expected for _, _, expected in cases])
        self.assertEqual(data["players"][0]["errors"], 3)
        self.assertEqual(data["players"][0]["blunders"], 1)
        listed = self.client.get('/api/v1/internal/results/', {"room": str(self.match.source_room_id)}).json()
        self.assertEqual(listed["matches"][0]["players"][0]["errors"], 3)
        self.assertEqual(listed["matches"][0]["players"][0]["blunders"], 1)
        player.refresh_from_db()
        self.assertEqual((player.errors, player.blunders), (99, 99))
        self.assertEqual(player_game.decisions.filter(classification="unclassified").count(), 9)
        self.assertEqual(player_game.decisions.filter(classification="blunder").count(), 1)
        cube_mock.assert_not_called()
        checker_mock.assert_not_called()

    def setUp(self):
        self.client = APIClient()
        self.match = MatchAnalysis.objects.create(
            source_match_id="44444444-4444-4444-4444-444444444444",
            source_room_id="11111111-1111-1111-1111-111111111111",
            source_type="quick", input_payload={"rules": {"target_points": 1}},
        )

    def authorize(self):
        self.client.credentials(HTTP_AUTHORIZATION="Bearer test-results-token")

    def test_names_and_depth_are_returned(self):
        self.authorize()
        self.match.input_payload['players'] = {'white': {'name': 'דנה'}}
        self.match.save()
        self.match.players.create(color='white', source_player_id=7)
        self.match.players.create(color='black', source_player_id=8)
        data = self.client.get(f'/api/v1/internal/results/{self.match.id}/').json()
        self.assertEqual({p['color']: p['name'] for p in data['players']}, {'white': 'דנה', 'black': ''})
        self.assertEqual(data['eval_level'], '1ply')

    def test_reanalysis_validates_and_queues_once_without_mutating_payload(self):
        self.authorize()
        self.match.status = 'completed'
        self.match.save()
        url = f'/api/v1/internal/results/{self.match.id}/'
        self.assertEqual(self.client.post(url, {'eval_level': 'rollout'}, format='json').status_code, 400)
        self.assertEqual(self.client.post(url, {'eval_level': '3ply'}, format='json').status_code, 202)
        self.match.refresh_from_db()
        self.assertEqual(self.match.status, 'pending')
        self.assertEqual(self.match.eval_level, '3ply')
        self.assertEqual(self.match.input_payload, {'rules': {'target_points': 1}})
        self.assertEqual(self.client.post(url, {'eval_level': '2ply'}, format='json').status_code, 409)

    def test_reanalysis_requires_token(self):
        response = self.client.post(f'/api/v1/internal/results/{self.match.id}/', {'eval_level': '2ply'}, format='json')
        self.assertEqual(response.status_code, 403)

    def test_reads_require_service_token(self):
        self.assertEqual(self.client.get('/api/v1/internal/results/').status_code, 403)
        self.client.credentials(HTTP_AUTHORIZATION="Bearer incorrect")
        self.assertEqual(self.client.get(f'/api/v1/internal/results/{self.match.id}/').status_code, 403)

    @override_settings(ANALYSIS_API_TOKEN="")
    def test_empty_token_is_never_accepted(self):
        from unittest.mock import patch
        with patch.dict('os.environ', {"ANALYSIS_API_TOKEN": ""}):
            self.client.credentials(HTTP_AUTHORIZATION="Bearer ")
            self.assertEqual(self.client.get('/api/v1/internal/results/').status_code, 403)

    def test_room_filter_and_safe_response(self):
        self.authorize()
        url = '/api/v1/internal/results/'
        self.assertEqual(self.client.get(url).json(), {"matches": [], "count": 0, "next_offset": None})
        data = self.client.get(url, {"room": str(self.match.source_room_id)}).json()
        self.assertEqual(len(data['matches']), 1)
        self.assertNotIn('input_payload', data['matches'][0])
        self.assertNotIn('source_player_id', str(data))

    def test_detail_and_missing_match(self):
        self.authorize()
        data = self.client.get(f'/api/v1/internal/results/{self.match.id}/').json()
        self.assertEqual(data['status'], 'pending')
        self.assertEqual(data['games'], [])
        self.assertEqual(self.client.get('/api/v1/internal/results/99999999-9999-9999-9999-999999999999/').status_code, 404)

    def test_five_item_pages_include_every_authorized_match_once(self):
        import uuid
        self.authorize()
        for _ in range(11):
            MatchAnalysis.objects.create(
                source_match_id=uuid.uuid4(), source_room_id=self.match.source_room_id,
                source_type="quick", input_payload={"rules": {"target_points": 3}},
            )
        MatchAnalysis.objects.create(
            source_match_id=uuid.uuid4(), source_room_id=uuid.uuid4(),
            source_type="quick", input_payload={},
        )
        url = '/api/v1/internal/results/'
        pages = [self.client.get(url, {
            "room": str(self.match.source_room_id), "limit": 5, "offset": offset,
        }).json() for offset in (0, 5, 10)]
        self.assertEqual([len(page["matches"]) for page in pages], [5, 5, 2])
        self.assertEqual([page["count"] for page in pages], [12, 12, 12])
        self.assertEqual([page["next_offset"] for page in pages], [5, 10, None])
        ids = [row["id"] for page in pages for row in page["matches"]]
        expected = [str(pk) for pk in MatchAnalysis.objects.filter(
            source_room_id=self.match.source_room_id,
        ).order_by("-created_at", "-id").values_list("id", flat=True)]
        self.assertEqual(ids, expected)
        self.assertEqual(len(set(ids)), 12)
        staff = self.client.get(url, {"staff": "1", "limit": 5}).json()
        self.assertEqual(staff["count"], 13)
        self.assertEqual(len(staff["matches"]), 5)

    def test_invalid_page_arguments_are_rejected(self):
        self.authorize()
        for params in ({"limit": 200}, {"offset": -1}, {"offset": "invalid"}):
            self.assertEqual(self.client.get('/api/v1/internal/results/', params).status_code, 400)

    def test_summary_page_does_not_materialize_full_history(self):
        from analysis.api.result_pages import summary_page
        self.authorize()
        self.match.input_payload = {
            "rules": {"target_points": 5}, "result": {"white_score": 5},
            "players": {"white": {"name": "Player"}},
            "games": [{"events": [{"private_history": "large" * 1000}]}],
        }
        self.match.raw_response = {"engine_debug": "large" * 1000}
        self.match.save()
        page, _, count, next_offset = summary_page([str(self.match.source_room_id)])
        self.assertEqual(count, 1)
        self.assertIsNone(next_offset)
        self.assertTrue({"input_payload", "raw_response"}.issubset(page[0].get_deferred_fields()))
        self.assertNotIn("games", page[0].summary_payload)
        self.assertEqual(page[0].summary_payload["rules"], {"target_points": 5})

    def test_false_beaver_does_not_turn_a_trivial_take_into_a_blunder(self):
        self.authorize()
        player = self.match.players.create(color="white", source_player_id=7)
        game = GameAnalysis.objects.create(
            match_analysis=self.match, source_game_id="trivial-take", game_number=1,
            winner="white", win_type="single",
        )
        player_game = PlayerGameAnalysis.objects.create(game_analysis=game, match_player_analysis=player)
        player_game.decisions.create(
            sequence_number=1, decision_type="take", equity_loss="0.5",
            raw_analysis={"is_beaver": False, "equities": {
                "no_double": 0.1, "double_take": 0.3, "double_pass": 0.3,
            }},
        )
        data = self.client.get('/api/v1/internal/results/', {"room": str(self.match.source_room_id)}).json()
        self.assertEqual(data["matches"][0]["players"][0]["errors"], 0)
        self.assertEqual(data["matches"][0]["players"][0]["blunders"], 0)
