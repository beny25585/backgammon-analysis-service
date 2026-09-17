from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from analysis.api.serializers import MatchAnalysisInputSerializer


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

    return Response(
        {
            "status": "accepted",
            "match_id": str(serializer.validated_data["match_id"]),
        },
        status=status.HTTP_202_ACCEPTED,
    )
