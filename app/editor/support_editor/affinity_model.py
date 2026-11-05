from PyQt5.QtGui import QPixmap, QIcon
from PyQt5.QtCore import Qt

from app.utilities.data import Data
from app.data.resources.resources import RESOURCES
from app.data.database.database import DB
from app.editor.edit_history import HISTORY
from app.data.database.database_types import DatabaseType as DType
from app.editor import reference_dialogs
from app.data.database import supports

from app.editor.custom_widgets import AffinityBox
from app.editor.base_database_gui import DragDropCollectionModel

from app.utilities import str_utils
import app.editor.utilities as editor_utilities

def get_pixmap(affinity):
    x, y = affinity.icon_index
    res = RESOURCES.icons16.get(affinity.icon_nid)
    if not res:
        return None
    if not res.pixmap:
        res.pixmap = QPixmap(res.full_path)
    pixmap = res.pixmap.copy(x*16, y*16, 16, 16)
    pixmap = QPixmap.fromImage(editor_utilities.convert_colorkey(pixmap.toImage()))
    return pixmap

class AffinityModel(DragDropCollectionModel):
    def data(self, index, role):
        if not index.isValid():
            return None
        if role == Qt.DisplayRole:
            affinity = self._data[index.row()]
            text = affinity.nid
            return text
        elif role == Qt.DecorationRole:
            affinity = self._data[index.row()]
            pixmap = get_pixmap(affinity)
            if pixmap:
                return QIcon(pixmap)
        return None

    def delete(self, idx):
        obj = self._data[idx]
        with HISTORY.change_set('Delete %s' % obj.nid):
            if reference_dialogs.check_delete(DType.AFFINITIES, obj.nid, 'Affinity', self.window,
                                              lambda: AffinityBox(self.window, exclude=obj)):
                super().delete(idx)

    def on_nid_changed(self, old_nid, new_nid):
        HISTORY.rewrite(DType.AFFINITIES, old_nid, new_nid)

    def create_new(self):
        nids = [d.nid for d in self._data]
        nid = name = str_utils.get_next_name("New Affinity", nids)
        new_affinity = supports.Affinity(
            nid, name, '', supports.SupportRankBonusList())
        DB.affinities.append(new_affinity)
        return new_affinity
