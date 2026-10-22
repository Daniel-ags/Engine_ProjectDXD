from PyQt5.QtGui import QPixmap, QIcon
from PyQt5.QtCore import Qt

from app.data.resources.resources import RESOURCES

from app.utilities.data import Data
from app.data.database.database import DB
from app.editor.edit_history import HISTORY
from app.data.database.database_types import DatabaseType as DType
from app.editor import reference_dialogs

from app.editor.custom_widgets import FactionBox
from app.editor.base_database_gui import DragDropCollectionModel
import app.editor.utilities as editor_utilities
from app.utilities import str_utils

from app.data.database import factions

def get_pixmap(faction):
    x, y = faction.icon_index
    res = RESOURCES.icons32.get(faction.icon_nid)
    if not res:
        return None
    if not res.pixmap:
        res.pixmap = QPixmap(res.full_path)
    pixmap = res.pixmap.copy(x*32, y*32, 32, 32)
    pixmap = QPixmap.fromImage(editor_utilities.convert_colorkey(pixmap.toImage()))
    return pixmap

class FactionModel(DragDropCollectionModel):
    def data(self, index, role):
        if not index.isValid():
            return None
        if role == Qt.DisplayRole:
            faction = self._data[index.row()]
            text = faction.nid
            return text
        elif role == Qt.DecorationRole:
            faction = self._data[index.row()]
            pixmap = get_pixmap(faction)
            if pixmap:
                return QIcon(pixmap)
        return None

    def create_new(self):
        new_faction = DB.factions.create_new(DB)
        return new_faction

    def delete(self, idx):
        obj = self._data[idx]
        with HISTORY.change_set('Delete %s' % obj.nid):
            if reference_dialogs.check_delete(DType.FACTIONS, obj.nid, 'Faction', self.window,
                                              lambda: FactionBox(self.window, exclude=obj)):
                super().delete(idx)

    def on_nid_changed(self, old_nid, new_nid):
        HISTORY.rewrite(DType.FACTIONS, old_nid, new_nid)
