from PyQt5.QtCore import Qt
from PyQt5.QtGui import QIcon, QPixmap

from app.utilities.data import Data
from app.data.resources.resources import RESOURCES
from app.data.database.database import DB

from app.editor.base_database_gui import DragDropCollectionModel

import app.editor.utilities as editor_utilities

def get_pixmap(skill):
    x, y = skill.icon_index
    res = RESOURCES.icons16.get(skill.icon_nid)
    if not res:
        return None
    if not res.pixmap:
        res.pixmap = QPixmap(res.full_path)
    return editor_utilities.cut_icon(res.pixmap, x*16, y*16, 16, 16)

class SkillModel(DragDropCollectionModel):
    def data(self, index, role):
        if not index.isValid():
            return None
        if role == Qt.DisplayRole:
            skill = self._data[index.row()]
            text = skill.nid
            return text
        elif role == Qt.DecorationRole:
            skill = self._data[index.row()]
            pix = get_pixmap(skill)
            if pix:
                pix = pix.scaled(32, 32)
                return QIcon(pix)
        return None

    def create_new(self):
        new_skill = DB.skills.create_new(DB)
        return new_skill
