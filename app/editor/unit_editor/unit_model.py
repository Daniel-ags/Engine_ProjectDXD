from PyQt5.QtGui import QPixmap, QIcon
from PyQt5.QtCore import Qt

from app.data.resources.resources import RESOURCES
from app.data.database.database import DB

from app.editor.base_database_gui import DragDropCollectionModel
from app.editor.portrait_editor import portrait_model
import app.editor.utilities as editor_utilities

class UnitModel(DragDropCollectionModel):
    def data(self, index, role):
        if not index.isValid():
            return None
        if role == Qt.DisplayRole:
            unit = self._data[index.row()]
            if not unit:
                return "None"
            text = unit.nid
            return text
        elif role == Qt.DecorationRole:
            unit = self._data[index.row()]
            if not unit:
                return None
            # Get chibi image
            pixmap = portrait_model.get_chibi(unit.portrait_nid)
            if pixmap:
                return QIcon(pixmap)
            else:
                return None
        return None

    def create_new(self):
        new_unit = self._data.create_new(DB)
        return new_unit
