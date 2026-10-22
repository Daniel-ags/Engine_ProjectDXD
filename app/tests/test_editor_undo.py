import logging
import unittest
from unittest.mock import patch

from app.tests import qt_headless  # noqa: F401 -- before any QApplication

from app.data.database.database import DB
from app.data.resources.resources import RESOURCES
from app.data.serialization.versions import CURRENT_SERIALIZATION_VERSION

UNIT = 'Eirika'
ITEM = 'Iron_Sword'


class EditorUndoTestCase(unittest.TestCase):
    """Drives the real editor dialogs without showing them"""
    @classmethod
    def setUpClass(cls):
        import sys
        from app.editor.editor_locale import init_locale
        init_locale()
        from PyQt5.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication(sys.argv)

    def setUp(self):
        from app.editor.edit_history import HISTORY
        logging.disable(logging.CRITICAL)
        self.addCleanup(logging.disable, logging.NOTSET)
        DB.load('testing_proj.ltproj', CURRENT_SERIALIZATION_VERSION)
        RESOURCES.load('testing_proj.ltproj', CURRENT_SERIALIZATION_VERSION)
        HISTORY.clear()
        self.history = HISTORY

    def open(self, dialog_type, tab_type):
        dialog = dialog_type(tab_type)
        self.addCleanup(dialog.stop_history)
        self.addCleanup(dialog.hide)
        return dialog


class ItemEditorUndoTests(EditorUndoTestCase):
    def setUp(self):
        super().setUp()
        from app.editor.data_editor import SingleDatabaseEditor
        from app.editor.item_editor.new_item_tab import NewItemDatabase
        self.dialog = self.open(SingleDatabaseEditor, NewItemDatabase)
        self.tab = self.dialog.tab
        self.tab.on_select(ITEM)
        self.item = DB.items.get(ITEM)

    def type_name(self, text):
        self.tab.right_frame.name_box.edit.setText(text)
        self.history.commit()  # As a change of focus would

    def test_ctrl_z_takes_back_an_edit_and_shows_it(self):
        old_name = self.item.name
        self.type_name('Renamed Sword')

        self.dialog.undo()

        self.assertEqual(old_name, self.item.name)
        self.assertEqual(old_name, self.tab.right_frame.name_box.edit.text())

        self.dialog.redo()
        self.assertEqual('Renamed Sword', self.item.name)

    def test_cancel_takes_back_everything_since_opening(self):
        old_name = self.item.name
        self.type_name('Renamed Sword')
        self.tab.rename(ITEM, 'Sword_Two')

        self.dialog.reject()

        self.assertIs(self.item, DB.items.get(ITEM))
        self.assertEqual(old_name, self.item.name)
        self.assertNotIn('Sword_Two', DB.items)

    def test_renaming_from_the_list_is_one_undo_step(self):
        DB.units.get(UNIT).starting_items = [[ITEM, False]]
        self.history.commit()
        self.tab.rename(ITEM, 'Sword_Two')
        self.assertEqual([['Sword_Two', False]], DB.units.get(UNIT).starting_items)

        self.dialog.undo()

        self.assertIs(self.item, DB.items.get(ITEM))
        self.assertEqual([[ITEM, False]], DB.units.get(UNIT).starting_items)

    def test_deleting_is_one_undo_step(self):
        DB.units.get(UNIT).starting_items = [[ITEM, False]]
        self.history.commit()
        from app.extensions.custom_gui import DeletionDialog
        with patch.object(DeletionDialog, 'get_swap', return_value=(DB.items.get('Vulnerary'), True)):
            self.assertTrue(self.tab.delete_from_db(ITEM))

        self.dialog.undo()

        self.assertIs(self.item, DB.items.get(ITEM))
        self.assertEqual([[ITEM, False]], DB.units.get(UNIT).starting_items)

    def test_undo_stops_where_the_dialog_opened(self):
        self.dialog.reject()
        self.type_name('Changed in another editor')
        from app.editor.data_editor import SingleDatabaseEditor
        from app.editor.item_editor.new_item_tab import NewItemDatabase
        dialog = self.open(SingleDatabaseEditor, NewItemDatabase)

        dialog.undo()

        self.assertEqual('Changed in another editor', self.item.name)


class LegacyEditorUndoTests(EditorUndoTestCase):
    def setUp(self):
        super().setUp()
        from app.editor.data_editor import SingleDatabaseEditor
        from app.editor.faction_editor.faction_tab import FactionDatabase
        self.dialog = self.open(SingleDatabaseEditor, FactionDatabase)
        self.tab = self.dialog.tab

    def test_an_edit_in_the_shown_record_is_undone_and_shown(self):
        faction = self.tab.right_frame.current
        old_name = faction.name
        self.tab.right_frame.name_box.edit.setText('Somebody')
        self.history.commit()

        self.dialog.undo()

        self.assertEqual(old_name, faction.name)
        self.assertEqual(old_name, self.tab.right_frame.name_box.edit.text())

    def test_the_keys_step_through_history_after_focus_moves_on(self):
        from PyQt5.QtCore import Qt
        from PyQt5.QtTest import QTest
        self.dialog.show()
        self.dialog.activateWindow()
        self.app.processEvents()
        faction = self.tab.right_frame.current
        old_name = faction.name
        name_box = self.tab.right_frame.name_box.edit
        name_box.setFocus()
        name_box.setText('Somebody')
        view = self.tab.left_frame.view
        view.setFocus()  # Moving focus on commits the edit
        self.app.processEvents()

        QTest.keyClick(view, Qt.Key_Z, Qt.ControlModifier)
        self.assertEqual(old_name, faction.name)
        QTest.keyClick(view, Qt.Key_Z, Qt.ControlModifier | Qt.ShiftModifier)
        self.assertEqual('Somebody', faction.name)

    def test_a_field_with_typing_of_its_own_undoes_that_first(self):
        from PyQt5.QtCore import Qt
        from PyQt5.QtTest import QTest
        self.dialog.show()
        self.dialog.activateWindow()
        self.app.processEvents()
        name_box = self.tab.right_frame.name_box.edit
        name_box.setFocus()
        self.app.processEvents()
        name_box.setText('Typed')
        name_box.insert('x')

        QTest.keyClick(name_box, Qt.Key_Z, Qt.ControlModifier)

        self.assertEqual('Typed', name_box.text())
        self.assertEqual('Typed', self.tab.right_frame.current.name)

    def test_creating_is_undone_and_the_list_shows_what_is_left(self):
        count = len(DB.factions)
        self.tab.left_frame.model.append()
        self.assertEqual(count + 1, len(DB.factions))

        self.dialog.undo()

        self.assertEqual(count, len(DB.factions))
        self.assertIn(self.tab.right_frame.current, list(DB.factions))

    def test_deleting_with_its_cascade_is_one_undo_step(self):
        faction = DB.factions[0]
        level_unit = DB.levels.get('0').units.get('101')
        level_unit.faction = faction.nid
        self.history.commit()
        from app.extensions.custom_gui import DeletionDialog
        with patch.object(DeletionDialog, 'get_swap', return_value=(DB.factions[1], True)):
            self.tab.left_frame.model.delete(0)
        self.assertNotIn(faction.nid, DB.factions)

        self.dialog.undo()

        self.assertIs(faction, DB.factions.get(faction.nid))
        self.assertEqual(faction.nid, DB.levels.get('0').units.get('101').faction)


if __name__ == '__main__':
    unittest.main()
