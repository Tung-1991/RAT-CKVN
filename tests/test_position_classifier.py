# -*- coding: utf-8 -*-

import unittest
from types import SimpleNamespace

from core.position_classifier import (
    is_bot_position,
    is_grid_position,
    is_hedge_position,
    is_manual_position,
)


class PositionClassifierTests(unittest.TestCase):
    def setUp(self):
        self.magics = {
            "bot_magic": 11,
            "manual_magic": 22,
            "grid_magic": 33,
            "hedge_magic": 44,
        }

    def test_classifies_by_magic(self):
        self.assertTrue(is_bot_position(SimpleNamespace(magic=11, comment=""), self.magics))
        self.assertTrue(is_manual_position(SimpleNamespace(magic=22, comment=""), self.magics))
        self.assertTrue(is_grid_position(SimpleNamespace(magic=33, comment=""), self.magics))
        self.assertTrue(is_hedge_position(SimpleNamespace(magic=44, comment=""), self.magics))

    def test_grid_comment_overrides_bot_magic(self):
        pos = SimpleNamespace(magic=11, comment="[GRID]_CHILD|GRID_X|L:BUY_1")
        self.assertTrue(is_grid_position(pos, self.magics))
        self.assertFalse(is_bot_position(pos, self.magics))

    def test_grid_comment_overrides_manual_magic(self):
        pos = SimpleNamespace(magic=22, comment="[GRID]_CHILD|GRID_X|L:SELL_1")
        self.assertTrue(is_grid_position(pos, self.magics))
        self.assertFalse(is_manual_position(pos, self.magics))

    def test_grid_safe_comment_prefix(self):
        pos = SimpleNamespace(magic=0, comment="GRID_SELL_6")
        self.assertTrue(is_grid_position(pos, self.magics))

    def test_hedge_comment_overrides_bot_and_manual_magic(self):
        bot_pos = SimpleNamespace(magic=11, comment="HEDGE_BUY")
        manual_pos = SimpleNamespace(magic=22, comment="[HEDGE] SELL")
        self.assertTrue(is_hedge_position(bot_pos, self.magics))
        self.assertTrue(is_hedge_position(manual_pos, self.magics))
        self.assertFalse(is_bot_position(bot_pos, self.magics))
        self.assertFalse(is_manual_position(manual_pos, self.magics))


if __name__ == "__main__":
    unittest.main()
