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
    match = serializers.DictField(required=False, default=dict)
    action = serializers.ChoiceField(choices=('move', 'cube'), default='move')


_lock = threading.Lock()
_engine = None


def match_context(state, match, color):
    target = match.get('target_points', 1)
    scores = match.get('scores', {'white': 0, 'black': 0})
    if type(target) is not int or not 1 <= target <= 25:
        raise ValueError('Invalid match length')
    if any(type(scores.get(c)) is not int or not 0 <= scores[c] < target for c in ('white', 'black')):
        raise ValueError('Invalid score')
    other = 'black' if color == 'white' else 'white'
    owner = state.get('cubeOwner', 'center')
    cube = state.get('cube', 1)
    limit = state.get('maxCube', 64)
    if cube not in (1, 2, 4, 8, 16, 32, 64) or owner not in ('center', 'white', 'black'):
        raise ValueError('Invalid cube')
    return dict(cube_value=cube,
        cube_owner='centered' if owner == 'center' else ('player' if owner == color else 'opponent'),
        away1=target - scores[color], away2=target - scores[other],
        is_crawford=bool(state.get('crawfordGame', target == 1) or not state.get('doublingAllowed', True)),
        jacoby=False, beaver=False, max_cube_value=limit if limit != 1 else 0)


def choose_board(state, difficulty, match=None, action='move'):
    """One-point practice: evaluate complete turns, with no live cube."""
    global _engine
    if action == 'cube':
        return choose_cube(state, match or {})
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
            board, dice[0], dice[1], **match_context(state, match or {}, state['turn']),
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


def choose_cube(state, match):
    """Upstream cube_action is from the offerer's pre-roll perspective.

    should_take describes the opponent's response, so do not flip the board
    to the responder when handling a pending human offer.
    """
    global _engine
    if state.get('phase') not in ('rolling', 'doubling_offered'):
        raise ValueError('Expected a cube decision')
    color = state.get('doubleOfferedBy') if state['phase'] == 'doubling_offered' else state['turn']
    if not state.get('doublingEnabled') or state.get('crawfordGame'):
        raise ValueError('Cube disabled')
    board = game_state_to_open_sage_board(state, player_on_roll=color)
    if not _lock.acquire(blocking=False):
        raise RuntimeError('Engine busy')
    try:
        if _engine is None:
            _engine = BgBotAnalyzer(eval_level='1ply', cubeful=True, parallel_threads=1)
        result = _engine.cube_action(board, **match_context(state, match, color))
        return {'should_double': bool(result.should_double), 'should_take': bool(result.should_take)}
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
