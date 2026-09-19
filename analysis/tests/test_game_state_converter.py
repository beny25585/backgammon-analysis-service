import copy

from django.test import SimpleTestCase

from analysis.converters.game_state import (
    GameStateConversionError,
    game_cube_owner_to_open_sage,
    game_state_to_open_sage_board,
)


def starting_state():
    points = [0] * 24
    points[23] = 2
    points[12] = 5
    points[7] = 3
    points[5] = 5
    points[0] = -2
    points[11] = -5
    points[16] = -3
    points[18] = -5
    return {
        "points": points,
        "bar": {"white": 0, "black": 0},
        "home": {"white": 0, "black": 0},
    }


class GameStateConverterTests(SimpleTestCase):
    def test_starting_position_white_matches_open_sage(self):
        from bgsage import STARTING_BOARD

        board = game_state_to_open_sage_board(
            starting_state(), player_on_roll="white"
        )
        self.assertEqual(board, list(STARTING_BOARD))

    def test_starting_position_black_matches_open_sage(self):
        from bgsage import STARTING_BOARD

        board = game_state_to_open_sage_board(
            starting_state(), player_on_roll="black"
        )
        # The standard opening is symmetric: identical from both sides.
        self.assertEqual(board, list(STARTING_BOARD))

    def test_asymmetric_position_perspectives(self):
        state = starting_state()
        # Shift one white checker: 23 -> 22 (still 15 white total).
        state["points"][23] = 1
        state["points"][22] = 1

        white_board = game_state_to_open_sage_board(
            state, player_on_roll="white"
        )
        # Direct point order for white.
        self.assertEqual(white_board[24], 1)  # points[23]
        self.assertEqual(white_board[23], 1)  # points[22]
        self.assertEqual(white_board[19], -5)  # points[18], black checker
        self.assertEqual(white_board[1], -2)  # points[0], black checker

        black_board = game_state_to_open_sage_board(
            state, player_on_roll="black"
        )
        # Reverse + sign inversion for black.
        self.assertEqual(black_board[1], -1)  # -points[23]
        self.assertEqual(black_board[2], -1)  # -points[22]
        self.assertEqual(black_board[6], 5)  # -points[18]: black's own blot
        self.assertEqual(black_board[24], 2)  # -points[0]: black's own pair

        self.assertNotEqual(white_board, black_board)

    def test_bars_mapped_per_perspective(self):
        state = starting_state()
        state["bar"] = {"white": 1, "black": 2}
        # Keep totals at 15: drop one white and two black checkers.
        state["points"][23] = 1
        state["points"][18] = -3

        white_board = game_state_to_open_sage_board(
            state, player_on_roll="white"
        )
        self.assertEqual(white_board[0], 2)  # opponent (black) bar
        self.assertEqual(white_board[25], 1)  # player (white) bar

        black_board = game_state_to_open_sage_board(
            state, player_on_roll="black"
        )
        self.assertEqual(black_board[0], 1)  # opponent (white) bar
        self.assertEqual(black_board[25], 2)  # player (black) bar

    def test_borne_off_checkers_excluded_from_board(self):
        state = starting_state()
        state["home"] = {"white": 2, "black": 0}
        # Two fewer white checkers on the points.
        state["points"][5] = 3

        for player in ("white", "black"):
            board = game_state_to_open_sage_board(
                state, player_on_roll=player
            )
            self.assertEqual(len(board), 26)
            # Borne-off checkers live nowhere on the 26-element board:
            # white shows only 13 checkers on points + bar.
            white_shown = (
                sum(v for v in board[1:25] if v > 0)
                + (board[25] if player == "white" else board[0])
            )
            if player == "white":
                self.assertEqual(white_shown, 13)
            else:
                black_shown = (
                    sum(v for v in board[1:25] if v > 0) + board[25]
                )
                self.assertEqual(black_shown, 15)

    def test_cube_owner_centered(self):
        for player in ("white", "black"):
            self.assertEqual(
                game_cube_owner_to_open_sage("center", player_on_roll=player),
                "centered",
            )

    def test_cube_owner_relative_perspective(self):
        self.assertEqual(
            game_cube_owner_to_open_sage("white", player_on_roll="white"),
            "player",
        )
        self.assertEqual(
            game_cube_owner_to_open_sage("black", player_on_roll="white"),
            "opponent",
        )
        self.assertEqual(
            game_cube_owner_to_open_sage("black", player_on_roll="black"),
            "player",
        )
        self.assertEqual(
            game_cube_owner_to_open_sage("white", player_on_roll="black"),
            "opponent",
        )

    def test_invalid_points_length(self):
        for bad_points in ([0] * 23, [0] * 25):
            state = starting_state()
            state["points"] = bad_points
            with self.assertRaises(GameStateConversionError):
                game_state_to_open_sage_board(
                    state, player_on_roll="white"
                )

    def test_invalid_checker_total(self):
        state = starting_state()
        # White drops to 14 total: nothing repairs this.
        state["points"][23] = 1
        with self.assertRaises(GameStateConversionError):
            game_state_to_open_sage_board(state, player_on_roll="white")

    def test_invalid_bar_home_values(self):
        bad_states = []

        negative_bar = starting_state()
        negative_bar["bar"] = {"white": -1, "black": 0}
        bad_states.append(negative_bar)

        float_home = starting_state()
        float_home["home"] = {"white": 1.5, "black": 0}
        bad_states.append(float_home)

        bool_bar = starting_state()
        bool_bar["bar"] = {"white": True, "black": 0}
        bad_states.append(bool_bar)

        for state in bad_states:
            with self.assertRaises(GameStateConversionError):
                game_state_to_open_sage_board(
                    state, player_on_roll="white"
                )

    def test_invalid_player_rejected(self):
        for bad_player in ("green", "", None, "White"):
            with self.assertRaises(GameStateConversionError):
                game_state_to_open_sage_board(
                    starting_state(), player_on_roll=bad_player
                )
            with self.assertRaises(GameStateConversionError):
                game_cube_owner_to_open_sage(
                    "center", player_on_roll=bad_player
                )

    def test_source_state_not_mutated(self):
        state = starting_state()
        snapshot = copy.deepcopy(state)

        game_state_to_open_sage_board(state, player_on_roll="white")
        game_state_to_open_sage_board(state, player_on_roll="black")

        self.assertEqual(state, snapshot)
