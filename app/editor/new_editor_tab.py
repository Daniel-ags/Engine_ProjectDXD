from __future__ import annotations

import json
import logging
from typing import Generic, List, Optional, Type, TypeVar

from PyQt5.QtGui import QIcon, QBrush
from PyQt5.QtWidgets import (QGridLayout, QHBoxLayout,
                             QMessageBox, QPushButton, QSplitter, QVBoxLayout,
                             QWidget, QApplication)

from app.data.database.database import DB, Database
from app.data.resources.resources import RESOURCES, Resources
from app.data.resources.base_catalog import ManifestCatalog
from app.data.category import Categories, CategorizedCatalog
from app.editor.custom_widgets import ObjBox
from app.editor.data_editor import SingleDatabaseEditor
from app.editor.edit_history import HISTORY
from app.editor.lib.components.nested_list import LTNestedList
from app.utilities import str_utils
from app.utilities.typing import NID

T = TypeVar('T', bound=CategorizedCatalog)

class NewEditorTab(QWidget, Generic[T]):
    """
    Used as a generic base class for NewXDatabases
    """
    # Make sure you define these
    catalog_type: Type[T] = None
    properties_type = None
    allow_rename = False
    allow_duplicate = True
    allow_import_from_xml = False
    allow_import_from_csv = False
    allow_copy_and_paste = False
    # Size of the icon beside each entry in the list. Shrink for data that has no icons
    icon_size = 32
    # Whether the tab can show its data again after an undo changes it
    supports_undo = True

    def __init__(self, parent, database: Database, resources: Resources = None) -> None:
        QWidget.__init__(self, parent)
        self.setWindowTitle(_('%s Editor') % self.properties_type.title)
        self._db = database
        self._res = resources

        self.left_frame = QWidget()
        left_frame_layout = QVBoxLayout()
        self.left_frame.setLayout(left_frame_layout)
        self.tree_list = LTNestedList(self, self.data.keys(), self.data.categories, self.allow_rename,
                                      self.allow_duplicate, self.get_icon, self.get_foreground,
                                      self.on_select, self.resort_db, self.on_begin_rename,
                                      self.delete_from_db, self.create_new, self.duplicate, self.rename,
                                      self.get_search_text, icon_size=self.icon_size)
        left_frame_layout.setContentsMargins(0, 0, 0, 0)
        left_frame_layout.setSpacing(0)
        left_frame_layout.addWidget(self.tree_list)

        button_frame = QWidget()
        button_frame_layout = QGridLayout(button_frame)
        
        if self.allow_import_from_csv:
            import_csv_button = QPushButton("Import .csv")
            import_csv_button.clicked.connect(self.import_csv)
            button_frame_layout.addWidget(import_csv_button, 0, 0, 1, 4)

        if self.allow_import_from_xml:
            import_xml_button = QPushButton("Import .xml")
            import_xml_button.clicked.connect(self.import_xml)
            button_frame_layout.addWidget(import_xml_button, 1, 0, 1, 4)

        if self.allow_copy_and_paste:
            copy_to_clipboard_button = QPushButton("Copy to clipboard")
            copy_to_clipboard_button.clicked.connect(self.copy_to_clipboard)
            button_frame_layout.addWidget(copy_to_clipboard_button, 2, 0, 1, 2)
            paste_from_clipboard_button = QPushButton("Paste from clipboard")
            paste_from_clipboard_button.clicked.connect(self.paste_from_clipboard)
            button_frame_layout.addWidget(paste_from_clipboard_button, 2, 2, 1, 2)

        left_frame_layout.addWidget(button_frame)
        self.right_frame = self.properties_type(self, None, self.attempt_change_nid,
                                                lambda: self.tree_list.regenerate_icons(initial_generation=True))
        self.splitter = QSplitter(self)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.addWidget(self.left_frame)
        self.splitter.addWidget(self.right_frame)
        self.splitter.setStyleSheet(
            "QSplitter::handle:horizontal {background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #eee, stop:1 #ccc); border: 1px solid #777; width: 13px; margin-top: 2px; margin-bottom: 2px; border-radius: 4px;}")

        self._layout = QHBoxLayout(self)
        self.setLayout(self._layout)

        self._layout.addWidget(self.splitter)

    @classmethod
    def edit(cls, parent=None):
        """This tab's editor window, not yet shown"""
        return SingleDatabaseEditor(cls, parent)

    def reset(self):
        """Shows the database again, as it is now. The properties widget draws on data
        other tabs own -- a unit's stat columns come from DB.stats -- and an undo may
        have taken away or renamed the shown entry."""
        current = self.right_frame.current
        if current is not None and not any(entry is current for entry in self.data):
            current = self.neighbour_of(current.nid)
        for box in self.right_frame.findChildren(ObjBox):
            box.refresh()
        # Rebuilding the list drops its selection, and so the binding, so select
        # the entry again by its nid
        # Rearranging the list puts a new categories object on the catalog, so read it afresh
        self.tree_list.reset(self.data.keys(), self.data.categories)
        if current is not None:
            self.tree_list.select_item(current.nid)
        else:
            self.on_select(None)

    def neighbour_of(self, nid: NID):
        """The entry the list showed below nid, or else above it, that is still in the
        catalog: what takes the place of a shown entry something else deleted"""
        shown, _ = self.tree_list.get_list_and_category_structure()
        if nid not in shown:
            return self.data[0] if self.data else None
        idx = shown.index(nid)
        for other in shown[idx + 1:] + shown[:idx][::-1]:
            if other in self.data:
                return self.data.get(other)
        return None

    def attempt_change_nid(self, old_nid: NID, new_nid: NID) -> bool:
        if not new_nid:
            return False
        if old_nid == new_nid:
            return True
        if self.data.get(new_nid):
            QMessageBox.warning(self, 'Warning', 'ID %s already in use' % new_nid)
            return False
        with HISTORY.change_set('Rename %s' % old_nid, origin=self), \
                HISTORY.modifying([(self.data.get(old_nid), self.data)]):
            self._on_nid_changed(old_nid, new_nid)
            if isinstance(self.data, ManifestCatalog):
                self.data.update_nid(self.data.get(old_nid), new_nid)
            else:
                self.data.change_key(old_nid, new_nid)
        self.tree_list.update_nid(old_nid, new_nid)
        self.tree_list.on_filter_changed(self.tree_list.search_box.text())
        return True

    def on_select(self, entry_nid: Optional[NID]):
        if not entry_nid:
            HISTORY.bind(None, self.data, self)
            self.right_frame.set_current(None)
            return
        curr_entry = self.data.get(entry_nid)
        if curr_entry:
            HISTORY.commit(origin=self)
            self.right_frame.set_current(curr_entry)
            HISTORY.bind(curr_entry, self.data, self)

    def resort_db(self, entries: List[str], categories: Categories):
        self.data.categories = categories
        self.data.sort(lambda x: entries.index(x.nid) if x.nid in entries else -1)

    def on_begin_rename(self, entry_nid: NID, on_begin: bool = True):
        self.right_frame.setEnabled(not on_begin)
        return

    def delete_from_db(self, nid):
        if len(self.data) == 1:
            return False
        with HISTORY.change_set('Delete %s' % nid, origin=self):
            if self._on_delete(nid):
                self.data.remove_key(nid)
                return True
        return False

    def create_new(self, nid):
        if self.data.get(nid):
            QMessageBox.warning(self, 'Warning', 'ID %s already in use' % nid)
            return False
        new_obj = self.catalog_type.datatype(nid, nid, '')
        self.data.append(new_obj)
        return True

    def duplicate(self, old_nid, nid):
        if self.data.get(nid):
            QMessageBox.warning(self, 'Warning', 'ID %s already in use' % nid)
            return False
        orig_obj = self.data.get(old_nid)
        if not orig_obj:
            QMessageBox.warning(self, 'Warning', 'ID %s not found' % old_nid)
            return False
        orig_obj = self.catalog_type.datatype.restore(orig_obj.save())
        orig_obj.nid = nid
        self.data.append(orig_obj)
        return True

    def rename(self, old_nid, new_nid):
        if self.data.get(new_nid):
            QMessageBox.warning(self, 'Warning', 'ID %s already in use' % new_nid)
            return False
        orig_obj = self.data.get(old_nid)
        if not orig_obj:
            QMessageBox.warning(self, 'Warning', 'ID %s not found' % old_nid)
            return False
        with HISTORY.change_set('Rename %s' % old_nid, origin=self), HISTORY.modifying([(orig_obj, self.data)]):
            self._on_nid_changed(old_nid, new_nid)
            if isinstance(self.data, ManifestCatalog):
                self.data.update_nid(self.data.get(old_nid), new_nid)
            else:
                self.data.change_key(old_nid, new_nid)
        self.tree_list.on_filter_changed(self.tree_list.search_box.text())
        self.tree_list.select_item(new_nid)
        return True

    def copy_to_clipboard(self):
        selected_nid = self.tree_list.get_selected_nid()
        if selected_nid:
            clipboard = QApplication.clipboard()
            prefab = self.data.get(selected_nid)
            if prefab:
                json_string = json.dumps([prefab.save()])
                clipboard.setText(json_string)

    def paste_from_clipboard(self):
        clipboard = QApplication.clipboard()
        json_string = clipboard.text()
        try:
            any_nid = None
            ser_list = json.loads(json_string)
            for ser_dict in reversed(ser_list):
                prefab = self.data.datatype.restore(ser_dict)
                prefab.nid = str_utils.get_next_name(prefab.nid, self.data.keys())
                self.data.append(prefab)
                any_nid = prefab.nid
            self.reset()
            if any_nid:
                self.tree_list.select_item(any_nid)
        except Exception as e:
            logging.warning("Could not read from clipboard! %s" % e)
            QMessageBox.critical(self, "Import Error", "Could not read valid json from clipboard!")

    @classmethod
    def create(cls, parent=None, db=None, res=None):
        db = db or DB
        res = res or RESOURCES
        return cls(parent, db, res)

    @property
    def data(self):
        raise NotImplementedError

    def get_icon(self, unit_nid: NID) -> Optional[QIcon]:
        raise NotImplementedError

    def get_foreground(self, unit_nid: NID) -> Optional[QBrush]:
        return None

    def get_search_text(self, nid: NID) -> str:
        """All the text the search box matches against for this entry"""
        return nid

    def import_xml(self):
        raise NotImplementedError

    def import_csv(self):
        raise NotImplementedError

    def _on_nid_changed(self, old_nid: NID, new_nid: NID):
        """
        Handles updating other objects in the engine with this nid change
        Should be implemented in the child class
        """
        raise NotImplementedError

    def _on_delete(self, nid: NID) -> bool:
        """
        Handles updating other objects in the engine with this deletion
        Returns whether the user wants to proceed with the deletion
        Should be implemented in the child class
        """
        raise NotImplementedError

    # @todo(mag) fix the unit tab (which is the only time this callback is used forcibly in data_editor.py) and remove this
    def on_tab_close(self):
        pass
