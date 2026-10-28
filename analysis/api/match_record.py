"""Read-only source records, independent of the derived analysis tables."""
import uuid

from django.shortcuts import get_object_or_404
from django.views.decorators.cache import cache_control
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from analysis.models import MatchAnalysis
from .results import ResultsClient


RULE_FIELDS = (
    "format", "target_points", "time_control", "doubling_enabled",
    "max_cube_value", "jacoby", "beaver",
)
GAME_FIELDS = (
    "game_id", "game_number", "winner", "win_type", "points_awarded", "is_crawford",
)
EVENT_FIELDS = ("sequence", "event_type", "player_color", "created_at")
STATE_FIELDS = (
    "phase", "turn", "dice", "remaining", "cube", "cubeOwner", "doubleOfferedBy",
    "winner", "winType", "points", "gameId", "crawfordGame",
    "gameEndReason", "gameEndPoints",
)


def fields(source, names):
    """Copy named fields without exposing arbitrary keys from the source."""
    return {name: source[name] for name in names if name in source}


def event_record(event):
    payload = event.get("payload") or {}
    state = fields(payload, STATE_FIELDS)
    for name in ("bar", "home", "openingRoll"):
        if name in payload:
            state[name] = fields(payload[name] or {}, ("white", "black"))
    if "lastMove" in payload:
        moves = payload["lastMove"]
        state["lastMove"] = (
            [fields(move, ("from", "to")) for move in moves]
            if isinstance(moves, list) else None
        )
    return {**fields(event, EVENT_FIELDS), "payload": state}


def source_record(match):
    payload = match.input_payload
    players = payload.get("players") or {}
    games = []
    for game in payload.get("games") or []:
        games.append({
            **fields(game, GAME_FIELDS),
            "score_before": fields(game.get("score_before") or {}, ("white", "black")),
            "score_after": fields(game.get("score_after") or {}, ("white", "black")),
            "events": [event_record(event) for event in game.get("events") or []],
        })
    return {
        "id": str(match.id),
        "match_id": str(match.source_match_id),
        "room_id": str(match.source_room_id) if match.source_room_id else None,
        "created_at": match.created_at.isoformat(),
        "players": {
            color: {"name": (players.get(color) or {}).get("name", "")}
            for color in ("white", "black")
        },
        "rules": fields(payload.get("rules") or {}, RULE_FIELDS),
        "result": fields(payload.get("result") or {}, ("winner", "white_score", "black_score")),
        "games": games,
    }


@cache_control(private=True, no_store=True)
@api_view(["GET"])
@permission_classes([ResultsClient])
def match_record(request, analysis_id):
    matches = MatchAnalysis.objects.only(
        "id", "source_match_id", "source_room_id", "created_at", "input_payload",
    )
    room = request.query_params.get("room")
    if room:
        try:
            room_id = uuid.UUID(room)
        except (ValueError, AttributeError):
            return Response({"detail": "Analysis not found."}, status=404)
        matches = matches.filter(source_room_id=room_id)
    elif request.query_params.get("staff") != "1":
        matches = matches.none()
    # The room filter is part of the source query, before materializing history.
    match = get_object_or_404(matches, pk=analysis_id)
    return Response(source_record(match))
