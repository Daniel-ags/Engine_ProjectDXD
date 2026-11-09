from __future__ import annotations

from typing import Optional, Tuple

class MovementComponent:
    grid_move = True
    
    def __init__(self, unit, follow=True, muted=False):
        self.active = True
        self._unit = unit
        self.follow: bool = follow
        self.muted: bool = muted

        self._last_update = 0

    @property
    def unit(self):
        return self._unit  

    def reset_position(self):
        # Used to reset the internal movement component position
        # Called when the free roam state begins
        pass

    def start(self):
        raise NotImplementedError

    def update(self, current_time: int) -> bool:
        raise NotImplementedError
    
    def finish(self, surprise=False):
        raise NotImplementedError

    def get_end_goal(self) -> Tuple[int, int]:
        """
        # Returns what the final goal of this
        # movement is as a position
        """
        return None

    def get_camera_position(self) -> Tuple[float, float]:
        return None

    def get_paced_camera_position(self) -> Optional[Tuple[float, float]]:
        """
        # Where the camera keeps pace with, pixel for pixel, every frame,
        # or None when it eases over to get_camera_position instead
        """
        return None

    def should_camera_center(self) -> bool:
        return self.follow
