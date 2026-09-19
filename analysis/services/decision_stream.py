def extract_checker_decisions(game_analysis):
    events = sorted(
        game_analysis.input_events or [],
        key=lambda event: event["sequence"],
    )

    decisions = []
    current = None

    for event in events:
        event_type = event.get("event_type")
        payload = event.get("payload") or {}

        # Normal turn: dice have just been rolled and the player can move.
        starts_normal_turn = (
            event_type == "roll"
            and payload.get("phase") == "moving"
            and payload.get("dice")
        )

        # First checker decision of the game: opening dice become playable.
        starts_opening_turn = (
            event_type == "opening_result_done"
            and payload.get("phase") == "moving"
            and payload.get("dice")
        )

        if starts_normal_turn or starts_opening_turn:
            if current is not None:
                decisions.append(current)

            player = (
                event.get("player_color")
                or payload.get("turn")
            )

            current = {
                "player": player,
                "dice": list(payload.get("dice") or []),
                "before_state": payload,
                "after_state": None,
                "start_sequence": event["sequence"],
                "end_sequence": None,
                "played_action": None,
                "is_opening_roll": starts_opening_turn,
            }

            continue

        if current is None:
            continue

        if event_type in ("move", "undo"):
            last_move = payload.get("lastMove")

            # Undo can intentionally return to an earlier move list.
            if isinstance(last_move, list):
                current["played_action"] = last_move
            elif event_type == "undo":
                current["played_action"] = None

            current["after_state"] = payload
            current["end_sequence"] = event["sequence"]

            # Some turns end automatically after a move when there are no
            # additional legal moves, or when the game itself ends.
            turn_finished = (
                payload.get("phase") == "game_over"
                or (
                    payload.get("phase") == "rolling"
                    and payload.get("turn") != current["player"]
                )
            )

            if turn_finished:
                decisions.append(current)
                current = None

            continue

        if event_type == "end_turn":
            current["after_state"] = payload
            current["end_sequence"] = event["sequence"]

            decisions.append(current)
            current = None

    if current is not None and current.get("after_state") is not None:
        decisions.append(current)

    return decisions


class CubeDecisionStreamError(ValueError):
    pass


def _can_offer_double(state, player):
    if player not in ("white", "black"):
        return False

    if not isinstance(state, dict):
        return False

    if not state.get("doublingEnabled", True):
        return False

    cube_owner = state.get("cubeOwner", "center")

    if cube_owner not in ("center", player):
        return False

    cube_value = int(state.get("cube", 1) or 1)

    max_cube_value = state.get("maxCube", 64)

    # 0 means unlimited.
    if max_cube_value in (None, 0):
        return True

    return cube_value < int(max_cube_value)


def extract_cube_decisions(game_analysis):
    events = sorted(
        game_analysis.input_events or [],
        key=lambda event: event["sequence"],
    )

    decisions = []
    pending_double = None

    for event in events:
        event_type = event.get("event_type")
        payload = event.get("payload") or {}
        sequence = event.get("sequence")
        player = event.get("player_color")

        # ---------------------------------------------------------
        # Player rolled without doubling.
        #
        # A normal roll means the player had already made the
        # pre-roll cube decision: NO DOUBLE.
        #
        # Opening-roll events are excluded because their resulting
        # phase is opening_roll / opening_result.
        # ---------------------------------------------------------
        if event_type == "roll":
            if (
                payload.get("phase") in ("moving", "rolling")
                and _can_offer_double(payload, player)
            ):
                decisions.append(
                    {
                        "player": player,
                        "decision_type": "no_double",
                        "played_action": "no_double",
                        "before_state": payload,
                        "source_event_sequence": sequence,
                    }
                )

            continue

        # ---------------------------------------------------------
        # DOUBLE / REDOUBLE
        # ---------------------------------------------------------
        if event_type == "double":
            if player not in ("white", "black"):
                player = payload.get("doubleOfferedBy")

            if player not in ("white", "black"):
                raise CubeDecisionStreamError(
                    "Double event is missing the offering player."
                )

            cube_owner = payload.get("cubeOwner", "center")

            if cube_owner == player:
                decision_type = "redouble"
                played_action = "redouble"
            else:
                decision_type = "double"
                played_action = "double"

            decision = {
                "player": player,
                "decision_type": decision_type,
                "played_action": played_action,
                "before_state": payload,
                "source_event_sequence": sequence,
            }

            decisions.append(decision)

            # Keep the offered position because the next
            # double_response needs the position BEFORE the player
            # accepted or passed.
            pending_double = {
                "offerer": player,
                "state": payload,
                "sequence": sequence,
            }

            continue

        # ---------------------------------------------------------
        # TAKE / PASS
        # ---------------------------------------------------------
        if event_type == "double_response":
            if pending_double is None:
                raise CubeDecisionStreamError(
                    "double_response event has no preceding double event."
                )

            if player not in ("white", "black"):
                offerer = pending_double["offerer"]
                player = (
                    "black"
                    if offerer == "white"
                    else "white"
                )

            # A rejected double immediately ends the game.
            passed = (
                payload.get("phase") == "game_over"
                and payload.get("winner") is not None
            )

            if passed:
                decision_type = "pass"
                played_action = "pass"
            else:
                decision_type = "take"
                played_action = "take"

            decisions.append(
                {
                    "player": player,
                    "decision_type": decision_type,
                    "played_action": played_action,

                    # Important:
                    # evaluate the position at the moment the
                    # double was offered, not the state after the
                    # response changed the cube.
                    "before_state": pending_double["state"],

                    "offerer": pending_double["offerer"],
                    "double_sequence": pending_double["sequence"],
                    "source_event_sequence": sequence,
                }
            )

            pending_double = None

    return decisions
