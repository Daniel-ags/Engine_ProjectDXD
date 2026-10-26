from __future__ import annotations

import os
from typing import Optional

from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QApplication, QDialog, QFileDialog, QMessageBox

from app.editor.edit_history import HISTORY
from app.data.database.database import DB
from app.data.database.database_types import DatabaseType as DType
from app.data.database.units import UnitCatalog
from app.editor import reference_dialogs
from app.editor.data_editor import SingleDatabaseEditor
from app.editor.unit_editor import unit_import, new_unit_properties
from app.editor.portrait_editor import portrait_model
from app.editor.settings.main_settings_controller import MainSettingsController
from app.editor.new_editor_tab import NewEditorTab
from app.utilities.typing import NID


class NewUnitDatabase(NewEditorTab):
    catalog_type = UnitCatalog
    properties_type = new_unit_properties.NewUnitProperties
    allow_import_from_xml = True
    allow_import_from_csv = True
    allow_copy_and_paste = True

    @property
    def data(self):
        return self._db.units

    def get_icon(self, unit_nid: NID) -> Optional[QIcon]:
        unit = self.data.get(unit_nid)
        if not unit:
            return None
        pix = portrait_model.get_chibi(unit.portrait_nid)
        if pix:
            return QIcon(pix.scaled(32, 32))
        return None

    def get_search_text(self, nid: NID) -> str:
        return '%s\n%s' % (nid, self.data.get(nid).name)

    def create_new(self, nid):
        if self.data.get(nid):
            QMessageBox.warning(self, 'Warning', 'ID %s already in use' % nid)
            return False
        new_unit = self.catalog_type.datatype(nid, nid, '')
        new_unit.klass = self._db.classes[0].nid
        self.data.append(new_unit)
        return True

    def import_xml(self):
        settings = MainSettingsController()
        starting_path = settings.get_last_open_path()
        fn, ok = QFileDialog.getOpenFileName(self, _("Import Units from units.xml"), starting_path, "Units XML (units.xml);;All Files(*)")
        if ok and fn.endswith('units.xml'):
            parent_dir = os.path.split(fn)[0]
            settings.set_last_open_path(parent_dir)
            new_units = unit_import.get_from_xml(parent_dir, fn)
            for unit in new_units:
                self.data.append(unit)
            self.reset()

    def import_csv(self):
        settings = MainSettingsController()
        starting_path = settings.get_last_open_path()
        fn, ok = QFileDialog.getOpenFileName(self, _("Import Units from csv"), starting_path, "units csv (*.csv);;All Files(*)")
        if ok and fn:
            parent_dir = os.path.split(fn)[0]
            settings.set_last_open_path(parent_dir)
            unit_import.update_db_from_csv(self._db, fn)
            self.reset()

    def _on_nid_changed(self, old_nid: NID, new_nid: NID):
        HISTORY.rewrite(DType.UNITS, old_nid, new_nid)

    def _on_delete(self, nid: NID) -> bool:
        # Levels drop the unit rather than take another in its place
        fallback = next(unit.nid for unit in self.data if unit.nid != nid)
        return reference_dialogs.check_delete(DType.UNITS, nid, 'Unit', self, fallback=fallback)

    def on_tab_close(self):
        # Checking to see if any levels need to be changed
        for level in DB.levels:
            for unit in level.units.values():
                if unit.generic or unit.nid in DB.units:
                    pass
                else:  # Remove any unit that no longer exist
                    level.units.remove_key(unit.nid)
            # Now remove groups
            for unit_group in level.unit_groups:
                for unit_nid in unit_group.units:
                    if unit_nid not in level.units:
                        unit_group.remove(unit_nid)

def get(unit_nid: Optional[NID] = None, parent=None):
    """Opens the unit editor on unit_nid. Returns the unit it shows when closed with OK."""
    window = SingleDatabaseEditor(NewUnitDatabase, parent)
    if unit_nid in DB.units:
        window.tab.tree_list.select_item(unit_nid)
    result = window.exec_()
    selected_unit = window.tab.right_frame.current
    if result == QDialog.Accepted and selected_unit:
        return selected_unit, True
    return None, False

# Testing
# Run "python -m app.editor.unit_editor.new_unit_tab" from main directory
if __name__ == '__main__':
    import sys
    from app.data.database.database import DB
    from PyQt5.QtWidgets import QApplication
    app = QApplication(sys.argv)
    from app.data.resources.resources import RESOURCES
    from app.data.serialization.versions import CURRENT_SERIALIZATION_VERSION
    DB.load('default.ltproj', CURRENT_SERIALIZATION_VERSION)
    RESOURCES.load('default.ltproj', CURRENT_SERIALIZATION_VERSION)
    window = NewUnitDatabase(None, DB, RESOURCES)
    window.show()
    app.exec_()
