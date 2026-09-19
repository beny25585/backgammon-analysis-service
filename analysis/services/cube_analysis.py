from analysis.converters.game_state import (
    game_cube_owner_to_open_sage,
    game_state_to_open_sage_board,
)
from analysis.engines.open_sage import OpenSageEngine


class CubeAnalysisError(ValueError):
    pass


_CUBE_DECISIONS = {
    "no_double",
    "double",
    "redouble",
    "take",
    "pass",
}


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


def _normalize_double_action(result, *, is_redouble):
    if not result["should_double"]:
        return {
            "action": "no_double",
            "engine_action": result["optimal_action"],
        }

    return {
        "action": "redouble" if is_redouble else "double",
        "response": "take" if result["should_take"] else "pass",
        "engine_action": result["optimal_action"],
    }


def analyze_cube_decision(
    *,
    game_analysis,
    decision,
    engine=None,
):
    player = decision.get("player")

    if player not in ("white", "black"):
        raise CubeAnalysisError(
            f"Invalid cube decision player: {player!r}"
        )

    decision_type = decision.get("decision_type")

    if decision_type not in _CUBE_DECISIONS:
        raise CubeAnalysisError(
            f"Invalid cube decision type: {decision_type!r}"
        )

    before_state = decision.get("before_state")

    if not isinstance(before_state, dict):
        raise CubeAnalysisError(
            "Cube decision is missing before_state."
        )

    # TAKE/PASS is evaluated from the perspective of the player
    # who offered the double, because Open Sage's cube_action
    # returns ND / DT / DP equities from that player's perspective.
    if decision_type in ("take", "pass"):
        engine_player = decision.get("offerer")

        if engine_player not in ("white", "black"):
            raise CubeAnalysisError(
                "Take/pass decision is missing a valid offerer."
            )
    else:
        engine_player = player

    board = game_state_to_open_sage_board(
        before_state,
        player_on_roll=engine_player,
    )

    cube_owner = game_cube_owner_to_open_sage(
        before_state.get("cubeOwner", "center"),
        player_on_roll=engine_player,
    )

    cube_value = int(
        before_state.get("cube", 1) or 1
    )

    rules = _rules_for(game_analysis)

    away1, away2 = _away_scores(
        game_analysis,
        engine_player,
        rules,
    )

    max_cube_value = rules.get("max_cube_value")

    if max_cube_value is None:
        max_cube_value = before_state.get(
            "maxCube",
            0,
        )

    max_cube_value = int(
        max_cube_value or 0
    )

    jacoby = bool(
        rules.get(
            "jacoby",
            before_state.get("jacoby", False),
        )
    )

    beaver = bool(
        rules.get("beaver", False)
    )

    if engine is None:
        engine = OpenSageEngine()

    result = engine.analyze_cube_action(
        board=board,
        cube_value=cube_value,
        cube_owner=cube_owner,
        away1=away1,
        away2=away2,
        is_crawford=game_analysis.is_crawford,
        jacoby=jacoby,
        max_cube_value=max_cube_value,
        beaver=beaver,
    )

    equities = result.get("equities") or {}

    try:
        no_double_equity = float(
            equities["no_double"]
        )
        double_take_equity = float(
            equities["double_take"]
        )
        double_pass_equity = float(
            equities["double_pass"]
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise CubeAnalysisError(
            "Open Sage returned incomplete cube equities."
        ) from exc

    # If the player doubles, the opponent chooses the response
    # that is best for the opponent, i.e. the lower equity from
    # the doubler's perspective.
    double_equity = min(
        double_take_equity,
        double_pass_equity,
    )

    # ---------------------------------------------------------
    # NO DOUBLE / DOUBLE / REDOUBLE
    # ---------------------------------------------------------
    if decision_type in (
        "no_double",
        "double",
        "redouble",
    ):
        best_equity = max(
            no_double_equity,
            double_equity,
        )

        if decision_type == "no_double":
            played_equity = no_double_equity
        else:
            played_equity = double_equity

        equity_loss = max(
            0.0,
            best_equity - played_equity,
        )

        best_action = _normalize_double_action(
            result,
            is_redouble=(
                decision_type == "redouble"
            ),
        )

    # ---------------------------------------------------------
    # TAKE / PASS
    # ---------------------------------------------------------
    else:
        # Open Sage values DT / DP from the offerer's
        # perspective.
        #
        # The responder wants to MINIMIZE the offerer's equity.
        best_offerer_equity = min(
            double_take_equity,
            double_pass_equity,
        )

        if decision_type == "take":
            played_offerer_equity = (
                double_take_equity
            )
        else:
            played_offerer_equity = (
                double_pass_equity
            )

        # Persist equities from the actual decision player's
        # perspective.
        played_equity = -played_offerer_equity
        best_equity = -best_offerer_equity

        equity_loss = max(
            0.0,
            played_offerer_equity
            - best_offerer_equity,
        )

        best_action = {
            "action": (
                "take"
                if result["should_take"]
                else "pass"
            ),
            "engine_action": (
                result["optimal_action"]
            ),
        }

    return {
        "player": player,
        "decision_type": decision_type,

        "source_event_sequence": (
            decision.get(
                "source_event_sequence"
            )
        ),

        "played_action": {
            "action": decision.get(
                "played_action"
            ),
        },

        "best_action": best_action,

        "played_equity": played_equity,
        "best_equity": best_equity,
        "equity_loss": equity_loss,

        "alternatives": {
            "no_double": no_double_equity,
            "double_take": double_take_equity,
            "double_pass": double_pass_equity,
        },

        "position_snapshot": before_state,

        "raw_analysis": {
            **result,
            "engine_player": engine_player,
        },
    }
