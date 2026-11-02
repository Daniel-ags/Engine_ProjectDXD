from app.editor.edit_history import HISTORY
from app.extensions.list_dialogs import MultiAttrListDialog
from app.utilities.data import Data


class RecordedListDialog(MultiAttrListDialog):
    """A list dialog over a catalog of the database, such as the tags. Each edit
    is an undo step of its own, announced so the open editor windows show it."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.bind_records()
        self.model.dataChanged.connect(self.on_edited)
        self.model.layoutChanged.connect(self.on_edited)

    def recorded(self) -> Data:
        """The catalog the dialog's edits change"""
        return self._data

    def bind_records(self):
        """Commits what changed, then watches every record, a new one too"""
        HISTORY.bind_all(self.recorded(), self.recorded(), self)

    def on_edited(self, *args):
        self.bind_records()

    def done(self, result):
        HISTORY.unbind(self)
        super().done(result)
