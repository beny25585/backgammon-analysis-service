from unittest.mock import patch
from django.test import SimpleTestCase, override_settings
from rest_framework.test import APIClient

from analysis.api.bot import choose_board
from analysis.tests.test_game_state_converter import starting_state


def position(dice=(3, 1), color='white'):
    state = starting_state()
    roll = list(dice) if dice[0] != dice[1] else [dice[0]] * 4
    state.update(turn=color, phase='moving', dice=list(dice), remaining=roll)
    return state


class LiveBotTests(SimpleTestCase):
    def test_all_opening_rolls_both_colors_return_upstream_legal_boards(self):
        from bgsage import possible_moves
        from analysis.converters.game_state import game_state_to_open_sage_board
        for color in ('white', 'black'):
            for a in range(1, 7):
                for b in range(1, a + 1):
                    state = position((a, b), color)
                    board = game_state_to_open_sage_board(state, player_on_roll=color)
                    result = choose_board(state, 'hard')
                    self.assertIn(result['board'], possible_moves(board, a, b))

    def test_difficulty_still_uses_upstream_moves(self):
        from bgsage import possible_moves, STARTING_BOARD
        for difficulty in ('easy', 'medium', 'hard'):
            self.assertIn(choose_board(position(), difficulty)['board'], possible_moves(STARTING_BOARD, 3, 1))

    @override_settings(ANALYSIS_API_TOKEN='test-only-token')
    def test_internal_auth_and_input_validation(self):
        client = APIClient()
        url = '/api/v1/internal/bot/move/'
        self.assertIn(client.post(url, {}, format='json').status_code, (401, 403))
        client.credentials(HTTP_AUTHORIZATION='Bearer test-only-token')
        self.assertEqual(client.post(url, {'state': {}, 'difficulty': 'hard'}, format='json').status_code, 400)
        self.assertEqual(client.post(url, {'state': position(), 'difficulty': 'expert'}, format='json').status_code, 400)
        self.assertEqual(client.post(url, {'state': position(), 'difficulty': 'hard'}, format='json').status_code, 200)
        with patch('analysis.api.bot.choose_board', side_effect=RuntimeError('private internals')):
            response = client.post(url, {'state': position(), 'difficulty': 'hard'}, format='json')
            self.assertEqual(response.status_code, 503)
            self.assertNotIn('private internals', str(response.data))

    def test_partial_roll_rejected(self):
        state = position()
        state['remaining'] = [1]
        with self.assertRaises(ValueError):
            choose_board(state, 'hard')

    @override_settings(ANALYSIS_API_TOKEN='test-only-token')
    def test_doubles_http_contract(self):
        from bgsage import possible_moves
        from analysis.converters.game_state import game_state_to_open_sage_board
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION='Bearer test-only-token')
        url = '/api/v1/internal/bot/move/'
        for die in range(1, 7):
            for color in ('white', 'black'):
                with self.subTest(die=die, color=color):
                    state = position((die, die), color)
                    board = game_state_to_open_sage_board(state, player_on_roll=color)
                    for dice in ([die, die], [die] * 4):
                        state['dice'] = dice
                        response = client.post(url, {'state': state, 'difficulty': 'hard'}, format='json')
                        self.assertEqual(response.status_code, 200)
                        self.assertIn(response.data['board'], possible_moves(board, die, die))
                    state['remaining'] = [die] * 3
                    self.assertEqual(client.post(url, {'state': state, 'difficulty': 'hard'},
                        format='json').status_code, 400)
