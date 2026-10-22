from functools import lru_cache
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap, QIcon, QPainter, QColor

from typing import List

from app.data.database import references
from app.data.resources.resources import RESOURCES
from app.data.resources.resource_types import ResourceType as RType
from app.data.database.database import DB

from app.utilities import utils
from app.utilities.data import Data

from app.data.resources.combat_palettes import Palette
from app.editor import reference_dialogs
from app.extensions.custom_gui import DeletionTab
from app.editor.custom_widgets import PaletteBox
from app.editor.base_database_gui import DragDropCollectionModel
from app.utilities import str_utils

from app.utilities.typing import NID

@lru_cache(None)
def generate_palette_pixmap(palette_colors: tuple):
    painter = QPainter()
    main_pixmap = QPixmap(32, 32)
    main_pixmap.fill(QColor(0, 0, 0, 0))
    painter.begin(main_pixmap)
    palette_colors = sorted(palette_colors, key=lambda color: utils.rgb2hsv(*color[:3])[0])
    for idx, color in enumerate(palette_colors[:16]):
        left = idx % 4
        top = idx // 4
        painter.fillRect(left * 8, top * 8, 8, 8, QColor(*color[:3]))
    painter.end()
    return main_pixmap

def get_palette_pixmap(palette) -> QPixmap:
    colors = palette.colors.values()
    return generate_palette_pixmap(tuple(colors))

def resource_deletion_tabs(nid: NID) -> List[DeletionTab]:
    """What a deletion would affect beyond the database's own references to the palette"""
    affected_combat_anims = [anim for anim in RESOURCES.combat_anims if nid in [palette[1] for palette in anim.palettes]]
    affected_effect_anims = [anim for anim in RESOURCES.combat_effects if nid in [palette[1] for palette in anim.palettes]]
    deletion_tabs = []
    if affected_combat_anims:
        from app.editor.combat_animation_editor.combat_animation_model import CombatAnimModel
        model = CombatAnimModel
        msg = "Deleting Palette <b>%s</b> would affect these combat animations." % nid
        deletion_tabs.append(DeletionTab(affected_combat_anims, model, msg, "Combat Animations"))
    if affected_effect_anims:
        from app.editor.combat_animation_editor.combat_effect_model import CombatEffectModel
        model = CombatEffectModel
        msg = "Deleting Palette <b>%s</b> would affect these effect animations." % nid
        deletion_tabs.append(DeletionTab(affected_effect_anims, model, msg, "Effect Animations"))
    return deletion_tabs

def check_delete(nid: NID, window) -> bool:
    res = window.data.get(nid)
    return reference_dialogs.check_delete(DB, RType.COMBAT_PALETTES, nid, 'Palette', window,
                                          lambda: PaletteBox(window, exclude=res),
                                          extra_tabs=resource_deletion_tabs(nid),
                                          on_swap=lambda swap_nid: swap_in_resources(nid, swap_nid))

def on_nid_changed(old_nid, new_nid):
    references.rewrite(DB, RType.COMBAT_PALETTES, old_nid, new_nid)
    swap_in_resources(old_nid, new_nid)

def swap_in_resources(old_nid, new_nid):
    for combat_anim in RESOURCES.combat_anims:
        for idx, palette in enumerate(combat_anim.palettes):
            if old_nid == palette[1]:
                combat_anim.palettes[idx][1] = new_nid
    for effect_anim in RESOURCES.combat_effects:
        for idx, palette in enumerate(effect_anim.palettes):
            if old_nid == palette[1]:
                effect_anim.palettes[idx][1] = new_nid

class PaletteModel(DragDropCollectionModel):
    def data(self, index, role):
        if not index.isValid():
            return None
        if role == Qt.DisplayRole:
            if len(self._data) > index.row():
                palette = self._data[index.row()]
                text = palette.nid
                return text
        elif role == Qt.DecorationRole:
            if len(self._data) > index.row():
                palette = self._data[index.row()]
                pixmap = get_palette_pixmap(palette)
                if pixmap:
                    return QIcon(pixmap)
        return None

    def create_new(self):
        nids = RESOURCES.combat_palettes.keys()
        nid = str_utils.get_next_name('New Palette', nids)
        new_palette = Palette(nid)
        RESOURCES.combat_palettes.append(new_palette)
        return new_palette
