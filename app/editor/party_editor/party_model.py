from PyQt5.QtCore import Qt

from app.data.database.database import DB
from app.editor.edit_history import HISTORY
from app.data.database.database_types import DatabaseType as DType
from app.editor import reference_dialogs

from app.editor.custom_widgets import PartyBox
from app.editor.base_database_gui import DragDropCollectionModel

class PartyModel(DragDropCollectionModel):
    def data(self, index, role):
        if not index.isValid():
            return None
        if role == Qt.DisplayRole:
            party = self._data[index.row()]
            text = party.nid + ": " + party.name
            return text
        return None

    def create_new(self):
        new_party = DB.parties.create_new(DB)
        return new_party

    def delete(self, idx):
        obj = self._data[idx]
        with HISTORY.change_set('Delete %s' % obj.nid):
            if reference_dialogs.check_delete(DType.PARTIES, obj.nid, 'Party', self.window,
                                              lambda: PartyBox(self.window, exclude=obj)):
                super().delete(idx)

    def on_nid_changed(self, old_nid, new_nid):
        HISTORY.rewrite(DType.PARTIES, old_nid, new_nid)
