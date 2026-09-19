from analysis.converters.game_state import (
    game_cube_owner_to_open_sage,
    game_state_to_open_sage_board,
)
from analysis.engines.open_sage import OpenSageEngine


class CheckerAnalysisError(ValueError):
    pass


def _rules_for(game_analysis):
    payload = game_analysis.match_analysis.input_payload or {}
    return payload.get("rules") or {}


def _away_scores(game_analysis, player, rules):
    if rules.get("format") != "match":
        return 0, 0

    target = int(rules["target_points"])

    if player == "white":
        player_score = game_analysis.white_score_before
        opponent_score = game_analysis.black_score_before
    else:
        player_score = game_analysis.black_score_before
        opponent_score = game_analysis.white_score_before

    return (
        max(0, target - player_score),
        max(0, target - opponent_score),
    )


def analyze_checker_decision(
    *,
    game_analysis,
    decision,
    engine=None,
):
    player = decision.get("player")

    if player not in ("white", "black"):
        raise CheckerAnalysisError(
            f"Invalid checker decision player: {player!r}"
        )

    before_state = decision.get("before_state")
    after_state = decision.get("after_state")

    if not isinstance(before_state, dict):
        raise CheckerAnalysisError(
            "Checker decision is missing before_state."
        )

    if not isinstance(after_state, dict):
        raise CheckerAnalysisError(
            "Checker decision is missing after_state."
        )

    dice = list(decision.get("dice") or [])

    if len(dice) != 2:
        raise CheckerAnalysisError(
            f"Checker decision must contain exactly two dice, got {dice!r}."
        )

    before_board = game_state_to_open_sage_board(
        before_state,
        player_on_roll=player,
    )

    played_board = game_state_to_open_sage_board(
        after_state,
        player_on_roll=player,
    )

    rules = _rules_for(game_analysis)

    away1, away2 = _away_scores(
        game_analysis,
        player,
        rules,
    )

    cube_value = int(before_state.get("cube", 1) or 1)

    cube_owner = game_cube_owner_to_open_sage(
        before_state.get("cubeOwner", "center"),
        player_on_roll=player,
    )

    max_cube_value = rules.get("max_cube_value")

    if max_cube_value is None:
        max_cube_value = before_state.get("maxCube", 0)

    max_cube_value = int(max_cube_value or 0)

    jacoby = bool(
        rules.get(
            "jacoby",
            before_state.get("jacoby", False),
        )
    )

    beaver = bool(rules.get("beaver", False))

    if engine is None:
        engine = OpenSageEngine()

    result = engine.analyze_checker_play(
        board=before_board,
        die1=dice[0],
        die2=dice[1],
        cube_value=cube_value,
        cube_owner=cube_owner,
        away1=away1,
        away2=away2,
        is_crawford=game_analysis.is_crawford,
        jacoby=jacoby,
        beaver=beaver,
        max_cube_value=max_cube_value,
        force_boards=[played_board],
    )

    moves = result.get("moves") or []

    if not moves:
        raise CheckerAnalysisError(
            "Open Sage returned no legal checker moves."
        )

    best_move = moves[0]

    played_move = next(
        (
            move
            for move in moves
            if move.get("board") == played_board
        ),
        None,
    )

    if played_move is None:
        raise CheckerAnalysisError(
            "Open Sage did not recognize the played resulting board "
            "as a legal candidate."
        )

    best_equity = float(best_move["equity"])
    played_equity = float(played_move["equity"])

    equity_loss = max(
        0.0,
        best_equity - played_equity,
    )

    return {
        "player": player,
        "dice": dice,

        "source_event_sequence": (
            decision.get("end_sequence")
            or decision.get("start_sequence")
        ),

        "played_action": decision.get("played_action"),

        "best_action": {
            "board": best_move["board"],
        },

        "played_equity": played_equity,
        "best_equity": best_equity,
        "equity_loss": equity_loss,

        "alternatives": [
            {
                "board": move["board"],
                "equity": move["equity"],
                "equity_diff": move["equity_diff"],
                "probabilities": move["probabilities"],
            }
            for move in moves[:5]
        ],

        "position_snapshot": before_state,

        "raw_analysis": result,
    }
