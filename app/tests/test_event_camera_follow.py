import unittest
from types import SimpleNamespace
from typing import List, Optional, Tuple
from unittest.mock import MagicMock

from app.engine import action  # noqa: F401 -- avoids a circular import, see test_menu_options
from app.engine.camera import Camera
from app.engine.movement.movement_component import MovementComponent
from app.engine.movement.movement_system import MovementSystem
from app.engine.movement.unit_path_movement_component import UnitPathMovementComponent
from app.events import event_functions
from app.events.event import Event
from app.events.event_prefab import EventPrefab
from app.events.triggers import GenericTrigger
from app.tests.engine_harness import EngineTestCase

PIXEL = 1 / 16


class WalkRight(MovementComponent):
    '''Walks along a row 2 pixels a frame, as a unit does on the GBA, the way an event moves it'''

    def __init__(self, start: Tuple[int, int], end_x: int, center=False):
        super().__init__(unit=None, follow=True)
        self.x, self.y = float(start[0]), start[1]
        self.end_x = end_x
        self.center = center

    def update(self, current_time: int):
        self.x = min(self.x + 2 * PIXEL, self.end_x)
        if self.x >= self.end_x:
            self.active = False

    def get_camera_position(self):
        return (int(self.x), self.y)

    def get_paced_camera_position(self) -> Optional[Tuple[float, float]]:
        return (self.x, self.y)

    def should_camera_center(self) -> bool:
        return self.center


class EventCameraFollowTests(unittest.TestCase):
    '''
    As on the GBA, while the camera follows a unit moving in an event, it moves with the unit
    pixel for pixel, keeping it 3 tiles in from the left and right of the screen and 2 from the
    top and bottom, or in the middle with center
    '''

    def setUp(self):
        self.camera = Camera(SimpleNamespace(tilemap=SimpleNamespace(width=40, height=30)))
        self.movement = MovementSystem(cursor=None, camera=self.camera)

    def walk(self, entity: MovementComponent) -> List[Tuple[float, float]]:
        '''Where the entity and the camera are each frame until it stops'''
        self.movement.add(entity)
        seen = []
        while len(self.movement):
            self.movement.update()
            self.camera.update()
            seen.append((entity.x, self.camera.current_x))
        return seen

    def test_camera_waits_for_the_unit_to_near_the_edge_then_keeps_pace(self):
        seen = self.walk(WalkRight((5, 4), 20))
        for unit_x, camera_x in seen:
            self.assertEqual(max(0, unit_x - 11), camera_x)
        self.assertEqual(9, self.camera.current_x)
        self.assertTrue(self.camera.at_rest())

    def test_center_keeps_the_unit_in_the_middle(self):
        self.camera.force_center(10, 4)
        seen = self.walk(WalkRight((10, 4), 25, center=True))
        for unit_x, camera_x in seen:
            self.assertEqual(unit_x - 7, camera_x)

    def test_eases_over_to_a_unit_off_screen_before_keeping_pace(self):
        '''Rather than jumping to it'''
        seen = self.walk(WalkRight((30, 4), 38))
        camera_xs = [camera_x for _, camera_x in seen]
        # No faster than the camera's top speed, a tile a frame
        self.assertLessEqual(camera_xs[0], 1)
        self.assertGreater(len([x for x in camera_xs if x != camera_xs[-1]]), 10)
        self.assertEqual(sorted(camera_xs), camera_xs)
        # Up to the right of the map, 40 tiles wide
        caught_up = next(idx for idx, (unit_x, camera_x) in enumerate(seen) if camera_x == unit_x - 11)
        for unit_x, camera_x in seen[caught_up:]:
            self.assertEqual(min(25, unit_x - 11), camera_x)

    def test_a_second_move_eases_over_too(self):
        '''Having kept pace with one unit, the camera does not jump to the next'''
        self.walk(WalkRight((5, 4), 20))
        seen = self.walk(WalkRight((36, 20), 38))
        self.assertLess(seen[0][1], 10)


class UnitPathPacingTests(unittest.TestCase):
    def mover(self, event: bool, follow=True, center=False) -> UnitPathMovementComponent:
        unit = MagicMock(position=(6, 3))
        unit.sprite.offset = [4, 0]
        return UnitPathMovementComponent(unit, [(7, 3)], event=event, follow=follow, center=center)

    def test_an_event_move_is_paced_where_the_sprite_is(self):
        mover = self.mover(event=True)
        self.assertEqual((6.25, 3), mover.get_paced_camera_position())
        self.assertFalse(mover.should_camera_center())

    def test_center_is_kept(self):
        self.assertTrue(self.mover(event=True, center=True).should_camera_center())

    def test_only_while_followed_in_an_event(self):
        self.assertIsNone(self.mover(event=False).get_paced_camera_position())
        self.assertIsNone(self.mover(event=True, follow=False).get_paced_camera_position())


class MoveUnitCenterFlagTests(EngineTestCase):
    def setUp(self):
        super().setUp()
        self.harness = self.start_harness()
        self.game = self.harness.start_level('0')
        self.harness.run_until_state('free')
        self.event = Event(EventPrefab('test_move_unit'), GenericTrigger(), game=self.game)

    def moving_centers(self, flags: set) -> bool:
        event_functions.move_unit(self.event, 'Eirika', '6,5', flags=flags)
        mover, = self.game.movement.moving_entities
        self.assertTrue(mover.event)
        return mover.should_camera_center()

    def test_move_unit_does_not_center_by_default(self):
        self.assertFalse(self.moving_centers(set()))

    def test_center_flag_centers(self):
        self.assertTrue(self.moving_centers({'center'}))


if __name__ == '__main__':
    unittest.main()
