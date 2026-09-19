from types import SimpleNamespace

from django.test import SimpleTestCase

from analysis.services.decision_stream import extract_checker_decisions


def game_with_events(events):
    return SimpleNamespace(input_events=events)


def event(sequence, event_type, payload, player_color=None):
    return {
        "sequence": sequence,
        "event_type": event_type,
        "player_color": player_color,
        "payload": payload,
    }


def state(
    *,
    turn="white",
    phase="moving",
    dice=None,
    remaining=None,
    last_move=None,
):
    return {
        "gameId": "game-1",
        "points": [0] * 24,
        "bar": {"white": 0, "black": 0},
        "home": {"white": 0, "black": 0},
        "turn": turn,
        "phase": phase,
        "dice": list(dice or []),
        "remaining": list(remaining or []),
        "lastMove": last_move,
        "cube": 1,
        "cubeOwner": "center",
    }


class CheckerDecisionStreamTests(SimpleTestCase):
    def _interrupted_double_events(self, *, remaining):
        return [
            event(159, "roll", state(dice=[5, 5], remaining=[5] * 4), "white"),
            event(162, "move", state(
                dice=[5, 5], remaining=remaining,
                last_move=[{"from": 11, "to": 6},
                           {"from": 5, "to": 0},
                           {"from": 7, "to": 2}],
            ), "white"),
        ]

    def test_partial_double_at_end_of_stream_is_not_scored(self):
        events = self._interrupted_double_events(remaining=[5])
        events[-1]["payload"]["clock"] = {"white": 0, "black": 32566}
        self.assertEqual(extract_checker_decisions(game_with_events(events)), [])

    def test_partial_turn_before_another_roll_is_not_scored(self):
        events = self._interrupted_double_events(remaining=[5])
        events.extend([
            event(163, "roll", state(turn="black", dice=[6, 1], remaining=[6, 1]), "black"),
            event(164, "move", state(turn="black", dice=[6, 1], remaining=[]), "black"),
            event(165, "end_turn", state(turn="white", phase="rolling"), "black"),
        ])
        decisions = extract_checker_decisions(game_with_events(events))
        self.assertEqual([d["start_sequence"] for d in decisions], [163])

    def test_exhausted_dice_without_confirmation_are_scored(self):
        events = self._interrupted_double_events(remaining=[])
        decisions = extract_checker_decisions(game_with_events(events))
        self.assertEqual(len(decisions), 1)
        self.assertEqual(decisions[0]["end_sequence"], 162)

    def test_undo_to_partial_turn_at_end_is_not_scored(self):
        events = self._interrupted_double_events(remaining=[])
        events.append(event(163, "undo", state(dice=[5, 5], remaining=[5]), "white"))
        self.assertEqual(extract_checker_decisions(game_with_events(events)), [])

    def test_winning_move_with_unused_dice_is_scored(self):
        events = self._interrupted_double_events(remaining=[5])
        events[-1]["payload"]["phase"] = "game_over"
        decisions = extract_checker_decisions(game_with_events(events))
        self.assertEqual(len(decisions), 1)
        self.assertEqual(decisions[0]["end_sequence"], 162)

    def test_normal_roll_moves_and_end_turn(self):
        events = [
            event(
                1,
                "roll",
                state(
                    turn="white",
                    phase="moving",
                    dice=[6, 3],
                    remaining=[6, 3],
                    last_move=[],
                ),
                player_color="white",
            ),
            event(
                2,
                "move",
                state(
                    turn="white",
                    phase="moving",
                    dice=[6, 3],
                    remaining=[3],
                    last_move=[
                        {"from": 23, "to": 17},
                    ],
                ),
                player_color="white",
            ),
            event(
                3,
                "move",
                state(
                    turn="white",
                    phase="moving",
                    dice=[6, 3],
                    remaining=[],
                    last_move=[
                        {"from": 23, "to": 17},
                        {"from": 17, "to": 14},
                    ],
                ),
                player_color="white",
            ),
            event(
                4,
                "end_turn",
                state(
                    turn="black",
                    phase="rolling",
                    dice=[],
                    remaining=[],
                    last_move=None,
                ),
                player_color="white",
            ),
        ]

        decisions = extract_checker_decisions(game_with_events(events))

        self.assertEqual(len(decisions), 1)

        decision = decisions[0]

        self.assertEqual(decision["player"], "white")
        self.assertEqual(decision["dice"], [6, 3])
        self.assertEqual(decision["start_sequence"], 1)
        self.assertEqual(decision["end_sequence"], 4)

        self.assertEqual(
            decision["played_action"],
            [
                {"from": 23, "to": 17},
                {"from": 17, "to": 14},
            ],
        )

        self.assertEqual(
            decision["before_state"]["phase"],
            "moving",
        )
        self.assertEqual(
            decision["after_state"]["turn"],
            "black",
        )

        self.assertFalse(decision["is_opening_roll"])

    def test_opening_result_creates_first_checker_decision(self):
        events = [
            event(
                1,
                "opening_result_done",
                state(
                    turn="black",
                    phase="moving",
                    dice=[5, 2],
                    remaining=[5, 2],
                    last_move=[],
                ),
            ),
            event(
                2,
                "move",
                state(
                    turn="black",
                    phase="moving",
                    dice=[5, 2],
                    remaining=[2],
                    last_move=[
                        {"from": 0, "to": 5},
                    ],
                ),
                player_color="black",
            ),
            event(
                3,
                "end_turn",
                state(
                    turn="white",
                    phase="rolling",
                    dice=[],
                    remaining=[],
                    last_move=None,
                ),
                player_color="black",
            ),
        ]

        decisions = extract_checker_decisions(game_with_events(events))

        self.assertEqual(len(decisions), 1)

        decision = decisions[0]

        self.assertEqual(decision["player"], "black")
        self.assertEqual(decision["dice"], [5, 2])
        self.assertTrue(decision["is_opening_roll"])

    def test_move_can_finish_turn_automatically(self):
        events = [
            event(
                10,
                "roll",
                state(
                    turn="white",
                    phase="moving",
                    dice=[6, 1],
                    remaining=[6, 1],
                    last_move=[],
                ),
                player_color="white",
            ),
            event(
                11,
                "move",
                state(
                    turn="black",
                    phase="rolling",
                    dice=[],
                    remaining=[],
                    last_move=[
                        {"from": 23, "to": 17},
                    ],
                ),
                player_color="white",
            ),
        ]

        decisions = extract_checker_decisions(game_with_events(events))

        self.assertEqual(len(decisions), 1)

        decision = decisions[0]

        self.assertEqual(decision["start_sequence"], 10)
        self.assertEqual(decision["end_sequence"], 11)
        self.assertEqual(decision["player"], "white")

    def test_undo_replaces_played_action_with_restored_move_list(self):
        events = [
            event(
                1,
                "roll",
                state(
                    turn="white",
                    phase="moving",
                    dice=[5, 3],
                    remaining=[5, 3],
                    last_move=[],
                ),
                player_color="white",
            ),
            event(
                2,
                "move",
                state(
                    turn="white",
                    phase="moving",
                    dice=[5, 3],
                    remaining=[3],
                    last_move=[
                        {"from": 23, "to": 18},
                    ],
                ),
                player_color="white",
            ),
            event(
                3,
                "move",
                state(
                    turn="white",
                    phase="moving",
                    dice=[5, 3],
                    remaining=[],
                    last_move=[
                        {"from": 23, "to": 18},
                        {"from": 18, "to": 15},
                    ],
                ),
                player_color="white",
            ),
            event(
                4,
                "undo",
                state(
                    turn="white",
                    phase="moving",
                    dice=[5, 3],
                    remaining=[3],
                    last_move=[
                        {"from": 23, "to": 18},
                    ],
                ),
                player_color="white",
            ),
            event(
                5,
                "move",
                state(
                    turn="white",
                    phase="moving",
                    dice=[5, 3],
                    remaining=[],
                    last_move=[
                        {"from": 23, "to": 18},
                        {"from": 12, "to": 9},
                    ],
                ),
                player_color="white",
            ),
            event(
                6,
                "end_turn",
                state(
                    turn="black",
                    phase="rolling",
                    dice=[],
                    remaining=[],
                    last_move=None,
                ),
                player_color="white",
            ),
        ]

        decisions = extract_checker_decisions(game_with_events(events))

        self.assertEqual(len(decisions), 1)

        self.assertEqual(
            decisions[0]["played_action"],
            [
                {"from": 23, "to": 18},
                {"from": 12, "to": 9},
            ],
        )

    def test_roll_with_no_legal_moves_is_not_checker_decision(self):
        events = [
            event(
                1,
                "roll",
                state(
                    turn="black",
                    phase="rolling",
                    dice=[6, 5],
                    remaining=[],
                    last_move=[],
                ),
                player_color="white",
            ),
        ]

        decisions = extract_checker_decisions(game_with_events(events))

        self.assertEqual(decisions, [])

    def test_two_consecutive_turns_create_two_decisions(self):
        events = [
            event(
                1,
                "roll",
                state(
                    turn="white",
                    phase="moving",
                    dice=[6, 2],
                    remaining=[6, 2],
                    last_move=[],
                ),
                player_color="white",
            ),
            event(
                2,
                "move",
                state(
                    turn="white",
                    phase="moving",
                    dice=[6, 2],
                    remaining=[],
                    last_move=[
                        {"from": 23, "to": 17},
                        {"from": 17, "to": 15},
                    ],
                ),
                player_color="white",
            ),
            event(
                3,
                "end_turn",
                state(
                    turn="black",
                    phase="rolling",
                    dice=[],
                    remaining=[],
                    last_move=None,
                ),
                player_color="white",
            ),
            event(
                4,
                "roll",
                state(
                    turn="black",
                    phase="moving",
                    dice=[4, 1],
                    remaining=[4, 1],
                    last_move=[],
                ),
                player_color="black",
            ),
            event(
                5,
                "move",
                state(
                    turn="black",
                    phase="moving",
                    dice=[4, 1],
                    remaining=[],
                    last_move=[
                        {"from": 0, "to": 4},
                        {"from": 4, "to": 5},
                    ],
                ),
                player_color="black",
            ),
            event(
                6,
                "end_turn",
                state(
                    turn="white",
                    phase="rolling",
                    dice=[],
                    remaining=[],
                    last_move=None,
                ),
                player_color="black",
            ),
        ]

        decisions = extract_checker_decisions(game_with_events(events))

        self.assertEqual(len(decisions), 2)

        self.assertEqual(decisions[0]["player"], "white")
        self.assertEqual(decisions[0]["dice"], [6, 2])

        self.assertEqual(decisions[1]["player"], "black")
        self.assertEqual(decisions[1]["dice"], [4, 1])
