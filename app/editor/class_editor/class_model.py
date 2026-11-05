from PyQt5.QtGui import QIcon, QPixmap
from PyQt5.QtCore import Qt

from app.data.resources.resources import RESOURCES

from app.utilities.data import Data
from app.data.database.database import DB

from app.editor import timer

from app.editor.base_database_gui import DragDropCollectionModel
from app.editor.map_sprite_editor import map_sprite_model
from app.editor.combat_animation_editor import combat_animation_model

def get_combat_anim_icon(klass_obj):
    if not klass_obj.combat_anim_nid:
        return None
    return combat_animation_model.get_combat_anim_icon(klass_obj.combat_anim_nid)

class ClassModel(DragDropCollectionModel):
    display_team = 'player'

    def data(self, index, role):
        if not index.isValid():
            return None
        if role == Qt.DisplayRole:
            klass = self._data[index.row()]
            text = klass.nid
            return text
        elif role == Qt.DecorationRole:
            klass = self._data[index.row()]
            num = timer.get_timer().passive_counter.count
            if hasattr(self.window, 'view') and self.window.view:
                active = index == self.window.view.currentIndex()
            else:
                active = False
            pixmap = map_sprite_model.get_map_sprite_icon(klass.map_sprite_nid, num, active, self.display_team)
            if pixmap:
                return QIcon(pixmap)
            else:
                return None
        return None

    def create_new(self):
        new_class = DB.classes.create_new(DB)
        return new_class
