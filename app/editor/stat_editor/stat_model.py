from PyQt5.QtCore import Qt

from app.data.database.database import DB
from app.data.database.database_types import DatabaseType as DType
from app.editor import reference_dialogs
from app.editor.edit_history import HISTORY
from app.editor.base_database_gui import DragDropCollectionModel

def stat_table_holders():
    """Every unit and class, each of which has a table of values per stat"""
    return [(unit, DB.units) for unit in DB.units] + [(klass, DB.classes) for klass in DB.classes]

def fill_stat_tables():
    """Gives every unit and class an entry for every stat in each of its stat tables,
    and drops the entries for stats that are gone, recorded"""
    all_stats = set([stat.nid for stat in DB.stats])
    with HISTORY.modifying(stat_table_holders()):
        for record in list(DB.units) + list(DB.classes):
            for row in record.get_stat_lists():
                for stat in all_stats.difference(row.keys()):
                    row[stat] = 0
                for stat in set(row.keys()).difference(all_stats):
                    row.pop(stat)


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
        # The catalog gives every unit and class an entry for the new stat: recorded
        # with the stat, as one undo step
        with HISTORY.modifying(stat_table_holders()):
            new_stat = self._data.create_new(DB)
        return new_stat

    def duplicate(self, idx):
        with HISTORY.change_set('Duplicate stat'):
            new_index = super().duplicate(idx)
            fill_stat_tables()
        return new_index

    def delete(self, idx):
        stat = self._data[idx]
        with HISTORY.change_set('Delete %s' % stat.nid):
            if reference_dialogs.check_delete(DType.STATS, stat.nid, 'Stat', self.window):
                super().delete(idx)
