"""Bounded, read-only pages of analysis summaries."""
from types import SimpleNamespace

from django.db.models import F, Prefetch

from analysis.models import DecisionAnalysis, MatchAnalysis, PlayerMatchAnalysis
from analysis.services.classification import ERROR_THRESHOLD, classify_decision

PAGE_SIZE = 5


def page_offset(params):
    try:
        limit = int(params.get("limit", PAGE_SIZE))
        offset = int(params.get("offset", 0))
    except (TypeError, ValueError) as exc:
        raise ValueError("Invalid pagination.") from exc
    if limit != PAGE_SIZE or offset < 0:
        raise ValueError("limit must be 5 and offset must be nonnegative.")
    return offset


def summary_page(rooms, *, staff=False, offset=0):
    matches = MatchAnalysis.objects.all()
    if not staff:
        matches = matches.filter(source_room_id__in=rooms)
    count = matches.count()
    # Project only the metadata displayed in a summary, never the full history
    # or raw engine response. Prefetch only players, not their games/decisions.
    matches = matches.annotate(
        summary_rules=F("input_payload__rules"),
        summary_result=F("input_payload__result"),
        summary_players=F("input_payload__players"),
    ).defer("input_payload", "raw_response").prefetch_related(
        Prefetch("players", queryset=PlayerMatchAnalysis.objects.only(
            "id", "match_analysis_id", "color", "game_rating", "pr", "luck", "equity_lost",
        )),
    ).order_by("-created_at", "-id")
    page = list(matches[offset:offset + PAGE_SIZE])
    for match in page:
        match.summary_payload = {
            "rules": match.summary_rules,
            "result": match.summary_result,
            "players": match.summary_players,
        }
    players = [player for match in page for player in match.players.all()]
    counts = {player.id: {"errors": 0, "blunders": 0} for player in players}
    # Legacy stored counts can be stale. Keep the shared classification policy,
    # but stream only potentially counted decisions and their scoring inputs.
    decisions = DecisionAnalysis.objects.filter(
        player_game_analysis__match_player_analysis_id__in=counts,
        equity_loss__gte=ERROR_THRESHOLD,
    ).order_by().values(
        "decision_type", "equity_loss",
        player_id=F("player_game_analysis__match_player_analysis_id"),
        moves=F("raw_analysis__moves"),
        equities=F("raw_analysis__equities"),
        is_beaver=F("raw_analysis__is_beaver"),
    )
    for row in decisions.iterator(chunk_size=25):
        decision = SimpleNamespace(
            decision_type=row["decision_type"], equity_loss=row["equity_loss"],
            raw_analysis={
                "moves": row["moves"], "equities": row["equities"],
                "is_beaver": row["is_beaver"],
            },
        )
        label = classify_decision(decision)
        if label == DecisionAnalysis.Classification.ERROR:
            counts[row["player_id"]]["errors"] += 1
        elif label == DecisionAnalysis.Classification.BLUNDER:
            counts[row["player_id"]]["blunders"] += 1
    next_offset = offset + PAGE_SIZE if offset + PAGE_SIZE < count else None
    return page, counts, count, next_offset
