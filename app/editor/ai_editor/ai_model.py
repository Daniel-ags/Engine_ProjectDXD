from PyQt5.QtCore import Qt

from app.data.database.database import DB
from app.data.database import references
from app.data.database.database_types import DatabaseType as DType
from app.editor import reference_dialogs

from app.editor.custom_widgets import AIBox
from app.editor.base_database_gui import DragDropCollectionModel

class AIModel(DragDropCollectionModel):
    def data(self, index, role):
        if not index.isValid():
            return None
        if role == Qt.DisplayRole:
            ai = self._data[index.row()]
            text = ai.nid
            return text
        return None

    def delete(self, idx):
        obj = self._data[idx]
        if reference_dialogs.check_delete(DB, DType.AI, obj.nid, 'AI', self.window,
                                          lambda: AIBox(self.window, exclude=obj)):
            super().delete(idx)

    def on_nid_changed(self, old_nid, new_nid):
        references.rewrite(DB, DType.AI, old_nid, new_nid)

    def create_new(self):
        new_ai = self._data.create_new(DB)
        return new_ai
