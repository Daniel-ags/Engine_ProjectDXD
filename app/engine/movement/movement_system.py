from __future__ import annotations

from typing import Optional, List, Tuple, TYPE_CHECKING

from app.engine import engine
from app.engine.movement import movement_funcs
from app.engine.movement.movement_component import MovementComponent
from app.engine.movement.unit_path_movement_component import UnitPathMovementComponent
from app.utilities import utils

if TYPE_CHECKING:
    from app.engine import camera, cursor

import logging

class MovementSystem:
    """
    Operates upon MovementComponents and handles moving the camera around
    """
    def __init__(self, cursor: Optional[cursor.BaseCursor], camera: Optional[camera.Camera]):
        self.cursor = cursor
        self.camera = camera

        self.moving_entities: List[MovementComponent] = []
        self.camera_follow: Tuple[int, int] = None  # What position to be over
        self.camera_center: bool = False  # Whether to center on the position
        # What the camera kept pace with last frame, pixel for pixel
        self.camera_paced_entity: Optional[MovementComponent] = None

    def __len__(self):
        return len(self.moving_entities)

    def add(self, mc: MovementComponent):
        self.moving_entities.append(mc)

    def check_if_occupied_in_future(self, pos: Tuple[int, int]):
        for movement_component in self.moving_entities:
            if movement_component.get_end_goal() == pos:
                return movement_component.unit
        return None

    def is_moving(self, unit) -> bool:
        for movement_component in self.moving_entities:
            if movement_component.unit == unit:
                return True
        return False

    def stop(self, unit):
        """
        # Stop all movement components associated with the given unit
        """
        for movement_component in self.moving_entities:
            if movement_component.unit == unit:
                movement_component.finish()    

    def begin_move(self, unit, path: List[Tuple[int, int]],
                   event=False, follow=True, speed=0, silent=False, center=False):
        """
        # Used for simple movement of a unit in the normal way
        """

        logging.info("Unit %s to begin moving", unit)
        speed = speed or movement_funcs.get_default_speed(unit)
        movement_component = \
            UnitPathMovementComponent(unit, path, event, follow, speed=speed, muted=silent, center=center)
        self.moving_entities.append(movement_component)

    def update(self):
        current_time = engine.get_time()
        old_follow = self.camera_follow
        old_paced_entity = self.camera_paced_entity
        paced_entity: Optional[MovementComponent] = None
        paced_position: Optional[Tuple[float, float]] = None

        # Update all remaining entities
        for entity in self.moving_entities[:]:
            entity.update(current_time)
            if entity.follow:
                self.camera_follow = entity.get_camera_position()
                self.camera_center = entity.should_camera_center()
                paced_entity = entity
                paced_position = entity.get_paced_camera_position()
            # Remove inactive entities
            if not entity.active:
                self.moving_entities.remove(entity)

        if not paced_position:
            paced_entity = None
        # The camera has caught up once it comes to rest following the same entity as last frame
        camera_caught_up = paced_entity is old_paced_entity and self.camera and self.camera.at_rest()
        self.camera_paced_entity = paced_entity if paced_entity and paced_entity.active else None

        # Update camera follow only if it's changed
        if self.camera_follow and old_follow != self.camera_follow:
            if self.cursor:
                self.cursor.set_pos(utils.round_pos(self.camera_follow))
            if self.camera and self.camera_center and not paced_position:
                self.camera.set_center(*self.camera_follow)
        if self.camera and paced_position:
            self.camera.keep_pace(*paced_position, self.camera_center, camera_caught_up)
