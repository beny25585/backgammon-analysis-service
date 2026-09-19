from types import SimpleNamespace

from django.test import SimpleTestCase

from analysis.services.checker_analysis import (
    CheckerAnalysisError,
    analyze_checker_decision,
)


STARTING_POINTS = [0] * 24
STARTING_POINTS[23] = 2
STARTING_POINTS[12] = 5
STARTING_POINTS[7] = 3
STARTING_POINTS[5] = 5
STARTING_POINTS[0] = -2
STARTING_POINTS[11] = -5
STARTING_POINTS[16] = -3
STARTING_POINTS[18] = -5


def make_state(
    *,
    points=None,
    turn="white",
    dice=None,
    cube=1,
    cube_owner="center",
):
    return {
        "points": list(points or STARTING_POINTS),
        "bar": {"white": 0, "black": 0},
        "home": {"white": 0, "black": 0},
        "turn": turn,
        "dice": list(dice or [6, 1]),
        "remaining": list(dice or [6, 1]),
        "phase": "moving",
        "cube": cube,
        "cubeOwner": cube_owner,
        "lastMove": [],
    }


def make_game_analysis(
    *,
    format="match",
    target_points=7,
    white_score=2,
    black_score=3,
    is_crawford=False,
):
    return SimpleNamespace(
        white_score_before=white_score,
        black_score_before=black_score,
        is_crawford=is_crawford,
        match_analysis=SimpleNamespace(
            input_payload={
                "rules": {
                    "format": format,
                    "target_points": target_points,
                    "time_control": "normal",
                    "doubling_enabled": True,
                    "max_cube_value": 8,
                    "jacoby": False,
                    "beaver": False,
                }
            }
        ),
    )


class FakeEngine:
    def __init__(self):
        self.calls = []

    def analyze_checker_play(self, **kwargs):
        self.calls.append(kwargs)

        played_board = kwargs["force_boards"][0]

        best_board = list(played_board)
        best_board[1] += 1
        best_board[2] -= 1

        return {
            "engine": "fake",
            "engine_version": "fake-1",
            "eval_level": "1ply",
            "board": kwargs["board"],
            "dice": [kwargs["die1"], kwargs["die2"]],
            "moves": [
                {
                    "board": best_board,
                    "equity": 0.40,
                    "cubeless_equity": 0.35,
                    "equity_diff": 0.0,
                    "eval_level": "1ply",
                    "probabilities": {
                        "win": 0.60,
                        "gammon_win": 0.10,
                        "backgammon_win": 0.01,
                        "gammon_loss": 0.05,
                        "backgammon_loss": 0.01,
                    },
                },
                {
                    "board": played_board,
                    "equity": 0.25,
                    "cubeless_equity": 0.20,
                    "equity_diff": -0.15,
                    "eval_level": "1ply",
                    "probabilities": {
                        "win": 0.55,
                        "gammon_win": 0.08,
                        "backgammon_win": 0.01,
                        "gammon_loss": 0.07,
                        "backgammon_loss": 0.01,
                    },
                },
            ],
        }


class CheckerAnalysisTests(SimpleTestCase):
    def test_white_match_decision(self):
        before_state = make_state(
            turn="white",
            dice=[6, 1],
            cube=2,
            cube_owner="white",
        )

        after_points = list(STARTING_POINTS)
        after_points[23] -= 1
        after_points[17] += 1
        after_points[7] -= 1
        after_points[6] += 1

        after_state = make_state(
            points=after_points,
            turn="white",
            dice=[6, 1],
            cube=2,
            cube_owner="white",
        )

        decision = {
            "player": "white",
            "dice": [6, 1],
            "before_state": before_state,
            "after_state": after_state,
            "played_action": [
                {"from": 23, "to": 17},
                {"from": 7, "to": 6},
            ],
            "start_sequence": 10,
            "end_sequence": 12,
        }

        game_analysis = make_game_analysis(
            target_points=7,
            white_score=2,
            black_score=3,
            is_crawford=True,
        )

        engine = FakeEngine()

        result = analyze_checker_decision(
            game_analysis=game_analysis,
            decision=decision,
            engine=engine,
        )

        self.assertEqual(len(engine.calls), 1)

        call = engine.calls[0]

        self.assertEqual(call["die1"], 6)
        self.assertEqual(call["die2"], 1)

        # White needs 5, black needs 4.
        self.assertEqual(call["away1"], 5)
        self.assertEqual(call["away2"], 4)

        self.assertEqual(call["cube_value"], 2)
        self.assertEqual(call["cube_owner"], "player")
        self.assertTrue(call["is_crawford"])

        self.assertEqual(call["max_cube_value"], 8)
        self.assertFalse(call["jacoby"])
        self.assertFalse(call["beaver"])

        self.assertEqual(
            call["force_boards"][0],
            result["raw_analysis"]["moves"][1]["board"],
        )

        self.assertEqual(result["player"], "white")
        self.assertEqual(result["dice"], [6, 1])

        self.assertAlmostEqual(result["best_equity"], 0.40)
        self.assertAlmostEqual(result["played_equity"], 0.25)
        self.assertAlmostEqual(result["equity_loss"], 0.15)

        self.assertEqual(result["source_event_sequence"], 12)

    def test_black_away_scores_are_from_black_perspective(self):
        before_state = make_state(
            turn="black",
            dice=[5, 2],
        )

        after_state = make_state(
            turn="black",
            dice=[5, 2],
        )

        decision = {
            "player": "black",
            "dice": [5, 2],
            "before_state": before_state,
            "after_state": after_state,
            "start_sequence": 20,
            "end_sequence": 21,
        }

        game_analysis = make_game_analysis(
            target_points=7,
            white_score=2,
            black_score=3,
        )

        engine = FakeEngine()

        analyze_checker_decision(
            game_analysis=game_analysis,
            decision=decision,
            engine=engine,
        )

        call = engine.calls[0]

        # Black needs 4, white needs 5.
        self.assertEqual(call["away1"], 4)
        self.assertEqual(call["away2"], 5)

    def test_money_game_uses_zero_away_scores(self):
        decision = {
            "player": "white",
            "dice": [4, 2],
            "before_state": make_state(dice=[4, 2]),
            "after_state": make_state(dice=[4, 2]),
            "start_sequence": 1,
            "end_sequence": 2,
        }

        game_analysis = make_game_analysis(
            format="money",
            white_score=0,
            black_score=0,
        )

        engine = FakeEngine()

        analyze_checker_decision(
            game_analysis=game_analysis,
            decision=decision,
            engine=engine,
        )

        call = engine.calls[0]

        self.assertEqual(call["away1"], 0)
        self.assertEqual(call["away2"], 0)

    def test_invalid_player_rejected(self):
        with self.assertRaises(CheckerAnalysisError):
            analyze_checker_decision(
                game_analysis=make_game_analysis(),
                decision={
                    "player": "red",
                    "dice": [6, 1],
                    "before_state": make_state(),
                    "after_state": make_state(),
                },
                engine=FakeEngine(),
            )

    def test_missing_before_state_rejected(self):
        with self.assertRaises(CheckerAnalysisError):
            analyze_checker_decision(
                game_analysis=make_game_analysis(),
                decision={
                    "player": "white",
                    "dice": [6, 1],
                    "after_state": make_state(),
                },
                engine=FakeEngine(),
            )

    def test_missing_after_state_rejected(self):
        with self.assertRaises(CheckerAnalysisError):
            analyze_checker_decision(
                game_analysis=make_game_analysis(),
                decision={
                    "player": "white",
                    "dice": [6, 1],
                    "before_state": make_state(),
                },
                engine=FakeEngine(),
            )

    def test_invalid_dice_rejected(self):
        with self.assertRaises(CheckerAnalysisError):
            analyze_checker_decision(
                game_analysis=make_game_analysis(),
                decision={
                    "player": "white",
                    "dice": [6],
                    "before_state": make_state(),
                    "after_state": make_state(),
                },
                engine=FakeEngine(),
            )


class EmptyMovesEngine:
    def analyze_checker_play(self, **kwargs):
        return {"moves": []}


class MissingPlayedMoveEngine:
    def analyze_checker_play(self, **kwargs):
        other_board = list(kwargs["force_boards"][0])
        other_board[1] += 1
        other_board[2] -= 1

        return {
            "moves": [
                {
                    "board": other_board,
                    "equity": 0.4,
                    "equity_diff": 0.0,
                    "probabilities": {},
                }
            ]
        }


class CheckerAnalysisEngineErrorsTests(SimpleTestCase):
    def _decision(self):
        return {
            "player": "white",
            "dice": [6, 1],
            "before_state": make_state(dice=[6, 1]),
            "after_state": make_state(dice=[6, 1]),
            "start_sequence": 1,
            "end_sequence": 2,
        }

    def test_empty_moves_rejected(self):
        with self.assertRaises(CheckerAnalysisError):
            analyze_checker_decision(
                game_analysis=make_game_analysis(),
                decision=self._decision(),
                engine=EmptyMovesEngine(),
            )

    def test_played_board_missing_from_result_rejected(self):
        with self.assertRaises(CheckerAnalysisError):
            analyze_checker_decision(
                game_analysis=make_game_analysis(),
                decision=self._decision(),
                engine=MissingPlayedMoveEngine(),
            )
