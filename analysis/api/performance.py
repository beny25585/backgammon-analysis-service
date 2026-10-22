"""Small aggregates for trusted clients, keyed by stable game-player IDs."""
from django.db.models import Count, Sum
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from analysis.api.results import ResultsClient
from analysis.models import PlayerMatchAnalysis
from analysis.services.scoring import PR_MULTIPLIER


@api_view(["GET"])
@permission_classes([ResultsClient])
def player_performance(request):
    try:
        ids = list(dict.fromkeys(int(value) for value in request.query_params.getlist("player")))
        if not ids or len(ids) > 2 or any(value <= 0 for value in ids):
            raise ValueError()
    except (TypeError, ValueError):
        return Response({"detail": "Supply one or two player IDs."}, status=400)
    players = {str(player_id): {"pr": None, "matches": 0, "decisions": 0} for player_id in ids}
    rows = PlayerMatchAnalysis.objects.filter(
        source_player_id__in=ids, match_analysis__status="completed",
        pr__isnull=False, equity_lost__isnull=False, decisions_analyzed__gt=0,
    ).order_by().values("source_player_id").annotate(
        matches=Count("id"), decisions=Sum("decisions_analyzed"), lost=Sum("equity_lost"),
    )
    for row in rows:
        players[str(row["source_player_id"])] = {
            "pr": str(row["lost"] * PR_MULTIPLIER / row["decisions"]),
            "matches": row["matches"], "decisions": row["decisions"],
        }
    response = Response({"players": players})
    response["Cache-Control"] = "private, no-store"
    return response
