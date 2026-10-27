from typing import Callable

from PyQt5.QtWidgets import QPushButton
from PyQt5.QtCore import QSize
from app.data.resources.resources import RESOURCES

# Custom Widgets
from app.utilities.data import Data
from app.data.database.database import DB

from app.extensions.custom_gui import PropertyBox, ComboBox

class CustomQtRoles():
    # PyQt uses ints 0-14 for its roles.
    # Therefore, for custom roles, we must use 15+
    FilterRole = 15
    UnderlyingDataRole = 16

def without(data: Data, exclude) -> Data:
    return Data([d for d in data if d is not exclude]) if exclude else data

class ObjBox(PropertyBox[ComboBox]):
    """A choice of one record. records gives the records to choose from, and is
    asked again on each refresh."""
    def __init__(self, title, model, records: Callable[[], Data], parent=None, button=False):
        super().__init__(title, ComboBox, parent)
        self.records = records
        self.model = model(records(), parent)
        self.edit.setModel(self.model)
        # The records can change under the box before it refreshes -- a deletion
        # moves every row below up one -- so its current text may already name
        # another record. Remember what it chose instead
        self.choice = self.edit.currentText()
        self.edit.currentIndexChanged.connect(self.remember_choice)
        if button:
            b = QPushButton('...')
            b.setMaximumWidth(40)
            self.add_button(b)

    def setValue(self, val):
        self.edit.setValue(val)

    def remember_choice(self, index):
        self.choice = self.edit.currentText()

    def refresh(self):
        """Lists the records as they are now, keeping the choice shown. Writes nothing:
        the form showing the box sets the record's own choice afterwards. A choice
        no longer listed shows blank but is still remembered, so an undo that brings
        the record back shows it again."""
        self.edit.blockSignals(True)
        self.model.beginResetModel()
        self.model._data = self.records()
        self.model.endResetModel()
        self.edit.setCurrentIndex(self.edit.findText(self.choice))
        self.edit.blockSignals(False)
class UnitBox(ObjBox):
    def __init__(self, parent=None, button=False, exclude=None, title="Unit"):
        from app.editor.unit_editor.unit_model import UnitModel
        super().__init__(title, UnitModel, lambda: without(DB.units, exclude), parent, button)
        self.edit.setIconSize(QSize(32, 32))
        self.edit.view().setUniformItemSizes(True)

class ClassBox(ObjBox):
    def __init__(self, parent=None, button=False, exclude=None):
        from app.editor.class_editor.class_model import ClassModel
        super().__init__("Class", ClassModel, lambda: without(DB.classes, exclude), parent, button)
        self.edit.setIconSize(QSize(32, 32))
        self.edit.view().setUniformItemSizes(True)

class TeamBox(ObjBox):
    def __init__(self, parent=None, button=False, exclude=None):
        from app.editor.team_editor.team_model import TeamModel
        super().__init__("Team", TeamModel, lambda: without(DB.teams, exclude), parent, button)

class FactionBox(ObjBox):
    def __init__(self, parent=None, button=False, exclude=None):
        from app.editor.faction_editor.faction_model import FactionModel
        super().__init__("Faction", FactionModel, lambda: without(DB.factions, exclude), parent, button)

class ItemBox(ObjBox):
    def __init__(self, parent=None, button=False, exclude=None):
        from app.editor.item_editor.item_model import ItemModel
        super().__init__("Item", ItemModel, lambda: without(DB.items, exclude), parent, button)

class SkillBox(ObjBox):
    def __init__(self, parent=None, button=False, exclude=None):
        from app.editor.skill_editor.skill_model import SkillModel
        super().__init__("Skill", SkillModel, lambda: without(DB.skills, exclude), parent, button)

class AIBox(ObjBox):
    def __init__(self, parent=None, button=False, exclude=None):
        from app.editor.ai_editor.ai_model import AIModel
        super().__init__("Normal AI", AIModel,
                         lambda: Data([d for d in DB.ai if not d.roam_ai and d is not exclude]), parent, button)

class RoamAIBox(ObjBox):
    def __init__(self, parent=None, button=False, exclude=None):
        from app.editor.ai_editor.ai_model import AIModel
        super().__init__("Roam AI", AIModel,
                         lambda: Data([d for d in DB.ai if (d.roam_ai or d.nid == 'None') and d is not exclude]),
                         parent, button)

class WeaponTypeBox(ObjBox):
    def __init__(self, parent=None, button=False, exclude=None):
        from app.editor.weapon_editor.weapon_model import WeaponModel
        super().__init__("Weapon Type", WeaponModel, lambda: without(DB.weapons, exclude), parent, button)
        self.edit.setIconSize(QSize(16, 16))
        self.edit.view().setUniformItemSizes(True)

class PartyBox(ObjBox):
    def __init__(self, parent=None, button=False, exclude=None):
        from app.editor.party_editor.party_model import PartyModel
        super().__init__("Party", PartyModel, lambda: without(DB.parties, exclude), parent, button)

class AffinityBox(ObjBox):
    def __init__(self, parent=None, button=False, exclude=None):
        from app.editor.support_editor.affinity_model import AffinityModel
        super().__init__("Affinity Type", AffinityModel, lambda: without(DB.affinities, exclude), parent, button)

class MovementCostBox(ObjBox):
    def __init__(self, parent=None, button=False):
        from app.editor.mcost_dialog import MovementCostModel
        super().__init__("Movement Cost", MovementCostModel, lambda: DB.mcost, parent, button)

class MovementClassBox(ObjBox):
    def __init__(self, parent=None, button=False, title="Movement Class"):
        from app.editor.mcost_dialog import MovementClassModel
        super().__init__(title, MovementClassModel, lambda: DB.mcost, parent, button)

class EventBox(ObjBox):
    def __init__(self, parent=None, button=False, exclude=None):
        from app.editor.event_editor.event_model import EventModel
        super().__init__("Event", EventModel, lambda: without(DB.events, exclude), parent, button)

class TerrainBox(ObjBox):
    def __init__(self, parent=None, button=False, exclude=None):
        from app.editor.terrain_editor.terrain_model import TerrainModel
        super().__init__("Terrain Type", TerrainModel, lambda: without(DB.terrain, exclude), parent, button)

    def setValue(self, nid):
        terrain = DB.terrain.get(nid)
        if terrain:
            self.edit.setValue(terrain.nid + " : " + terrain.name)

class TilemapBox(ObjBox):
    def __init__(self, parent=None, button=False):
        from app.editor.tile_editor.tile_model import TileMapModel
        super().__init__("Tilemap", TileMapModel, lambda: RESOURCES.tilemaps, parent, button)

class PaletteBox(ObjBox):
    def __init__(self, parent=None, button=False, exclude=None):
        from app.editor.combat_animation_editor.palette_model import PaletteModel
        super().__init__("Palette", PaletteModel, lambda: without(RESOURCES.combat_palettes, exclude), parent, button)
