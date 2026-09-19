from analysis.converters.game_state import (
    game_cube_owner_to_open_sage,
    game_state_to_open_sage_board,
)
from analysis.engines.open_sage import OpenSageEngine


class LuckAnalysisError(ValueError):
    pass


_VALID_PLAYERS = {"white", "black"}


def _rules_for(game_analysis):
    payload = (
        game_analysis.match_analysis.input_payload
        or {}
    )

    rules = payload.get("rules") or {}

    if not isinstance(rules, dict):
        raise LuckAnalysisError(
            "Match rules must be an object."
        )

    return rules


def _away_scores(
    game_analysis,
    player,
    rules,
):
    if rules.get("format") != "match":
        return 0, 0

    target_points = int(
        rules.get("target_points") or 0
    )

    if target_points <= 0:
        raise LuckAnalysisError(
            "Match target_points must be positive."
        )

    white_score = int(
        game_analysis.white_score_before or 0
    )

    black_score = int(
        game_analysis.black_score_before or 0
    )

    if player == "white":
        player_score = white_score
        opponent_score = black_score
    else:
        player_score = black_score
        opponent_score = white_score

    away1 = max(
        0,
        target_points - player_score,
    )

    away2 = max(
        0,
        target_points - opponent_score,
    )

    return away1, away2


def analyze_roll_luck(
    *,
    game_analysis,
    roll,
    engine=None,
):
    player = roll.get("player")

    if player not in _VALID_PLAYERS:
        raise LuckAnalysisError(
            f"Invalid roll player: {player!r}"
        )

    dice = roll.get("dice")

    if (
        not isinstance(dice, list)
        or len(dice) != 2
    ):
        raise LuckAnalysisError(
            f"Invalid roll dice: {dice!r}"
        )

    state = roll.get("state")

    if not isinstance(state, dict):
        raise LuckAnalysisError(
            "Roll state must be an object."
        )

    rules = _rules_for(game_analysis)

    board = game_state_to_open_sage_board(
        state,
        player_on_roll=player,
    )

    cube_value = int(
        state.get("cube", 1) or 1
    )

    cube_owner = game_cube_owner_to_open_sage(
        state.get("cubeOwner", "center"),
        player_on_roll=player,
    )

    away1, away2 = _away_scores(
        game_analysis,
        player,
        rules,
    )

    jacoby = bool(
        rules.get("jacoby", True)
    )

    max_cube_value = int(
        rules.get("max_cube_value", 0) or 0
    )

    if engine is None:
        engine = OpenSageEngine()

    result = engine.analyze_roll_luck(
        board=board,
        die1=dice[0],
        die2=dice[1],
        cube_value=cube_value,
        cube_owner=cube_owner,
        away1=away1,
        away2=away2,
        is_crawford=bool(
            game_analysis.is_crawford
        ),
        jacoby=jacoby,
        max_cube_value=max_cube_value,
        is_opening_roll=bool(
            roll.get("is_opening_roll")
        ),
    )

    if result is None:
        raise LuckAnalysisError(
            "Open Sage could not calculate roll luck."
        )

    return {
        "player": player,
        "dice": list(dice),
        "source_event_sequence": roll[
            "source_event_sequence"
        ],
        "is_opening_roll": bool(
            roll.get("is_opening_roll")
        ),
        "luck": result["luck"],
        "actual_equity": result[
            "actual_equity"
        ],
        "average_equity": result[
            "average_equity"
        ],
        "ply": result["ply"],
        "level_label": result[
            "level_label"
        ],
        "position_snapshot": state,
        "raw_analysis": result,
    }
