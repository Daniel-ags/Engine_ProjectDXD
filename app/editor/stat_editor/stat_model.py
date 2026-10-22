from PyQt5.QtCore import Qt

from app.data.database.database import DB
from app.data.database.database_types import DatabaseType as DType
from app.editor import reference_dialogs
from app.editor.edit_history import HISTORY
from app.editor.base_database_gui import DragDropCollectionModel

class StatTypeModel(DragDropCollectionModel):
    def data(self, index, role):
        if not index.isValid():
            return None
        if role == Qt.DisplayRole:
            stat_type = self._data[index.row()]
            text = stat_type.nid + ": " + stat_type.name
            return text
        return None

    def create_new(self):
        new_stat = self._data.create_new(DB)
        return new_stat

    def delete(self, idx):
        stat = self._data[idx]
        with HISTORY.change_set('Delete %s' % stat.nid):
            if reference_dialogs.check_delete(DType.STATS, stat.nid, 'Stat', self.window):
                super().delete(idx)
