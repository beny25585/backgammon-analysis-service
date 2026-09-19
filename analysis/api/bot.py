"""Live checker play using the pinned markbgsage/bgsage API.

Source: python/bgsage/{analyzer,board,types}.py at
d8325a491168062df1047ffd998f3a5dfb426a0c. This endpoint is server-to-server.
Difficulty sampling is application policy, not an upstream strength rating.
"""
import math
import secrets
import threading

from bgsage import BgBotAnalyzer
from rest_framework import serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from analysis.api.results import ResultsClient
from analysis.converters.game_state import game_state_to_open_sage_board, GameStateConversionError
from analysis.engines.open_sage import OPEN_SAGE_VERSION


class BotInput(serializers.Serializer):
    state = serializers.DictField()
    difficulty = serializers.ChoiceField(choices=("easy", "medium", "hard"))


_lock = threading.Lock()
_engine = None


def choose_board(state, difficulty):
    """One-point practice: evaluate complete turns, with no live cube."""
    global _engine
    if state.get("phase") != "moving" or state.get("turn") not in ("white", "black"):
        raise ValueError("Expected the start of a checker-play turn")
    dice = state.get("dice", [])
    if len(dice) not in (2, 4) or any(type(d) is not int or not 1 <= d <= 6 for d in dice):
        raise ValueError("Invalid dice")
    expected = [dice[0]] * 4 if dice[0] == dice[1] else dice[:2]
    # The game server stores two physical dice, including doubles; only
    # remaining expands doubles to four moves. Accept expanded legacy input too.
    if dice not in (expected[:2], expected) or sorted(state.get("remaining", [])) != sorted(expected):
        raise ValueError("Expected an unplayed full roll")
    board = game_state_to_open_sage_board(state, player_on_roll=state["turn"])
    # A busy live worker returns promptly instead of accumulating requests.
    if not _lock.acquire(blocking=False):
        raise RuntimeError("Engine busy")
    try:
        if _engine is None:
            _engine = BgBotAnalyzer(eval_level="1ply", cubeful=True, parallel_threads=1)
        result = _engine.checker_play(
            board, dice[0], dice[1], away1=1, away2=1,
            is_crawford=True, jacoby=False, beaver=False,
        )
        if not result.moves:
            raise RuntimeError("Engine returned no candidate")
        selected = result.moves[0]
        if difficulty != "hard":
            temperature, limit = {"easy": (0.10, 0.30), "medium": (0.025, 0.08)}[difficulty]
            candidates = [m for m in result.moves if selected.equity - m.equity <= limit]
            weights = [math.exp((m.equity - selected.equity) / temperature) for m in candidates]
            selected = secrets.SystemRandom().choices(candidates, weights=weights, k=1)[0]
        return {"board": list(selected.board), "engine": "open_sage",
                "engine_version": OPEN_SAGE_VERSION, "eval_level": str(selected.eval_level)}
    finally:
        _lock.release()


@api_view(["POST"])
@permission_classes([ResultsClient])
def bot_move(request):
    serializer = BotInput(data=request.data)
    serializer.is_valid(raise_exception=True)
    try:
        return Response(choose_board(**serializer.validated_data))
    except (ValueError, TypeError, KeyError, GameStateConversionError):
        return Response({"error": "Invalid game position"}, status=400)
    except Exception:
        import logging
        logging.getLogger(__name__).exception("Live Open Sage move failed")
        return Response({"error": "AI temporarily unavailable"}, status=503)
