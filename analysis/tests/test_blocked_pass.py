from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace

from django.test import SimpleTestCase

from analysis.api.match_record import source_record
from analysis.services.decision_stream import extract_checker_decisions, extract_cube_decisions
from analysis.services.luck_stream import extract_luck_rolls


def event(sequence, kind, color, **state):
    return {
        'sequence': sequence, 'event_type': kind, 'player_color': color,
        'payload': {
            'turn': color, 'phase': 'moving', 'dice': [2, 1],
            'remaining': [2, 1], 'cube': 1, 'cubeOwner': 'center', **state,
        },
    }


class UnrolledBlockedPassAnalysisTests(SimpleTestCase):
    def test_pass_creates_no_checker_cube_or_luck_decision(self):
        for color in ('white', 'black'):
            with self.subTest(color=color):
                events = [event(
                    1, 'blocked_pass', color,
                    turn='black' if color == 'white' else 'white',
                    phase='rolling', dice=[], remaining=[],
                )]
                game = SimpleNamespace(input_events=events)
                self.assertEqual(extract_checker_decisions(game), [])
                self.assertEqual(extract_cube_decisions(game), [])
                self.assertEqual(extract_luck_rolls(game), [])

    def test_pass_separates_completed_turns_without_reusing_old_dice(self):
        events = [
            event(1, 'roll', 'black'),
            event(2, 'move', 'black', remaining=[], lastMove=[{'from': 18, 'to': 20}]),
            event(3, 'blocked_pass', 'white', turn='black', phase='rolling', dice=[], remaining=[]),
            event(4, 'roll', 'black', dice=[6, 3], remaining=[6, 3]),
            event(5, 'move', 'black', dice=[6, 3], remaining=[], lastMove=[{'from': 0, 'to': 6}]),
            event(6, 'end_turn', 'black', turn='white', phase='rolling', dice=[], remaining=[]),
        ]
        game = SimpleNamespace(input_events=events)
        original = deepcopy(events)
        decisions = extract_checker_decisions(game)
        self.assertEqual([item['start_sequence'] for item in decisions], [1, 4])
        self.assertEqual([item['dice'] for item in decisions], [[2, 1], [6, 3]])
        self.assertEqual([item['source_event_sequence'] for item in extract_luck_rolls(game)], [1, 4])
        self.assertEqual(events, original)

    def test_source_record_preserves_the_unrolled_event(self):
        source_event = event(7, 'blocked_pass', 'white', turn='black', phase='rolling', dice=[], remaining=[])
        match = SimpleNamespace(
            id='analysis-one', source_match_id='match-one', source_room_id=None,
            created_at=datetime(2026, 10, 29, tzinfo=timezone.utc),
            input_payload={
                'games': [{'game_id': 'game-one', 'game_number': 1, 'events': [source_event]}],
            },
        )
        record = source_record(match)
        exported = record['games'][0]['events'][0]
        self.assertEqual(exported['event_type'], 'blocked_pass')
        self.assertEqual(exported['player_color'], 'white')
        self.assertEqual(exported['payload']['dice'], [])
        self.assertEqual(exported['payload']['turn'], 'black')
