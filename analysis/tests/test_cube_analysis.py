from types import SimpleNamespace

from django.test import SimpleTestCase

from analysis.services.cube_analysis import analyze_cube_decision


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
        "bar": {
            "white": 0,
            "black": 0,
        },
        "home": {
            "white": 0,
            "black": 0,
        },
        "turn": "white",
        "phase": "rolling",

        "cube": 1,
        "cubeOwner": "center",

        "doublingEnabled": True,
        "maxCube": 8,

        "jacoby": False,
    }


def make_game_analysis():
    return SimpleNamespace(
        white_score_before=0,
        black_score_before=0,
        is_crawford=False,

        match_analysis=SimpleNamespace(
            input_payload={
                "rules": {
                    "format": "match",
                    "target_points": 7,
                    "time_control": "normal",

                    "doubling_enabled": True,
                    "max_cube_value": 8,

                    "jacoby": False,
                    "beaver": False,
                }
            }
        ),
    )


class CubeAnalysisRealEngineTests(SimpleTestCase):

    def test_no_double_with_real_open_sage(self):
        game_analysis = make_game_analysis()

        decision = {
            "player": "white",
            "decision_type": "no_double",
            "played_action": "no_double",
            "before_state": starting_state(),
            "source_event_sequence": 10,
        }

        result = analyze_cube_decision(
            game_analysis=game_analysis,
            decision=decision,
        )

        self.assertEqual(
            result["player"],
            "white",
        )

        self.assertEqual(
            result["decision_type"],
            "no_double",
        )

        self.assertEqual(
            result["source_event_sequence"],
            10,
        )

        self.assertGreaterEqual(
            result["best_equity"],
            result["played_equity"],
        )

        self.assertGreaterEqual(
            result["equity_loss"],
            0.0,
        )

        self.assertIn(
            "no_double",
            result["alternatives"],
        )

        self.assertIn(
            "double_take",
            result["alternatives"],
        )

        self.assertIn(
            "double_pass",
            result["alternatives"],
        )

        self.assertEqual(
            result["raw_analysis"]["engine"],
            "open_sage",
        )

    def test_double_with_real_open_sage(self):
        game_analysis = make_game_analysis()

        state = starting_state()
        state["phase"] = "doubling_offered"
        state["doubleOfferedBy"] = "white"

        decision = {
            "player": "white",
            "decision_type": "double",
            "played_action": "double",
            "before_state": state,
            "source_event_sequence": 20,
        }

        result = analyze_cube_decision(
            game_analysis=game_analysis,
            decision=decision,
        )

        self.assertEqual(
            result["decision_type"],
            "double",
        )

        self.assertGreaterEqual(
            result["best_equity"],
            result["played_equity"],
        )

        self.assertGreaterEqual(
            result["equity_loss"],
            0.0,
        )

    def test_take_with_real_open_sage(self):
        game_analysis = make_game_analysis()

        state = starting_state()
        state["phase"] = "doubling_offered"
        state["doubleOfferedBy"] = "white"

        decision = {
            "player": "black",
            "decision_type": "take",
            "played_action": "take",

            "offerer": "white",

            "before_state": state,

            "double_sequence": 30,
            "source_event_sequence": 31,
        }

        result = analyze_cube_decision(
            game_analysis=game_analysis,
            decision=decision,
        )

        self.assertEqual(
            result["player"],
            "black",
        )

        self.assertEqual(
            result["decision_type"],
            "take",
        )

        self.assertEqual(
            result["raw_analysis"]["engine_player"],
            "white",
        )

        self.assertGreaterEqual(
            result["best_equity"],
            result["played_equity"],
        )

        self.assertGreaterEqual(
            result["equity_loss"],
            0.0,
        )
