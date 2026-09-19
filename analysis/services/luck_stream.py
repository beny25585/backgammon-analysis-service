class LuckStreamError(ValueError):
    pass


_VALID_PLAYERS = {"white", "black"}


def _sequence(event):
    try:
        return int(event.get("sequence"))
    except (TypeError, ValueError):
        raise LuckStreamError(
            f"Invalid event sequence: {event.get('sequence')!r}"
        )


def _payload(event):
    payload = event.get("payload")

    if not isinstance(payload, dict):
        raise LuckStreamError(
            "Event payload must be an object."
        )

    return payload


def _dice(payload):
    dice = payload.get("dice")

    if (
        not isinstance(dice, list)
        or len(dice) != 2
        or any(
            not isinstance(value, int)
            or isinstance(value, bool)
            or value < 1
            or value > 6
            for value in dice
        )
    ):
        raise LuckStreamError(
            f"Invalid roll dice: {dice!r}"
        )

    return list(dice)


def _player(payload):
    player = payload.get("turn")

    if player not in _VALID_PLAYERS:
        raise LuckStreamError(
            f"Invalid player on roll: {player!r}"
        )

    return player


def extract_luck_rolls(game_analysis):
    events = sorted(
        game_analysis.input_events or [],
        key=lambda event: int(
            event.get("sequence", 0)
        ),
    )

    rolls = []

    for event in events:
        if not isinstance(event, dict):
            raise LuckStreamError(
                "Game event must be an object."
            )

        event_type = event.get("event_type")
        payload = _payload(event)

        is_opening_roll = (
            event_type == "opening_result_done"
        )

        is_normal_roll = (
            event_type == "roll"
            and payload.get("phase") == "moving"
        )

        if not (
            is_opening_roll
            or is_normal_roll
        ):
            continue

        rolls.append(
            {
                "source_event_sequence": _sequence(
                    event
                ),
                "player": _player(payload),
                "dice": _dice(payload),
                "state": payload,
                "is_opening_roll": (
                    is_opening_roll
                ),
            }
        )

    return rolls
