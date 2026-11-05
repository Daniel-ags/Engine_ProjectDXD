from PyQt5.QtCore import Qt

from app.utilities.data import Data
from app.data.database.database import DB
from app.editor.edit_history import HISTORY
from app.data.database.database_types import DatabaseType as DType
from app.editor import reference_dialogs

from app.editor.custom_widgets import TeamBox
from app.editor.base_database_gui import DragDropCollectionModel

class TeamModel(DragDropCollectionModel):
    def data(self, index, role):
        if not index.isValid():
            return None
        if role == Qt.DisplayRole:
            team = self._data[index.row()]
            text = team.nid
            return text
        return None

    def create_new(self):
        new_team = DB.teams.create_new(DB)
        return new_team

    def delete(self, idx):
        obj = self._data[idx]
        with HISTORY.change_set('Delete %s' % obj.nid):
            if reference_dialogs.check_delete(DType.TEAMS, obj.nid, 'Team', self.window,
                                              lambda: TeamBox(self.window, exclude=obj)):
                super().delete(idx)

    def on_nid_changed(self, old_nid, new_nid):
        HISTORY.rewrite(DType.TEAMS, old_nid, new_nid)
