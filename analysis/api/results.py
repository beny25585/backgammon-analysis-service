"""Read-only results for the trusted tournaments server, never the browser."""
import hmac
import os

from django.conf import settings
from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import BasePermission
from rest_framework.response import Response

from analysis.models import MatchAnalysis
from analysis.engines.open_sage import checker_move_notation
from analysis.services.decision_stream import extract_checker_decisions
from analysis.services.scoring import is_blunder
from analysis.converters.game_state import game_state_to_open_sage_board


class ResultsClient(BasePermission):
    def has_permission(self, request, view):
        token = getattr(settings, "ANALYSIS_API_TOKEN", "") or os.environ.get("ANALYSIS_API_TOKEN", "")
        supplied = request.headers.get("Authorization", "")
        return bool(token) and hmac.compare_digest(supplied.encode(), f"Bearer {token}".encode())


def summary(match):
    return {
        "id": str(match.id), "status": match.status,
        "room_id": str(match.source_room_id) if match.source_room_id else None,
        "created_at": match.created_at.isoformat(),
        "engine": match.engine, "engine_version": match.engine_version,
        "rules": match.input_payload.get("rules", {}),
        "result": match.input_payload.get("result", {}),
        "players": [{"color": p.color, "pr": p.pr, "luck": p.luck,
                     "errors": p.errors, "blunders": p.blunders,
                     "equity_lost": p.equity_lost} for p in match.players.all()],
    }


@api_view(["GET"])
@permission_classes([ResultsClient])
def match_results(request, analysis_id=None):
    matches = MatchAnalysis.objects.prefetch_related("players")
    if analysis_id is None:
        # The trusted caller supplies only rooms authorized for its session.
        if request.query_params.get("staff") != "1":
            rooms = request.query_params.getlist("room")
            matches = matches.filter(source_room_id__in=rooms)
        return Response({"matches": [summary(m) for m in matches[:200]]})

    match = get_object_or_404(matches, pk=analysis_id)
    data = summary(match)
    data["games"] = []
    for game in match.games.prefetch_related("players__match_player_analysis", "players__decisions"):
        played = {d["end_sequence"]: d for d in extract_checker_decisions(game)}
        decisions = []
        for player in game.players.all():
            color = player.match_player_analysis.color
            for decision in player.decisions.all():
                snapshot = decision.position_snapshot
                item = {
                    "id": str(decision.id), "sequence": decision.sequence_number,
                    "player": color, "type": decision.decision_type,
                    "dice": decision.dice,
                    "classification": "blunder" if is_blunder(decision) else decision.classification,
                    "equity_loss": decision.equity_loss,
                    "played_equity": decision.played_equity, "best_equity": decision.best_equity,
                    "played_action": decision.played_action, "best_action": decision.best_action,
                    "alternatives": decision.alternatives,
                    "board": game_state_to_open_sage_board(snapshot, player_on_roll=color),
                    "cube": snapshot.get("cube", 1), "played_board": None,
                }
                extracted = played.get(decision.source_event_sequence)
                if decision.decision_type == "checker_move" and extracted:
                    item["played_board"] = game_state_to_open_sage_board(extracted["after_state"], player_on_roll=color)
                if decision.decision_type == "checker_move":
                    item["alternatives"] = [
                        {**candidate, "notation": checker_move_notation(item["board"], candidate["board"], decision.dice)}
                        for candidate in decision.alternatives
                    ]
                    item["played_notation"] = checker_move_notation(item["board"], item["played_board"], decision.dice)
                    item["best_notation"] = checker_move_notation(item["board"], (decision.best_action or {}).get("board"), decision.dice)
                decisions.append(item)
        data["games"].append({"number": game.game_number, "is_crawford": game.is_crawford,
                              "score": [game.white_score_before, game.black_score_before],
                              "decisions": sorted(decisions, key=lambda d: d["sequence"])})
    return Response(data)
