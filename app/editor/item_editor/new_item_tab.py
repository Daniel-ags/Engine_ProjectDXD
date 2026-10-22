from __future__ import annotations

import os
from typing import Optional

from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QFileDialog

import app.engine.item_component_access as ICA
from app.data.database import references
from app.data.database.database_types import DatabaseType as DType
from app.data.database.items import ItemCatalog, ItemPrefab
from app.editor import reference_dialogs, timer
from app.editor.data_editor import SingleDatabaseEditor
from app.editor.item_editor import item_import, item_model
from app.editor.component_editor_properties import NewComponentProperties, component_search_text
from app.editor.settings.main_settings_controller import MainSettingsController
from app.editor.new_editor_tab import NewEditorTab
from app.editor.custom_widgets import ItemBox

from app.utilities.typing import NID


class NewItemProperties(NewComponentProperties[ItemPrefab]):
    title = "Item"
    get_components = staticmethod(ICA.get_item_components)
    get_templates = staticmethod(ICA.get_templates)
    get_tags = staticmethod(ICA.get_item_tags)


class NewItemDatabase(NewEditorTab):
    catalog_type = ItemCatalog
    properties_type = NewItemProperties

    @classmethod
    def edit(cls, parent=None):
        timer.get_timer().stop_for_editor()  # Don't need these while running game
        window = SingleDatabaseEditor(NewItemDatabase, parent)
        window.exec_()
        timer.get_timer().start_for_editor()

    @property
    def data(self):
        return self._db.items

    def get_icon(self, item_nid) -> Optional[QIcon]:
        pix = item_model.get_pixmap(self.data.get(item_nid))
        if pix:
            return QIcon(pix.scaled(32, 32))
        return None

    def get_search_text(self, nid: NID) -> str:
        return component_search_text(self.data.get(nid))

    def _on_delete(self, nid: NID) -> bool:
        """
        Returns whether the user wants to proceed with deletion
        """
        return reference_dialogs.check_delete(self._db, DType.ITEMS, nid, 'Item',
                                              self, lambda: ItemBox(self, exclude=self.data.get(nid)))

    def _on_nid_changed(self, old_nid: NID, new_nid: NID) -> None:
        references.rewrite(self._db, DType.ITEMS, old_nid, new_nid)

    def import_xml(self):
        settings = MainSettingsController()
        starting_path = settings.get_last_open_path()
        fn, ok = QFileDialog.getOpenFileName(self, _("Import items from items.xml"), starting_path, "Items XML (items.xml);;All Files(*)")
        if ok and fn.endswith('items.xml'):
            parent_dir = os.path.split(fn)[0]
            settings.set_last_open_path(parent_dir)
            new_items = item_import.get_from_xml(parent_dir, fn)
            for item in new_items:
                self.data.append(item)
            self.reset()

    def import_csv(self):
        settings = MainSettingsController()
        starting_path = settings.get_last_open_path()
        fn, ok = QFileDialog.getOpenFileName(self, _("Import items from csv"), starting_path, "items csv (*.csv);;All Files(*)")
        if ok and fn:
            parent_dir = os.path.split(fn)[0]
            settings.set_last_open_path(parent_dir)
            item_import.update_db_from_csv(self._db, fn)
            self.reset()

# Testing
# Run "python -m app.editor.item_editor.new_item_tab" from main directory
if __name__ == '__main__':
    import sys
    from app.data.database.database import DB
    from PyQt5.QtWidgets import QApplication
    app = QApplication(sys.argv)
    from app.data.resources.resources import RESOURCES
    from app.data.serialization.versions import CURRENT_SERIALIZATION_VERSION
    DB.load('default.ltproj', CURRENT_SERIALIZATION_VERSION)
    RESOURCES.load('default.ltproj', CURRENT_SERIALIZATION_VERSION)
    window = NewItemDatabase(None, DB)
    window.show()
    app.exec_()
