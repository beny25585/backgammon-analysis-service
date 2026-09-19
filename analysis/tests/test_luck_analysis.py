from types import SimpleNamespace

from django.test import SimpleTestCase

from analysis.services.luck_analysis import (
    LuckAnalysisError,
    analyze_roll_luck,
)


STARTING_STATE = {
    "points": [
        -2,
        0,
        0,
        0,
        0,
        5,
        0,
        3,
        0,
        0,
        0,
        -5,
        5,
        0,
        0,
        0,
        -3,
        0,
        -5,
        0,
        0,
        0,
        0,
        2,
    ],
    "bar": {
        "white": 0,
        "black": 0,
    },
    "home": {
        "white": 0,
        "black": 0,
    },
    "cube": 1,
    "cubeOwner": "center",
    "turn": "white",
    "phase": "moving",
}


class LuckAnalysisRealEngineTests(
    SimpleTestCase
):
    def game_analysis(
        self,
        *,
        game_format="match",
    ):
        return SimpleNamespace(
            match_analysis=SimpleNamespace(
                input_payload={
                    "rules": {
                        "format": game_format,
                        "target_points": 5,
                        "jacoby": True,
                        "max_cube_value": 0,
                    }
                }
            ),
            white_score_before=0,
            black_score_before=0,
            is_crawford=False,
        )

    def test_normal_roll_with_real_open_sage(self):
        game = self.game_analysis()

        roll = {
            "source_event_sequence": 10,
            "player": "white",
            "dice": [6, 3],
            "state": dict(STARTING_STATE),
            "is_opening_roll": False,
        }

        result = analyze_roll_luck(
            game_analysis=game,
            roll=roll,
        )

        self.assertEqual(
            result["player"],
            "white",
        )

        self.assertEqual(
            result["dice"],
            [6, 3],
        )

        self.assertEqual(
            result["source_event_sequence"],
            10,
        )

        self.assertIsInstance(
            result["luck"],
            float,
        )

        self.assertIsInstance(
            result["actual_equity"],
            float,
        )

        self.assertIsInstance(
            result["average_equity"],
            float,
        )

        self.assertAlmostEqual(
            result["luck"],
            (
                result["actual_equity"]
                - result["average_equity"]
            ),
            places=10,
        )

        self.assertGreaterEqual(
            result["ply"],
            1,
        )

    def test_opening_roll_with_real_open_sage(self):
        game = self.game_analysis()

        state = dict(STARTING_STATE)

        roll = {
            "source_event_sequence": 5,
            "player": "white",
            "dice": [6, 2],
            "state": state,
            "is_opening_roll": True,
        }

        result = analyze_roll_luck(
            game_analysis=game,
            roll=roll,
        )

        self.assertTrue(
            result["is_opening_roll"]
        )

        self.assertIsInstance(
            result["luck"],
            float,
        )

        self.assertAlmostEqual(
            result["luck"],
            (
                result["actual_equity"]
                - result["average_equity"]
            ),
            places=10,
        )

    def test_money_game_with_real_open_sage(self):
        game = self.game_analysis(
            game_format="money"
        )

        roll = {
            "source_event_sequence": 10,
            "player": "black",
            "dice": [4, 2],
            "state": {
                **STARTING_STATE,
                "turn": "black",
            },
            "is_opening_roll": False,
        }

        result = analyze_roll_luck(
            game_analysis=game,
            roll=roll,
        )

        self.assertEqual(
            result["player"],
            "black",
        )

        self.assertIsInstance(
            result["luck"],
            float,
        )

    def test_invalid_player_rejected(self):
        game = self.game_analysis()

        roll = {
            "source_event_sequence": 10,
            "player": "green",
            "dice": [6, 3],
            "state": dict(STARTING_STATE),
            "is_opening_roll": False,
        }

        with self.assertRaises(
            LuckAnalysisError
        ):
            analyze_roll_luck(
                game_analysis=game,
                roll=roll,
            )
