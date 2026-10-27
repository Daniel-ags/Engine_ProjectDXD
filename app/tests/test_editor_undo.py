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

    def test_closing_keeps_the_edits_and_undo_still_takes_them_back(self):
        old_name = self.item.name
        self.type_name('Renamed Sword')
        self.tab.rename(ITEM, 'Sword_Two')

        self.dialog.reject()
        self.assertIs(self.item, DB.items.get('Sword_Two'))
        self.assertEqual('Renamed Sword', self.item.name)
        self.history.undo()
        self.history.undo()

        self.assertIs(self.item, DB.items.get(ITEM))
        self.assertEqual(old_name, self.item.name)
        self.assertNotIn('Sword_Two', DB.items)

    def test_undo_reaches_edits_from_before_the_dialog_opened(self):
        old_name = DB.units.get(UNIT).name
        with self.history.modifying([(DB.units.get(UNIT), DB.units)]):
            DB.units.get(UNIT).name = 'Lady'
        self.history.commit()
        from app.editor.data_editor import SingleDatabaseEditor
        from app.editor.item_editor.new_item_tab import NewItemDatabase
        dialog = self.open(SingleDatabaseEditor, NewItemDatabase)

        dialog.undo()

        self.assertEqual(old_name, DB.units.get(UNIT).name)

    def test_renaming_from_the_list_is_one_undo_step(self):
        DB.units.get(UNIT).starting_items = [[ITEM, False]]
        self.history.commit()
        self.tab.rename(ITEM, 'Sword_Two')
        self.assertEqual([['Sword_Two', False]], DB.units.get(UNIT).starting_items)

        self.dialog.undo()

        self.assertIs(self.item, DB.items.get(ITEM))
        self.assertEqual([[ITEM, False]], DB.units.get(UNIT).starting_items)

    def test_an_edit_after_undoing_a_rename_is_still_recorded(self):
        old_name = self.item.name
        self.tab.rename(ITEM, 'Sword_Two')
        self.dialog.undo()
        self.assertIs(self.item, self.tab.right_frame.current)

        self.type_name('Renamed Sword')
        self.dialog.undo()

        self.assertEqual(old_name, self.item.name)

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


class IdBoxTests(EditorUndoTestCase):
    """An ID box renames the record, with its cascade, only when editing finishes"""
    OLD, NEW = 'Eirika_Lord', 'Eirika_Lrd'

    def setUp(self):
        super().setUp()
        from PyQt5.QtTest import QTest
        from app.editor.data_editor import SingleDatabaseEditor
        from app.editor.class_editor.new_class_tab import NewClassDatabase
        from app.editor import new_editor_tab
        patcher = patch.object(new_editor_tab.QMessageBox, 'warning')
        self.warning = patcher.start()
        self.addCleanup(patcher.stop)
        self.dialog = self.open(SingleDatabaseEditor, NewClassDatabase)
        self.dialog.show()
        self.dialog.activateWindow()
        self.dialog.tab.on_select(self.OLD)
        self.klass = DB.classes.get(self.OLD)
        self.box = self.dialog.tab.right_frame.nid_box.edit
        self.box.setFocus()
        self.app.processEvents()
        self.box.selectAll()
        QTest.keyClicks(self.box, self.NEW)

    def assertNamed(self, nid):
        self.assertEqual(nid, self.klass.nid)
        self.assertIs(self.klass, DB.classes.get(nid))
        self.assertEqual(nid, DB.units.get(UNIT).klass)
        self.assertEqual(nid, DB.levels.get('0').units.get(UNIT).klass)

    def test_typing_changes_nothing_until_editing_finishes(self):
        from PyQt5.QtCore import Qt
        from PyQt5.QtTest import QTest
        self.history.commit()
        self.assertNamed(self.OLD)
        self.assertFalse(self.history.can_undo())

        QTest.keyClick(self.box, Qt.Key_Tab)
        self.assertNamed(self.NEW)
        self.assertEqual('Lord', self.klass.name)  # The name was not the ID's

        self.dialog.undo()
        self.assertNamed(self.OLD)

    def test_switching_windows_mid_typing_renames_with_the_cascade(self):
        from PyQt5.QtWidgets import QWidget
        other = QWidget()
        self.addCleanup(other.close)
        other.show()
        other.activateWindow()
        self.app.processEvents()
        self.assertNamed(self.NEW)

        self.dialog.undo()

        self.assertNamed(self.OLD)

    def test_closing_mid_typing_renames_with_the_cascade(self):
        self.dialog.reject()
        self.app.processEvents()
        self.assertNamed(self.NEW)

        self.history.undo()

        self.assertNamed(self.OLD)

    def test_closing_after_enter_keeps_the_new_id(self):
        from PyQt5.QtCore import Qt
        from PyQt5.QtTest import QTest
        QTest.keyClick(self.box, Qt.Key_Return)
        self.assertNamed(self.NEW)

        self.dialog.reject()
        self.app.processEvents()

        self.assertNamed(self.NEW)

    def test_redo_mid_typing_renames_with_the_cascade(self):
        from PyQt5.QtCore import Qt
        from PyQt5.QtTest import QTest
        # The box has no redo of its own, so the key goes to the history
        QTest.keyClick(self.box, Qt.Key_Z, Qt.ControlModifier | Qt.ShiftModifier)
        self.assertNamed(self.NEW)

        self.dialog.undo()

        self.assertNamed(self.OLD)

    def test_ok_mid_typing_renames_with_the_cascade(self):
        self.dialog.accept()
        self.app.processEvents()
        self.assertNamed(self.NEW)


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

    def test_renaming_in_the_id_box_with_its_cascade_and_name_is_one_undo_step(self):
        from PyQt5.QtCore import Qt
        from PyQt5.QtTest import QTest
        self.dialog.show()
        self.dialog.activateWindow()
        self.app.processEvents()
        faction = self.tab.right_frame.current
        old_nid = faction.nid
        faction.name = old_nid.replace('_', ' ')
        level_unit = DB.levels.get('0').units.get('101')
        level_unit.faction = old_nid
        self.history.commit()
        self.tab.right_frame.set_current(faction)
        box = self.tab.right_frame.nid_box.edit
        box.setFocus()
        self.app.processEvents()
        box.selectAll()
        QTest.keyClicks(box, 'New_Faction')
        self.assertEqual(old_nid, faction.nid)  # Not until editing finishes

        QTest.keyClick(box, Qt.Key_Tab)
        self.assertIs(faction, DB.factions.get('New_Faction'))
        self.assertEqual('New Faction', faction.name)
        self.assertEqual('New_Faction', level_unit.faction)

        self.dialog.undo()

        self.assertIs(faction, DB.factions.get(old_nid))
        self.assertEqual(old_nid.replace('_', ' '), faction.name)
        # Undo rebuilds the level's units, so look the unit up again
        self.assertEqual(old_nid, DB.levels.get('0').units.get('101').faction)

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


class ConstantsUndoTests(EditorUndoTestCase):
    """The constants windows show every constant at once, and show them again after an undo"""
    def show(self, dialog):
        dialog.show()
        dialog.activateWindow()
        self.app.processEvents()

    def widget(self, tab, constant):
        """The widget under the constant's name"""
        from app.extensions.custom_gui import PropertyBox
        return next(box.edit for box in tab.findChildren(PropertyBox) if box.label.text() == constant.name)

    def test_ctrl_z_in_the_constants_window_takes_back_a_constant_and_shows_it(self):
        from PyQt5.QtCore import Qt
        from PyQt5.QtTest import QTest
        from app.editor.constant_tab import ConstantDatabase
        from app.editor.data_editor import SingleDatabaseEditor
        dialog = self.open(SingleDatabaseEditor, ConstantDatabase)
        self.show(dialog)
        box = self.widget(dialog.tab, DB.constants.get('num_items'))
        box.setFocus()
        old = DB.constants.value('num_items')
        box.setValue(old + 1)
        self.history.commit()

        QTest.keyClick(box, Qt.Key_Z, Qt.ControlModifier)

        self.assertEqual(old, DB.constants.value('num_items'))
        self.assertEqual(old, box.value())

    def test_an_undo_from_another_window_shows_in_the_constants_window(self):
        from app.editor.constant_tab import ConstantDatabase, MainExpEquation
        from app.editor.data_editor import SingleDatabaseEditor
        from app.engine.exp_calculator import ExpCalcType
        dialog = self.open(SingleDatabaseEditor, ConstantDatabase)
        tab = dialog.tab
        equation = tab.findChild(MainExpEquation)
        formula = ExpCalcType(DB.constants.value('exp_formula')).name
        gexp_max = DB.constants.value('gexp_max')
        music = self.widget(tab, DB.constants.get('music_main'))
        DB.constants.get('music_main').set_value('Distant Roads')
        music.setText('Distant Roads')
        self.history.commit()
        equation.exp_calc_type_selector.edit.setCurrentText(ExpCalcType.GOMPERTZ.name)
        equation.gexp_max.setValue(gexp_max + 10)
        self.history.commit()

        self.history.undo()
        self.history.undo()
        self.app.processEvents()  # The window shows the change once the undo is done

        self.assertEqual(formula, equation.exp_calc_type_selector.edit.currentText())
        self.assertTrue(equation.gompertz_exp_frame.isHidden())
        self.assertEqual(gexp_max, equation.gexp_max.value())
        self.assertEqual(DB.constants.value('music_main') or '', music.text())

    def test_ctrl_z_in_the_support_constants_takes_back_a_constant_and_shows_it(self):
        from PyQt5.QtCore import Qt
        from PyQt5.QtTest import QTest
        from app.editor.data_editor import SingleDatabaseEditor
        from app.editor.support_editor.support_constants_tab import SupportConstantDatabase
        dialog = self.open(SingleDatabaseEditor, SupportConstantDatabase)
        self.show(dialog)
        box = self.widget(dialog.tab, DB.support_constants.get('bonus_range'))
        box.setFocus()
        old = DB.support_constants.value('bonus_range')
        box.setValue(old + 1)
        self.history.commit()

        QTest.keyClick(box, Qt.Key_Z, Qt.ControlModifier)

        self.assertEqual(old, DB.support_constants.value('bonus_range'))
        self.assertEqual(old, box.value())


if __name__ == '__main__':
    unittest.main()
