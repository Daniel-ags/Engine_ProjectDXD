from __future__ import annotations
from typing import Tuple
from app.constants import WINHEIGHT, WINWIDTH
from app.utilities import utils
from app.utilities.typing import Point

_edge_margin = max(0, (WINWIDTH - 240) // 4)

horizontal_screen_positions = {'OffscreenLeft': -96,
                               'FarLeft': -24,
                               'LeftCorner': -16,
                               'Left': _edge_margin,
                               'MidLeft': _edge_margin + 24,
                               'CenterLeft': WINWIDTH // 2 - 96 - 12,
                               'CenterRight': WINWIDTH // 2 + 12,
                               'MidRight': WINWIDTH - 96 - _edge_margin - 24,
                               'LevelUpRight': WINWIDTH - 100,
                               'Right': WINWIDTH - 96 - _edge_margin,
                               'RightCorner': WINWIDTH - 80,
                               'FarRight': WINWIDTH - 72,
                               'OffscreenRight': WINWIDTH}

vertical_screen_positions = {'Top': 0,
                             'Middle': (WINHEIGHT - 80) // 2,
                             'Bottom': WINHEIGHT - 80}

def parse_screen_position(pos: Tuple | str, portrait_size: Tuple[int, int] = (96, 80)) -> Tuple[Point, bool]:
    """Returns a tuple of Point (on screen) and bool (indicating if the portrait should be mirrored)"""
    true_ver_screen_pos =  {'Top': 0,
                            'Middle': (WINHEIGHT - portrait_size[1]) // 2,
                            'Bottom':  WINHEIGHT - portrait_size[1]}

    # Only `LevelUpRight` is relative to the right, other horiz are relative to the left
    true_hor_screen_pos = horizontal_screen_positions | {'LevelUpRight': WINWIDTH - portrait_size[0] - 4}

    if not isinstance(pos, tuple):
        pos = (pos,)
    def resolve_pos(p: int | str, horiz=True) -> int:
        if isinstance(p, int):
            return p
        else:
            if horiz:
                return true_hor_screen_pos.get(p, 0)
            else:
                return true_ver_screen_pos.get(p, 0)
    position = (0, 0)

    if len(pos) == 2:
        position = resolve_pos(pos[0]), resolve_pos(pos[1], False)
    else:
        pos = pos[0]
        if isinstance(pos, int) or pos in true_hor_screen_pos:
            position = resolve_pos(pos), true_ver_screen_pos['Bottom']
        else:
            position = true_hor_screen_pos['Left'], resolve_pos(pos, False)
    return position, position[0] <= true_hor_screen_pos['CenterLeft']


def get_desired_center(x: int) -> int:
    return utils.clamp(x, 80, WINWIDTH - 88)
