import json

from django.test import SimpleTestCase

from analysis.engines.open_sage import (
    DEFAULT_EVAL_LEVEL,
    OPEN_SAGE_ENGINE,
    OPEN_SAGE_VERSION,
    OpenSageEngine,
    OpenSageError,
)


class OpenSageEngineTests(SimpleTestCase):
    def test_engine_initializes_with_1ply_default(self):
        engine = OpenSageEngine()
        self.assertEqual(engine.eval_level, "1ply")
        self.assertEqual(engine.eval_level, DEFAULT_EVAL_LEVEL)
        self.assertIsNotNone(engine.analyzer)

    def test_checker_play_starting_board(self):
        from bgsage import STARTING_BOARD

        engine = OpenSageEngine()
        result = engine.analyze_checker_play(
            board=list(STARTING_BOARD), die1=3, die2=1, max_cube_value=0,
            beaver=False
        )

        self.assertIsInstance(result, dict)
        self.assertEqual(result["engine"], OPEN_SAGE_ENGINE)
        self.assertEqual(result["engine"], "open_sage")
        self.assertEqual(result["engine_version"], OPEN_SAGE_VERSION)
        self.assertEqual(
            result["engine_version"],
            "2.0.20260907@d8325a491168062df1047ffd998f3a5dfb426a0c",
        )

        self.assertTrue(result["moves"], "expected at least one legal move")
        first = result["moves"][0]
        self.assertIn("equity", first)
        self.assertIsInstance(first["equity"], float)
        self.assertIn("probabilities", first)
        for key in (
            "win",
            "gammon_win",
            "backgammon_win",
            "gammon_loss",
            "backgammon_loss",
        ):
            self.assertIn(key, first["probabilities"])

        # Output must be plain JSON-serializable data.
        json.dumps(result)

    def test_cube_action_starting_board(self):
        from bgsage import STARTING_BOARD

        engine = OpenSageEngine()
        result = engine.analyze_cube_action(
            board=list(STARTING_BOARD), max_cube_value=0, beaver=False
        )

        self.assertIn("no_double", result["equities"])
        self.assertIn("double_take", result["equities"])
        self.assertIn("double_pass", result["equities"])
        self.assertIn("optimal_action", result)
        self.assertIsInstance(result["optimal_action"], str)
        self.assertIn("should_double", result)
        self.assertIn("should_take", result)
        self.assertIsInstance(result["should_double"], bool)
        self.assertIsInstance(result["should_take"], bool)

        json.dumps(result)

    def test_roll_luck(self):
        from bgsage import STARTING_BOARD

        engine = OpenSageEngine()
        # Ordinary analysis stays at the 1-ply default.
        self.assertEqual(engine.eval_level, "1ply")

        result = engine.analyze_roll_luck(
            board=list(STARTING_BOARD), die1=3, die2=1, max_cube_value=8,
            beaver=False
        )

        self.assertIsNotNone(result, "luck must be computed, not None")
        self.assertIn("luck", result)
        self.assertIn("actual_equity", result)
        self.assertIn("average_equity", result)
        self.assertIn("ply", result)
        self.assertIn("level_label", result)
        json.dumps(result)

        # The dedicated 2-ply luck analyzer is retained and reused.
        first_luck_analyzer = engine._luck_analyzer
        self.assertIsNotNone(first_luck_analyzer)
        second = engine.analyze_roll_luck(
            board=list(STARTING_BOARD), die1=3, die2=1, max_cube_value=8,
            beaver=False
        )
        self.assertIsNotNone(second)
        self.assertIs(engine._luck_analyzer, first_luck_analyzer)

    def test_checker_play_capped_cube(self):
        from bgsage import STARTING_BOARD

        engine = OpenSageEngine()
        result = engine.analyze_checker_play(
            board=list(STARTING_BOARD), die1=3, die2=1, max_cube_value=8,
            beaver=False
        )

        self.assertIsInstance(result, dict)
        self.assertTrue(result["moves"], "expected at least one legal move")
        json.dumps(result)

    def test_cube_action_capped_cube(self):
        from bgsage import STARTING_BOARD

        engine = OpenSageEngine()
        result = engine.analyze_cube_action(
            board=list(STARTING_BOARD), max_cube_value=8, beaver=False
        )

        self.assertIsInstance(result, dict)
        self.assertIn("no_double", result["equities"])
        self.assertIn("double_take", result["equities"])
        self.assertIn("double_pass", result["equities"])
        self.assertIn("optimal_action", result)
        json.dumps(result)

    def test_invalid_board_length_rejected(self):
        engine = OpenSageEngine()
        # 24 elements = Game-style board, must never reach Open Sage.
        with self.assertRaises(OpenSageError):
            engine.analyze_checker_play(board=[0] * 24, die1=3, die2=1)

    def test_invalid_board_element_rejected(self):
        engine = OpenSageEngine()
        board = [0] * 26
        board[5] = "not-an-int"
        with self.assertRaises(OpenSageError):
            engine.analyze_checker_play(board=board, die1=3, die2=1)
