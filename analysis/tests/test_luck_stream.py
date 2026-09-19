from types import SimpleNamespace

from django.test import SimpleTestCase

from analysis.services.luck_stream import (
    LuckStreamError,
    extract_luck_rolls,
)


def event(
    sequence,
    event_type,
    *,
    turn=None,
    dice=None,
    phase=None,
    **extra,
):
    payload = {
        "turn": turn,
        "dice": dice,
        "phase": phase,
        **extra,
    }

    return {
        "sequence": sequence,
        "event_type": event_type,
        "payload": payload,
    }


class LuckStreamTests(SimpleTestCase):
    def game(self, events):
        return SimpleNamespace(
            input_events=events,
        )

    def test_extracts_normal_roll(self):
        game = self.game(
            [
                event(
                    10,
                    "roll",
                    turn="white",
                    dice=[6, 3],
                    phase="moving",
                ),
            ]
        )

        rolls = extract_luck_rolls(game)

        self.assertEqual(len(rolls), 1)

        self.assertEqual(
            rolls[0]["player"],
            "white",
        )

        self.assertEqual(
            rolls[0]["dice"],
            [6, 3],
        )

        self.assertEqual(
            rolls[0]["source_event_sequence"],
            10,
        )

        self.assertFalse(
            rolls[0]["is_opening_roll"]
        )

    def test_extracts_opening_roll(self):
        game = self.game(
            [
                event(
                    5,
                    "opening_result_done",
                    turn="black",
                    dice=[2, 6],
                    phase="moving",
                ),
            ]
        )

        rolls = extract_luck_rolls(game)

        self.assertEqual(len(rolls), 1)

        self.assertEqual(
            rolls[0]["player"],
            "black",
        )

        self.assertEqual(
            rolls[0]["dice"],
            [2, 6],
        )

        self.assertTrue(
            rolls[0]["is_opening_roll"]
        )

    def test_roll_without_moves_is_still_included(self):
        game = self.game(
            [
                event(
                    10,
                    "roll",
                    turn="white",
                    dice=[5, 2],
                    phase="moving",
                ),
                event(
                    11,
                    "end_turn",
                    turn="black",
                    dice=[],
                    phase="rolling",
                ),
            ]
        )

        rolls = extract_luck_rolls(game)

        self.assertEqual(len(rolls), 1)

        self.assertEqual(
            rolls[0]["dice"],
            [5, 2],
        )

    def test_ignores_non_roll_events(self):
        game = self.game(
            [
                event(
                    10,
                    "move",
                    turn="white",
                    dice=[6, 3],
                    phase="moving",
                ),
                event(
                    11,
                    "end_turn",
                    turn="black",
                    dice=[],
                    phase="rolling",
                ),
            ]
        )

        rolls = extract_luck_rolls(game)

        self.assertEqual(rolls, [])

    def test_ignores_roll_outside_moving_phase(self):
        game = self.game(
            [
                event(
                    10,
                    "roll",
                    turn="white",
                    dice=[6, 3],
                    phase="opening_roll",
                ),
            ]
        )

        rolls = extract_luck_rolls(game)

        self.assertEqual(rolls, [])

    def test_rolls_are_sorted_by_sequence(self):
        game = self.game(
            [
                event(
                    20,
                    "roll",
                    turn="black",
                    dice=[4, 1],
                    phase="moving",
                ),
                event(
                    10,
                    "roll",
                    turn="white",
                    dice=[6, 2],
                    phase="moving",
                ),
            ]
        )

        rolls = extract_luck_rolls(game)

        self.assertEqual(
            [
                roll["source_event_sequence"]
                for roll in rolls
            ],
            [10, 20],
        )

    def test_invalid_dice_rejected(self):
        game = self.game(
            [
                event(
                    10,
                    "roll",
                    turn="white",
                    dice=[7, 2],
                    phase="moving",
                ),
            ]
        )

        with self.assertRaises(
            LuckStreamError
        ):
            extract_luck_rolls(game)

    def test_invalid_player_rejected(self):
        game = self.game(
            [
                event(
                    10,
                    "roll",
                    turn="green",
                    dice=[6, 2],
                    phase="moving",
                ),
            ]
        )

        with self.assertRaises(
            LuckStreamError
        ):
            extract_luck_rolls(game)
