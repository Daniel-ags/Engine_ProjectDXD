from PyQt5.QtGui import QPixmap, QIcon
from PyQt5.QtCore import Qt

from app.utilities.data import Data
from app.data.resources.resources import RESOURCES
from app.data.database.database import DB
from app.data.database import references
from app.data.database.database_types import DatabaseType as DType
from app.editor import reference_dialogs

from app.editor.custom_widgets import WeaponTypeBox
from app.editor.base_database_gui import DragDropCollectionModel

import app.editor.utilities as editor_utilities

def get_pixmap(weapon):
    x, y = weapon.icon_index
    res = RESOURCES.icons16.get(weapon.icon_nid)
    if not res:
        return None
    if not res.pixmap:
        res.pixmap = QPixmap(res.full_path)
    pixmap = res.pixmap.copy(x*16, y*16, 16, 16)
    pixmap = QPixmap.fromImage(editor_utilities.convert_colorkey(pixmap.toImage()))
    return pixmap

class WeaponModel(DragDropCollectionModel):
    def data(self, index, role):
        if not index.isValid():
            return None
        if role == Qt.DisplayRole:
            weapon = self._data[index.row()]
            text = weapon.nid + " : " + weapon.name
            return text
        elif role == Qt.DecorationRole:
            weapon = self._data[index.row()]
            pixmap = get_pixmap(weapon)
            if pixmap:
                return QIcon(pixmap)
        return None

    def delete(self, idx):
        obj = self._data[idx]
        if reference_dialogs.check_delete(DB, DType.WEAPONS, obj.nid, 'Weapon Type', self.window,
                                          lambda: WeaponTypeBox(self.window, exclude=obj)):
            super().delete(idx)

    def on_nid_changed(self, old_nid, new_nid):
        references.rewrite(DB, DType.WEAPONS, old_nid, new_nid)

    def create_new(self):
        new_weapon = DB.weapons.create_new(DB)
        return new_weapon
