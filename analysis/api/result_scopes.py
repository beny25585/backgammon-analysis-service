"""Bounded upload of request-bound authorization; never a permanent ACL mirror."""
from datetime import timedelta
import hashlib
import hmac
import re
import uuid

from django.db import transaction
from django.http import Http404
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from analysis.models import ResultAccessRoom, ResultAccessScope
from analysis.api.results import ResultsClient

SCOPE_CHUNK_SIZE = 128
SCOPE_BODY_LIMIT = 8192
SCOPE_LIFETIME_SECONDS = 300
DIRECT_ROOM_LIMIT = 32


def scope_binding(request):
    supplied = request.headers.get("X-Analysis-Scope-Binding", "")
    if not re.fullmatch(r"[0-9a-f]{64}", supplied):
        raise ValidationError({"detail": "A request binding is required."})
    # A scope cannot be reused with another trusted caller's credential.
    credential = request.headers.get("Authorization", "")
    return hmac.new(credential.encode(), supplied.encode(), hashlib.sha256).hexdigest()


def cleanup_expired_scopes(*, batch_size=25):
    """Bound each cleanup operation; cascades delete the scope's room rows."""
    ids = list(ResultAccessScope.objects.filter(expires_at__lte=timezone.now())
               .order_by("expires_at").values_list("pk", flat=True)[:batch_size])
    if ids:
        ResultAccessScope.objects.filter(pk__in=ids).delete()
    return len(ids)


def authorized_scope_rooms(request, scope_id):
    try:
        scope_id = uuid.UUID(str(scope_id))
    except (ValueError, TypeError, AttributeError):
        raise Http404
    scope = ResultAccessScope.objects.filter(
        pk=scope_id, binding=scope_binding(request),
        expires_at__gt=timezone.now(), finalized_at__isnull=False,
    ).first()
    if scope is None:
        raise Http404
    return ResultAccessRoom.objects.filter(scope=scope).values("room_id")


def _payload(request):
    try:
        length = int(request.headers.get("Content-Length", "0"))
    except (ValueError, TypeError):
        raise ValidationError({"detail": "Invalid request length."})
    if length > SCOPE_BODY_LIMIT or len(request.body) > SCOPE_BODY_LIMIT:
        raise ValidationError({"detail": "Scope upload is too large."})
    if not isinstance(request.data, dict):
        raise ValidationError({"detail": "Supply a JSON object."})
    return request.data


@api_view(["POST", "DELETE"])
@permission_classes([ResultsClient])
def result_scope(request, scope_id=None):
    binding = scope_binding(request)
    if scope_id is None:
        if request.method != "POST":
            return Response(status=405)
        data = _payload(request)
        count = data.get("room_count")
        if isinstance(count, bool) or not isinstance(count, int) or not 0 <= count <= 2_147_483_647:
            return Response({"detail": "Invalid room count."}, status=400)
        cleanup_expired_scopes()
        scope = ResultAccessScope.objects.create(
            binding=binding, expected_count=count,
            expires_at=timezone.now() + timedelta(seconds=SCOPE_LIFETIME_SECONDS),
        )
        return Response({"id": str(scope.pk)}, status=201)

    # Serialize append/finalize/delete for this request's scope. An incomplete
    # upload can never be used to compute a partial count or page.
    with transaction.atomic():
        scope = ResultAccessScope.objects.select_for_update().filter(
            pk=scope_id, binding=binding, expires_at__gt=timezone.now(),
        ).first()
        if scope is None:
            raise Http404
        if request.method == "DELETE":
            scope.delete()
            return Response(status=204)
        data = _payload(request)
        if scope.finalized_at is not None:
            return Response({"detail": "Scope is already finalized."}, status=409)
        if data.get("finalize") is True:
            if scope.received_count != scope.expected_count:
                return Response({"detail": "Scope upload is incomplete."}, status=409)
            scope.finalized_at = timezone.now()
            scope.expires_at = scope.finalized_at + timedelta(seconds=SCOPE_LIFETIME_SECONDS)
            scope.save(update_fields=["finalized_at", "expires_at"])
            return Response({"id": str(scope.pk), "finalized": True})
        rooms = data.get("rooms")
        offset = data.get("offset")
        if (isinstance(offset, bool) or not isinstance(offset, int)
                or offset != scope.received_count or not isinstance(rooms, list)
                or not 1 <= len(rooms) <= SCOPE_CHUNK_SIZE):
            return Response({"detail": "Invalid scope chunk or offset."}, status=400)
        try:
            rooms = [uuid.UUID(str(room)) for room in rooms]
        except (ValueError, TypeError, AttributeError):
            return Response({"detail": "Invalid room ID."}, status=400)
        if (len(set(rooms)) != len(rooms)
                or scope.received_count + len(rooms) > scope.expected_count
                or scope.rooms.filter(room_id__in=rooms).exists()):
            return Response({"detail": "Duplicate rooms or excess upload."}, status=400)
        ResultAccessRoom.objects.bulk_create([
            ResultAccessRoom(scope=scope, room_id=room) for room in rooms
        ], batch_size=SCOPE_CHUNK_SIZE)
        scope.received_count += len(rooms)
        scope.expires_at = timezone.now() + timedelta(seconds=SCOPE_LIFETIME_SECONDS)
        scope.save(update_fields=["received_count", "expires_at"])
        return Response({"received_count": scope.received_count})
