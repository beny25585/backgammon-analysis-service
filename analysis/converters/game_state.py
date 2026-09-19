"""Pure converter from Backgammon Game state to native Open Sage boards.

Game representation:
    points[0..23]  positive = white, negative = black
    bar/home       {"white": int, "black": int}
    white moves 23 -> 0 -> off, black moves 0 -> 23 -> off

Open Sage representation (always from the player-on-roll perspective):
    26 integers, index 0 = opponent bar, 1..24 = points,
    index 25 = player-on-roll bar; positive = player on roll.

No Django, no models, no engine calls here.
"""


class GameStateConversionError(ValueError):
    pass


_VALID_PLAYERS = ("white", "black")


def _require_valid_player(player_on_roll):
    if player_on_roll not in _VALID_PLAYERS:
        raise GameStateConversionError(
            f"player_on_roll must be one of {_VALID_PLAYERS}, "
            f"got {player_on_roll!r}."
        )


def _require_valid_points(state):
    try:
        points = state["points"]
    except (KeyError, TypeError) as exc:
        raise GameStateConversionError(
            'state must contain a "points" list.'
        ) from exc
    if (
        not isinstance(points, list)
        or len(points) != 24
        or any(
            not isinstance(value, int) or isinstance(value, bool)
            for value in points
        )
    ):
        raise GameStateConversionError(
            'state["points"] must be a list of exactly 24 integers.'
        )
    return points


def _require_non_negative_int(value, *, label):
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise GameStateConversionError(
            f"{label} must be a non-negative integer, got {value!r}."
        )
    return value


def _require_valid_bar(state):
    try:
        bar = state["bar"]
        white = bar["white"]
        black = bar["black"]
    except (KeyError, TypeError) as exc:
        raise GameStateConversionError(
            'state must contain bar {"white": int, "black": int}.'
        ) from exc
    _require_non_negative_int(white, label='bar["white"]')
    _require_non_negative_int(black, label='bar["black"]')
    return white, black


def _require_valid_home(state):
    try:
        home = state["home"]
        white = home["white"]
        black = home["black"]
    except (KeyError, TypeError) as exc:
        raise GameStateConversionError(
            'state must contain home {"white": int, "black": int}.'
        ) from exc
    _require_non_negative_int(white, label='home["white"]')
    _require_non_negative_int(black, label='home["black"]')
    return white, black


def game_state_to_open_sage_board(state, *, player_on_roll) -> list[int]:
    """Convert a Game state to a 26-element Open Sage board.

    The caller must explicitly pass ``player_on_roll`` ("white"/"black");
    ``state["turn"]`` is never consulted.
    """
    _require_valid_player(player_on_roll)
    points = _require_valid_points(state)
    bar_white, bar_black = _require_valid_bar(state)
    home_white, home_black = _require_valid_home(state)

    white_on_points = sum(value for value in points if value > 0)
    black_on_points = sum(-value for value in points if value < 0)
    if white_on_points + bar_white + home_white != 15:
        raise GameStateConversionError(
            "White checkers must total 15 "
            f"(points={white_on_points}, bar={bar_white}, home={home_white})."
        )
    if black_on_points + bar_black + home_black != 15:
        raise GameStateConversionError(
            "Black checkers must total 15 "
            f"(points={black_on_points}, bar={bar_black}, home={home_black})."
        )

    board = [0] * 26
    if player_on_roll == "white":
        board[0] = bar_black
        for index in range(24):
            board[index + 1] = points[index]
        board[25] = bar_white
    else:
        board[0] = bar_white
        for index in range(24):
            board[index + 1] = -points[23 - index]
        board[25] = bar_black
    return board


def game_cube_owner_to_open_sage(cube_owner, *, player_on_roll) -> str:
    """Map Game cube ownership to Open Sage perspective terms."""
    _require_valid_player(player_on_roll)
    if cube_owner == "center":
        return "centered"
    if cube_owner == player_on_roll:
        return "player"
    other = "black" if player_on_roll == "white" else "white"
    if cube_owner == other:
        return "opponent"
    raise GameStateConversionError(
        f"cube_owner must be one of ('center', 'white', 'black'), "
        f"got {cube_owner!r}."
    )
