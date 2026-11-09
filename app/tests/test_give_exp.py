import unittest
from unittest.mock import MagicMock

from app.tests.engine_harness import EngineTestCase


class SilentGiveExpTests(EngineTestCase):
    project = 'default.ltproj'

    def give_exp(self, level: int, old_exp: int, exp: int, tags: set):
        from app.data.database.database import DB
        from app.events import event_functions
        harness = self.start_harness()
        harness.start_level('0')
        game = harness.game
        harness.run_until(lambda: game.get_unit('Eirika') is not None, 60, 'Eirika loaded')
        unit = game.get_unit('Eirika')
        self.assertEqual(20, DB.classes.get(unit.klass).max_level)
        unit.level = level
        unit.exp = old_exp
        unit._tags |= tags
        event = MagicMock()
        event._get_unit = lambda nid: unit
        event.game = game
        event_functions.give_exp(event, 'Eirika', exp, {'silent'})
        return unit

    def test_auto_promote_unit_at_max_level_stops_short_of_promotion(self):
        '''It levelled past its class's max level instead'''
        unit = self.give_exp(20, 50, 60, {'AutoPromote'})
        self.assertEqual((20, 99, 'Eirika_Lord'), (unit.level, unit.exp, unit.klass))

    def test_auto_promote_unit_below_max_level_levels_up(self):
        unit = self.give_exp(19, 50, 60, {'AutoPromote'})
        self.assertEqual((20, 10), (unit.level, unit.exp))

    def test_unit_at_max_level_gains_nothing(self):
        # Its exp gains stopped at 0 exp of its max level
        unit = self.give_exp(20, 0, 60, set())
        self.assertEqual((20, 0), (unit.level, unit.exp))


if __name__ == '__main__':
    unittest.main()
