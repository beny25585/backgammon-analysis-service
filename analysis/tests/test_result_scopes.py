from datetime import timedelta
import uuid

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from analysis.api.result_scopes import cleanup_expired_scopes
from analysis.models import MatchAnalysis, ResultAccessRoom, ResultAccessScope


@override_settings(ANALYSIS_API_TOKEN="scope-tests")
class ResultScopeTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.client.credentials(
            HTTP_AUTHORIZATION="Bearer scope-tests", HTTP_X_ANALYSIS_SCOPE_BINDING="a" * 64,
        )

    def create_scope(self, rooms, *, finalize=True):
        created = self.client.post("/api/v1/internal/results/scopes/", {"room_count": len(rooms)}, format="json")
        self.assertEqual(created.status_code, 201)
        scope_id = created.json()["id"]
        path = f"/api/v1/internal/results/scopes/{scope_id}/"
        for offset in range(0, len(rooms), 128):
            uploaded = self.client.post(path, {"offset": offset, "rooms": rooms[offset:offset + 128]}, format="json")
            self.assertEqual(uploaded.status_code, 200)
        if finalize:
            self.assertEqual(self.client.post(path, {"finalize": True}, format="json").status_code, 200)
        return scope_id

    def results(self, scope_id, **params):
        return self.client.get("/api/v1/internal/results/", {"scope": scope_id, "limit": 5, **params})

    def test_large_scope_has_exact_authorized_count_and_order_before_five_item_pages(self):
        rooms = [str(uuid.uuid4()) for _ in range(1100)]
        authorized = [MatchAnalysis(
            source_match_id=uuid.uuid4(), source_room_id=room, source_type="quick", input_payload={},
        ) for room in rooms[:12]]
        MatchAnalysis.objects.bulk_create(authorized)
        MatchAnalysis.objects.bulk_create([MatchAnalysis(
            source_match_id=uuid.uuid4(), source_room_id=uuid.uuid4(), source_type="quick", input_payload={},
        ) for _ in range(40)])
        scope_id = self.create_scope(rooms)
        pages = [self.results(scope_id, offset=offset).json() for offset in (0, 5, 10)]
        self.assertEqual([page["count"] for page in pages], [12, 12, 12])
        self.assertEqual([page["next_offset"] for page in pages], [5, 10, None])
        self.assertEqual([len(page["matches"]) for page in pages], [5, 5, 2])
        expected = [str(pk) for pk in MatchAnalysis.objects.filter(source_room_id__in=rooms)
                    .order_by("-created_at", "-id").values_list("pk", flat=True)]
        self.assertEqual([match["id"] for page in pages for match in page["matches"]], expected)
        self.assertEqual(ResultAccessRoom.objects.filter(scope_id=scope_id).count(), 1100)
        self.assertEqual(self.client.delete(f"/api/v1/internal/results/scopes/{scope_id}/").status_code, 204)
        self.assertFalse(ResultAccessRoom.objects.filter(scope_id=scope_id).exists())

    def test_unfinished_scope_and_incomplete_finalization_are_rejected(self):
        created = self.client.post("/api/v1/internal/results/scopes/", {"room_count": 2}, format="json")
        scope_id = created.json()["id"]
        path = f"/api/v1/internal/results/scopes/{scope_id}/"
        self.assertEqual(self.client.post(path, {"offset": 0, "rooms": [str(uuid.uuid4())]}, format="json").status_code, 200)
        self.assertEqual(self.client.post(path, {"finalize": True}, format="json").status_code, 409)
        self.assertEqual(self.results(scope_id).status_code, 404)

    def test_scope_binding_cannot_be_reused_by_another_session_or_caller(self):
        scope_id = self.create_scope([str(uuid.uuid4())])
        path = f"/api/v1/internal/results/scopes/{scope_id}/"
        self.client.credentials(HTTP_AUTHORIZATION="Bearer scope-tests", HTTP_X_ANALYSIS_SCOPE_BINDING="b" * 64)
        self.assertEqual(self.results(scope_id).status_code, 404)
        self.assertEqual(self.client.post(path, {"finalize": True}, format="json").status_code, 404)
        self.assertEqual(self.client.delete(path).status_code, 404)
        with override_settings(ANALYSIS_API_TOKEN="rotated-credential"):
            self.client.credentials(HTTP_AUTHORIZATION="Bearer rotated-credential", HTTP_X_ANALYSIS_SCOPE_BINDING="a" * 64)
            self.assertEqual(self.results(scope_id).status_code, 404)

    def test_scope_requires_service_authentication_and_binding(self):
        self.client.credentials()
        self.assertEqual(self.client.post("/api/v1/internal/results/scopes/", {"room_count": 0}, format="json").status_code, 403)
        self.client.credentials(HTTP_AUTHORIZATION="Bearer scope-tests")
        self.assertEqual(self.client.post("/api/v1/internal/results/scopes/", {"room_count": 0}, format="json").status_code, 400)

    def test_expired_scopes_are_unreadable_and_cleanup_deletes_membership(self):
        scope_id = self.create_scope([str(uuid.uuid4())])
        ResultAccessScope.objects.filter(pk=scope_id).update(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self.results(scope_id).status_code, 404)
        self.assertEqual(cleanup_expired_scopes(), 1)
        self.assertFalse(ResultAccessRoom.objects.exists())

    def test_chunk_bounds_order_duplicates_and_immutability(self):
        created = self.client.post("/api/v1/internal/results/scopes/", {"room_count": 2}, format="json")
        path = f'/api/v1/internal/results/scopes/{created.json()["id"]}/'
        room = str(uuid.uuid4())
        for payload in (
            {"offset": 0, "rooms": [str(uuid.uuid4()) for _ in range(129)]},
            {"offset": 1, "rooms": [room]},
            {"offset": 0, "rooms": [room, room]},
        ):
            self.assertEqual(self.client.post(path, payload, format="json").status_code, 400)
        self.assertEqual(self.client.post(path, {"offset": 0, "rooms": [room]}, format="json").status_code, 200)
        self.assertEqual(self.client.post(path, {"offset": 1, "rooms": [room]}, format="json").status_code, 400)
        self.assertEqual(self.client.post(path, {"offset": 1, "rooms": [str(uuid.uuid4())]}, format="json").status_code, 200)
        self.assertEqual(self.client.post(path, {"finalize": True}, format="json").status_code, 200)
        self.assertEqual(self.client.post(path, {"offset": 2, "rooms": [str(uuid.uuid4())]}, format="json").status_code, 409)

    def test_empty_scope_never_grants_all_matches_and_mixed_filters_are_rejected(self):
        MatchAnalysis.objects.create(source_match_id=uuid.uuid4(), source_room_id=uuid.uuid4(), source_type="quick", input_payload={})
        scope_id = self.create_scope([])
        self.assertEqual(self.results(scope_id).json(), {"matches": [], "count": 0, "next_offset": None})
        # A scope takes precedence over the trusted staff bypass as well.
        self.assertEqual(self.results(scope_id, staff=1).json()["count"], 0)
        self.assertEqual(self.results(scope_id, room=str(uuid.uuid4())).status_code, 400)

    def test_direct_filters_are_bounded(self):
        response = self.client.get("/api/v1/internal/results/", {"room": [str(uuid.uuid4()) for _ in range(33)]})
        self.assertEqual(response.status_code, 400)
