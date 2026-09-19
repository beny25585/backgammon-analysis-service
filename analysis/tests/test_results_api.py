from django.test import TestCase, override_settings
from rest_framework.test import APIClient
from analysis.models import MatchAnalysis


@override_settings(ANALYSIS_API_TOKEN="test-results-token")
class ResultsAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.match = MatchAnalysis.objects.create(
            source_match_id="44444444-4444-4444-4444-444444444444",
            source_room_id="11111111-1111-1111-1111-111111111111",
            source_type="quick", input_payload={"rules": {"target_points": 1}},
        )

    def authorize(self):
        self.client.credentials(HTTP_AUTHORIZATION="Bearer test-results-token")

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
        self.assertEqual(self.client.get(url).json(), {"matches": []})
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
