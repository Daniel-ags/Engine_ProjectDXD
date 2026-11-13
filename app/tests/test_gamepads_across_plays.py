import unittest
from unittest.mock import patch

from app.tests.engine_harness import EngineTestCase
from app.engine import driver, engine
from app.engine.input_manager import get_input_manager
from app.engine.utils import garbage


class ClosedPad():
    """A pad closed by pygame.quit: reading it raises, like pygame-ce's"""
    def get_button(self, button):
        raise engine.pygame.error('Controller is not initialized')

    def get_axis(self, axis):
        raise engine.pygame.error('Controller is not initialized')


class GamepadsAcrossPlaysTests(EngineTestCase):
    """
    The editor runs every test play in the editor's process, so the input manager
    outlives each play. A pad from an earlier play is closed once that play
    quits pygame, so the next play must not read it, whether or not the pad is
    connected when that play starts
    """
    def setUp(self) -> None:
        super().setUp()
        self.input_manager = get_input_manager()
        old_pads = self.input_manager.controllers, self.input_manager.joysticks
        self.addCleanup(setattr, self.input_manager, 'controllers', old_pads[0])
        self.addCleanup(setattr, self.input_manager, 'joysticks', old_pads[1])

    def test_new_play_forgets_pads_from_the_last(self):
        self.input_manager.controllers, self.input_manager.joysticks = [ClosedPad()], []
        with patch.object(engine, 'get_gamepads', return_value=([], [])), \
                patch.object(engine, 'build_display', return_value=engine.DISPLAYSURF), \
                patch.object(garbage, 'settle'), \
                patch.dict(engine.constants, {'standalone': False}):
            driver.start('Test', from_editor=True)
        self.assertEqual(self.input_manager.controllers, [])
        self.input_manager.process_input([])  # Reads the pads, as every frame does


if __name__ == '__main__':
    unittest.main()
