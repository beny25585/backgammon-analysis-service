import copy

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from analysis.api.serializers import MatchAnalysisInputSerializer
from analysis.services.ingestion import MatchPayloadConflict, ingest_match


@api_view(["GET"])
@permission_classes([AllowAny])
def health(request):
    return Response({
        "service": "backgammon-analysis",
        "status": "ok",
    })


@api_view(["POST"])
@permission_classes([AllowAny])
def receive_match(request):
    serializer = MatchAnalysisInputSerializer(data=request.data)

    if not serializer.is_valid():
        return Response(
            serializer.errors,
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Keep the exact JSON-shaped package received from Backgammon Game.
    raw_payload = copy.deepcopy(request.data)

    try:
        analysis, created = ingest_match(
            validated_data=serializer.validated_data,
            raw_payload=raw_payload,
        )
    except MatchPayloadConflict:
        return Response(
            {
                "status": "conflict",
                "code": "match_payload_conflict",
                "match_id": str(serializer.validated_data["match_id"]),
            },
            status=status.HTTP_409_CONFLICT,
        )

    return Response(
        {
            "status": "accepted" if created else "already_exists",
            "analysis_id": str(analysis.id),
            "match_id": str(analysis.source_match_id),
        },
        status=(
            status.HTTP_202_ACCEPTED
            if created
            else status.HTTP_200_OK
        ),
    )
