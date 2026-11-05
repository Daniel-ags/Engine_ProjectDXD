from app.utilities import str_utils
from app.utilities.data import Data
from app.data.database.database import DB
from app.data.database.database_types import DatabaseType as DType

from app.editor import reference_dialogs
from app.editor.custom_widgets import ObjBox
from app.editor.edit_history import HISTORY
from app.editor.recorded_list_dialog import RecordedListDialog
from app.extensions.list_models import MultiAttrListModel

from app.data.database.supports import SupportRank

class SupportRankMultiModel(MultiAttrListModel):
    def delete(self, idx):
        element = self._data[idx]
        others = Data([rank for rank in DB.support_ranks if rank is not element])
        with HISTORY.change_set('Delete %s' % element.nid):
            if reference_dialogs.check_delete(DType.SUPPORT_RANKS, element.nid, 'Support Rank', self.window,
                                              lambda: ObjBox("Support Rank", reference_dialogs.NidListModel, lambda: others, self.window)):
                super().delete(idx)

    def create_new(self):
        nids = DB.support_ranks.keys()
        nid = str_utils.get_next_name("Support Rank", nids)
        new_support_rank = SupportRank(nid)
        DB.support_ranks.append(new_support_rank)
        return new_support_rank

    def on_attr_changed(self, data, attr, old_value, new_value):
        if attr == 'nid':
            self._data.update_nid(data, new_value)
            HISTORY.rewrite(DType.SUPPORT_RANKS, old_value, new_value)

class SupportRankDialog(RecordedListDialog):
    @classmethod
    def create(cls):
        def deletion_func(model, index):
            return model.rowCount() > 1

        return cls(DB.support_ranks, "Support Rank",
                   ("nid",), SupportRankMultiModel, (deletion_func, None, None))
