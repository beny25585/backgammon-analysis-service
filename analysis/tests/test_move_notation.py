from django.test import SimpleTestCase
from analysis.engines.open_sage import checker_move_notation


class MoveNotationTests(SimpleTestCase):
    def test_bar_hit_and_bearoff(self):
        before = [0] * 26
        before[25] = 1
        before[20] = -1
        after = list(before)
        after[25] = 0
        after[20] = 0
        after[19] = 1
        after[0] = 1
        self.assertEqual(checker_move_notation(before, after, [5, 1]), 'bar/20* 20/19')
        before = [0] * 26
        before[6] = 2
        after = [0] * 26
        self.assertEqual(checker_move_notation(before, after, [6, 6]), '6/off(2)')

    def test_ordinary_play_and_unchanged_board(self):
        from bgsage import STARTING_BOARD
        before = list(STARTING_BOARD)
        after = list(before)
        after[24] -= 1
        after[18] += 1
        after[8] -= 1
        after[7] += 1
        self.assertEqual(checker_move_notation(before, after, [6, 1]), '24/18 8/7')
        self.assertEqual(checker_move_notation(before, None, [6, 1]), '')
