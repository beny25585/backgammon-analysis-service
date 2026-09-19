from types import SimpleNamespace

from django.test import SimpleTestCase

from analysis.services.decision_stream import (
    CubeDecisionStreamError,
    extract_cube_decisions,
)


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
    phase="rolling",
    turn="white",
    cube=1,
    cube_owner="center",
    doubling_enabled=True,
    max_cube=64,
    double_offered_by=None,
    winner=None,
):
    return {
        "phase": phase,
        "turn": turn,
        "cube": cube,
        "cubeOwner": cube_owner,
        "doublingEnabled": doubling_enabled,
        "maxCube": max_cube,
        "doubleOfferedBy": double_offered_by,
        "winner": winner,
    }


class CubeDecisionStreamTests(SimpleTestCase):
    def test_roll_creates_no_double_decision(self):
        events = [
            event(
                10,
                "roll",
                state(
                    phase="moving",
                    turn="white",
                    cube=1,
                    cube_owner="center",
                ),
                player_color="white",
            )
        ]

        decisions = extract_cube_decisions(
            game_with_events(events)
        )

        self.assertEqual(len(decisions), 1)

        decision = decisions[0]

        self.assertEqual(decision["player"], "white")
        self.assertEqual(
            decision["decision_type"],
            "no_double",
        )
        self.assertEqual(
            decision["played_action"],
            "no_double",
        )
        self.assertEqual(
            decision["source_event_sequence"],
            10,
        )

    def test_roll_does_not_create_no_double_when_cube_unavailable(self):
        events = [
            event(
                1,
                "roll",
                state(
                    phase="moving",
                    turn="white",
                    cube=2,
                    cube_owner="black",
                ),
                player_color="white",
            )
        ]

        decisions = extract_cube_decisions(
            game_with_events(events)
        )

        self.assertEqual(decisions, [])

    def test_roll_does_not_create_no_double_when_doubling_disabled(self):
        events = [
            event(
                1,
                "roll",
                state(
                    phase="moving",
                    doubling_enabled=False,
                ),
                player_color="white",
            )
        ]

        decisions = extract_cube_decisions(
            game_with_events(events)
        )

        self.assertEqual(decisions, [])

    def test_roll_does_not_create_no_double_at_cube_cap(self):
        events = [
            event(
                1,
                "roll",
                state(
                    phase="moving",
                    cube=8,
                    cube_owner="white",
                    max_cube=8,
                ),
                player_color="white",
            )
        ]

        decisions = extract_cube_decisions(
            game_with_events(events)
        )

        self.assertEqual(decisions, [])

    def test_unlimited_cube_allows_no_double(self):
        events = [
            event(
                1,
                "roll",
                state(
                    phase="moving",
                    cube=64,
                    cube_owner="white",
                    max_cube=0,
                ),
                player_color="white",
            )
        ]

        decisions = extract_cube_decisions(
            game_with_events(events)
        )

        self.assertEqual(len(decisions), 1)
        self.assertEqual(
            decisions[0]["decision_type"],
            "no_double",
        )

    def test_double_creates_double_decision(self):
        events = [
            event(
                5,
                "double",
                state(
                    phase="doubling_offered",
                    turn="white",
                    cube=1,
                    cube_owner="center",
                    double_offered_by="white",
                ),
                player_color="white",
            )
        ]

        decisions = extract_cube_decisions(
            game_with_events(events)
        )

        self.assertEqual(len(decisions), 1)

        decision = decisions[0]

        self.assertEqual(decision["player"], "white")
        self.assertEqual(
            decision["decision_type"],
            "double",
        )
        self.assertEqual(
            decision["played_action"],
            "double",
        )

    def test_owned_cube_creates_redouble_decision(self):
        events = [
            event(
                7,
                "double",
                state(
                    phase="doubling_offered",
                    turn="white",
                    cube=2,
                    cube_owner="white",
                    double_offered_by="white",
                ),
                player_color="white",
            )
        ]

        decisions = extract_cube_decisions(
            game_with_events(events)
        )

        self.assertEqual(len(decisions), 1)
        self.assertEqual(
            decisions[0]["decision_type"],
            "redouble",
        )

    def test_double_and_take_create_two_decisions(self):
        offered_state = state(
            phase="doubling_offered",
            turn="white",
            cube=1,
            cube_owner="center",
            double_offered_by="white",
        )

        accepted_state = state(
            phase="rolling",
            turn="white",
            cube=2,
            cube_owner="black",
            double_offered_by=None,
        )

        events = [
            event(
                10,
                "double",
                offered_state,
                player_color="white",
            ),
            event(
                11,
                "double_response",
                accepted_state,
                player_color="black",
            ),
        ]

        decisions = extract_cube_decisions(
            game_with_events(events)
        )

        self.assertEqual(len(decisions), 2)

        self.assertEqual(
            decisions[0]["decision_type"],
            "double",
        )

        take = decisions[1]

        self.assertEqual(take["player"], "black")
        self.assertEqual(
            take["decision_type"],
            "take",
        )
        self.assertEqual(
            take["played_action"],
            "take",
        )
        self.assertEqual(
            take["offerer"],
            "white",
        )
        self.assertEqual(
            take["double_sequence"],
            10,
        )
        self.assertEqual(
            take["source_event_sequence"],
            11,
        )
        self.assertEqual(
            take["before_state"],
            offered_state,
        )

    def test_double_and_pass_create_two_decisions(self):
        offered_state = state(
            phase="doubling_offered",
            turn="white",
            cube=2,
            cube_owner="white",
            double_offered_by="white",
        )

        passed_state = state(
            phase="game_over",
            turn="white",
            cube=2,
            cube_owner="white",
            winner="white",
        )

        events = [
            event(
                20,
                "double",
                offered_state,
                player_color="white",
            ),
            event(
                21,
                "double_response",
                passed_state,
                player_color="black",
            ),
        ]

        decisions = extract_cube_decisions(
            game_with_events(events)
        )

        self.assertEqual(len(decisions), 2)

        response = decisions[1]

        self.assertEqual(
            response["player"],
            "black",
        )
        self.assertEqual(
            response["decision_type"],
            "pass",
        )
        self.assertEqual(
            response["played_action"],
            "pass",
        )

    def test_response_player_can_be_inferred(self):
        events = [
            event(
                1,
                "double",
                state(
                    phase="doubling_offered",
                    cube_owner="center",
                    double_offered_by="white",
                ),
                player_color="white",
            ),
            event(
                2,
                "double_response",
                state(
                    phase="rolling",
                    cube=2,
                    cube_owner="black",
                ),
                player_color=None,
            ),
        ]

        decisions = extract_cube_decisions(
            game_with_events(events)
        )

        self.assertEqual(
            decisions[1]["player"],
            "black",
        )

    def test_response_without_double_is_rejected(self):
        events = [
            event(
                1,
                "double_response",
                state(
                    phase="rolling",
                    cube=2,
                    cube_owner="black",
                ),
                player_color="black",
            )
        ]

        with self.assertRaises(
            CubeDecisionStreamError
        ):
            extract_cube_decisions(
                game_with_events(events)
            )

    def test_opening_roll_does_not_create_no_double(self):
        events = [
            event(
                1,
                "roll",
                state(
                    phase="opening_roll",
                    turn="black",
                ),
                player_color="white",
            ),
            event(
                2,
                "roll",
                state(
                    phase="opening_result",
                    turn="white",
                ),
                player_color="black",
            ),
        ]

        decisions = extract_cube_decisions(
            game_with_events(events)
        )

        self.assertEqual(decisions, [])
