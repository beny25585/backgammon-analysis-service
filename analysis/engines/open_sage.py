"""Isolated adapter around the installed Open Sage (``bgsage``) package.

This module is the only place in application code that directly depends on
``bgsage``. Everything else (services, views, models) talks to
:class:`OpenSageEngine` and :class:`OpenSageError`.

Boards are expected in native Open Sage format (26 elements, player-on-roll
perspective). No Game -> Open Sage board conversion happens here.
"""

from bgsage import BgBotAnalyzer, roll_luck

OPEN_SAGE_ENGINE = "open_sage"
OPEN_SAGE_PACKAGE_VERSION = "2.0.20260907"
OPEN_SAGE_REVISION = "d8325a491168062df1047ffd998f3a5dfb426a0c"
OPEN_SAGE_VERSION = (
    f"{OPEN_SAGE_PACKAGE_VERSION}@{OPEN_SAGE_REVISION}"
)
DEFAULT_EVAL_LEVEL = "1ply"


class OpenSageError(Exception):
    pass


def _validate_board(board):
    if (
        not isinstance(board, list)
        or len(board) != 26
        or any(not isinstance(point, int) or isinstance(point, bool) for point in board)
    ):
        raise OpenSageError(
            "Board must be a list of exactly 26 integers "
            "(native Open Sage format)."
        )


def _probabilities_dict(probs):
    return {
        "win": float(probs.win),
        "gammon_win": float(probs.gammon_win),
        "backgammon_win": float(probs.backgammon_win),
        "gammon_loss": float(probs.gammon_loss),
        "backgammon_loss": float(probs.backgammon_loss),
    }


class OpenSageEngine:
    """Owns a single :class:`BgBotAnalyzer` instance."""

    def __init__(self, *, eval_level=DEFAULT_EVAL_LEVEL):
        self.eval_level = eval_level
        try:
            self.analyzer = BgBotAnalyzer(
                eval_level=eval_level,
                cubeful=True,
            )
        except Exception as exc:
            raise OpenSageError(
                f"Failed to initialize Open Sage analyzer: {exc}"
            ) from exc
        self._luck_analyzer = None

    def _get_luck_analyzer(self):
        """Lazily create and reuse a dedicated 2-ply analyzer for Luck.

        Roll-luck needs cube per-roll details, which require 2-ply or
        higher. The ordinary analyzer stays at ``DEFAULT_EVAL_LEVEL``.
        """
        if self._luck_analyzer is None:
            try:
                self._luck_analyzer = BgBotAnalyzer(
                    eval_level="2ply",
                    cubeful=True,
                )
            except Exception as exc:
                raise OpenSageError(
                    f"Failed to initialize Open Sage luck analyzer: {exc}"
                ) from exc
        return self._luck_analyzer

    def analyze_checker_play(
        self,
        *,
        board,
        die1,
        die2,
        cube_value=1,
        cube_owner="centered",
        away1=0,
        away2=0,
        is_crawford=False,
        jacoby=True,
        max_cube_value=0,
        beaver=False,
        force_boards=None,
    ):
        # Cube-cap enforcement belongs to Open Sage; forward it.
        _validate_board(board)
        normalized_force_boards = None

        if force_boards is not None:
            normalized_force_boards = []

            for forced_board in force_boards:
                _validate_board(forced_board)
                normalized_force_boards.append(list(forced_board))
        try:
            result = self.analyzer.checker_play(
                list(board),
                die1,
                die2,
                cube_value=cube_value,
                cube_owner=cube_owner,
                away1=away1,
                away2=away2,
                is_crawford=is_crawford,
                jacoby=jacoby,
                max_cube_value=max_cube_value,
                beaver=beaver,
                force_boards=normalized_force_boards,
            )
        except Exception as exc:
            raise OpenSageError(
                f"Open Sage checker play failed: {exc}") from exc

        moves = []
        for move in result.moves:
            moves.append(
                {
                    "board": list(move.board),
                    "equity": float(move.equity),
                    "cubeless_equity": float(move.cubeless_equity),
                    "equity_diff": float(move.equity_diff),
                    "eval_level": str(move.eval_level),
                    "probabilities": _probabilities_dict(move.probs),
                }
            )

        return {
            "engine": OPEN_SAGE_ENGINE,
            "engine_version": OPEN_SAGE_VERSION,
            "eval_level": str(result.eval_level),
            "board": list(board),
            "dice": [die1, die2],
            "moves": moves,
        }

    def analyze_cube_action(
        self,
        *,
        board,
        cube_value=1,
        cube_owner="centered",
        away1=0,
        away2=0,
        is_crawford=False,
        jacoby=True,
        max_cube_value=0,
        beaver=False,
    ):
        # Cube-cap enforcement belongs to Open Sage; forward it.
        _validate_board(board)
        try:
            result = self.analyzer.cube_action(
                list(board),
                cube_value=cube_value,
                cube_owner=cube_owner,
                away1=away1,
                away2=away2,
                is_crawford=is_crawford,
                jacoby=jacoby,
                max_cube_value=max_cube_value,
                beaver=beaver,
            )
        except Exception as exc:
            raise OpenSageError(
                f"Open Sage cube action failed: {exc}") from exc

        return {
            "engine": OPEN_SAGE_ENGINE,
            "engine_version": OPEN_SAGE_VERSION,
            "eval_level": str(result.eval_level),
            "cubeless_equity": float(result.cubeless_equity),
            "equities": {
                "no_double": float(result.equity_nd),
                "double_take": float(result.equity_dt),
                "double_pass": float(result.equity_dp),
            },
            "should_double": bool(result.should_double),
            "should_take": bool(result.should_take),
            "is_beaver": bool(
                getattr(result, "is_beaver", False)
            ),
            "optimal_equity": float(result.optimal_equity),
            "optimal_action": str(result.optimal_action),
            "probabilities": _probabilities_dict(result.probs),
        }

    def analyze_roll_luck(
        self,
        *,
        board,
        die1,
        die2,
        cube_value=1,
        cube_owner="centered",
        away1=0,
        away2=0,
        is_crawford=False,
        jacoby=True,
        max_cube_value=0,
        beaver=False,
        is_opening_roll=False,
    ):
        _validate_board(board)
        try:
            luck_analyzer = self._get_luck_analyzer()
            # Luck must use the same capped cube rules as the game, so run
            # the capped cube analysis first (single engine evaluation)
            # and derive Luck from its per-roll details.
            cube_result = luck_analyzer.cube_action(
                list(board),
                cube_value=cube_value,
                cube_owner=cube_owner,
                away1=away1,
                away2=away2,
                is_crawford=is_crawford,
                jacoby=jacoby,
                max_cube_value=max_cube_value,
                beaver=beaver,
                incl_2ply_details=True,
            )
            result = roll_luck(
                cube_result,
                die1,
                die2,
                is_opening_roll=is_opening_roll,
            )
        except Exception as exc:
            raise OpenSageError(f"Open Sage roll luck failed: {exc}") from exc

        if result is None:
            return None

        return {
            "engine": OPEN_SAGE_ENGINE,
            "engine_version": OPEN_SAGE_VERSION,
            "luck": float(result.luck),
            "actual_equity": float(result.actual_equity),
            "average_equity": float(result.average_equity),
            "ply": int(result.ply),
            "level_label": str(result.level_label),
        }
