from app.data.database.database import DB
from app.data.database.database_types import DatabaseType as DType

from app.editor import reference_dialogs
from app.editor.custom_widgets import ObjBox
from app.editor.edit_history import HISTORY
from app.editor.recorded_list_dialog import RecordedListDialog
from app.extensions.list_models import MultiAttrListModel
from app.utilities.data import Data

class TagMultiModel(MultiAttrListModel):
    def delete(self, idx):
        element = self._data[idx]
        others = Data([tag for tag in DB.tags if tag is not element])
        with HISTORY.change_set('Delete %s' % element.nid):
            if reference_dialogs.check_delete(DType.TAGS, element.nid, 'Tag', self.window,
                                              lambda: ObjBox("Tag", reference_dialogs.NidListModel, lambda: others, self.window)):
                super().delete(idx)

    def create_new(self):
        return self._data.add_new_default(DB)

    def on_attr_changed(self, data, attr, old_value, new_value):
        if attr == 'nid':
            self._data.update_nid(data, new_value)
            HISTORY.rewrite(DType.TAGS, old_value, new_value)

class TagDialog(RecordedListDialog):
    locked_vars = {'Lord', 'Boss', 'Required', 'Mounted', 'Flying', 'Armor', 'Dragon', 'AutoPromote',
                   'NoAutoPromote', 'Convoy', 'AdjConvoy', 'Tile', 'Blacklist', 'Protect'}

    @classmethod
    def create(cls, parent=None):
        def deletion_func(model, index):
            return model._data[index.row()].nid not in cls.locked_vars

        dlg = cls(DB.tags, "Tag", ("nid",), TagMultiModel, (deletion_func, None, deletion_func), cls.locked_vars, parent)
        return dlg

# Testing
# Run "python -m app.editor.tag_widget"
if __name__ == '__main__':
    import sys
    from PyQt5.QtWidgets import QApplication
    app = QApplication(sys.argv)
    from app.data.serialization.versions import CURRENT_SERIALIZATION_VERSION
    DB.load('default.ltproj', CURRENT_SERIALIZATION_VERSION)
    window = TagDialog.create()
    window.show()
    app.exec_()
