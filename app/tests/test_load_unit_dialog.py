import logging
import unittest
from unittest.mock import patch

from app.tests import qt_headless  # noqa: F401 -- before any QApplication

from app.data.database.database import DB
from app.data.resources.resources import RESOURCES
from app.data.serialization.versions import CURRENT_SERIALIZATION_VERSION


class LoadUnitDialogTests(unittest.TestCase):
    """The level editor's Load Unit dialog, and the unit editor opened from it"""
    @classmethod
    def setUpClass(cls):
        import sys
        from app.editor.editor_locale import init_locale
        init_locale()
        from PyQt5.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication(sys.argv)

    def setUp(self):
        from PyQt5.QtWidgets import QMessageBox, QWidget
        from app.editor.edit_history import HISTORY
        logging.disable(logging.CRITICAL)
        self.addCleanup(logging.disable, logging.NOTSET)
        DB.load('testing_proj.ltproj', CURRENT_SERIALIZATION_VERSION)
        RESOURCES.load('testing_proj.ltproj', CURRENT_SERIALIZATION_VERSION)
        HISTORY.clear()
        self.messages = []
        for name in ('warning', 'information'):
            patcher = patch.object(QMessageBox, name, side_effect=lambda *a, **k: self.messages.append(a[2]))
            patcher.start()
            self.addCleanup(patcher.stop)
        # Stands in for the level editor's unit painter
        self.painter = QWidget()
        self.addCleanup(self.painter.deleteLater)
        self.painter.current_level = DB.levels.get('0')
        self.free_unit = next(unit.nid for unit in DB.units if unit.nid not in self.painter.current_level.units)

    def load_unit_dialog(self, level_unit=None):
        from app.editor.level_editor.unit_painter_menu import LoadUnitDialog
        dialog = LoadUnitDialog(self.painter, level_unit)
        self.addCleanup(dialog.deleteLater)
        return dialog

    def open_unit_editor(self, closing):
        """Runs closing(editor) in place of the user, while the unit editor is open"""
        from PyQt5.QtWidgets import QDialog
        from app.editor.data_editor import SingleDatabaseEditor

        def exec_(editor):
            self.editor_opened_on = editor.tab.right_frame.current.nid
            accepted = closing(editor)
            (editor.accept if accepted else editor.reject)()
            return QDialog.Accepted if accepted else QDialog.Rejected
        return patch.object(SingleDatabaseEditor, 'exec_', exec_)

    def delete_in(self, editor, nid):
        from app.extensions.custom_gui import DeletionDialog
        tree = editor.tab.tree_list
        with patch.object(DeletionDialog, 'inform', return_value=True):
            tree.delete(tree.find_item_by_nid(nid))  # As its context menu does
        self.app.processEvents()

    def test_level_edits_from_before_the_unit_editor_opened_are_recorded_and_kept_on_its_cancel(self):
        from app.editor.edit_history import HISTORY
        from app.editor.lib.state_editor.editor_state_manager import EditorStateManager
        from app.editor.level_editor.level_editor import LevelEditor
        check = patch('app.editor.edit_history.CHECK_UNRECORDED', True)
        check.start()
        self.addCleanup(check.stop)
        HISTORY.clear()  # The check starts from the database as it is now
        state_manager = EditorStateManager()
        level_editor = LevelEditor(state_manager)  # Shows level 0, as the main window does
        self.addCleanup(level_editor.deleteLater)
        state_manager.change_and_broadcast('selected_level', '0')
        level = self.painter.current_level
        level_unit = level.units.get('Eirika')
        dialog = self.load_unit_dialog(level_unit)
        dialog.unit_box.edit.setValue(self.free_unit)  # Edits the level

        with patch.object(logging, 'warning') as warning, self.open_unit_editor(lambda editor: False):
            dialog.access_units()

        self.assertEqual([], [c for c in warning.call_args_list if 'LT_EDITOR_CHECK' in c.args[0]])
        self.assertIs(level_unit, level.units.get(self.free_unit))

    def test_the_unit_editor_opens_on_the_unit_and_gives_it_back_only_on_ok(self):
        from app.editor.unit_editor import new_unit_tab
        with self.open_unit_editor(lambda editor: True):
            unit, ok = new_unit_tab.get('Seth')
        self.assertEqual('Seth', self.editor_opened_on)
        self.assertIs(DB.units.get('Seth'), unit)
        self.assertTrue(ok)

        with self.open_unit_editor(lambda editor: False):
            self.assertEqual((None, False), new_unit_tab.get('Seth'))

    def test_deleting_the_chosen_unit_then_ok_chooses_the_unit_the_editor_shows(self):
        dialog = self.load_unit_dialog()
        dialog.unit_box.edit.setValue(self.free_unit)

        with self.open_unit_editor(lambda editor: self.delete_in(editor, self.free_unit) or True):
            dialog.access_units()

        self.assertIn(dialog.current.nid, DB.units)
        self.assertEqual(dialog.current.nid, dialog.unit_box.edit.currentText())

    def test_deleting_the_chosen_unit_then_cancel_keeps_it(self):
        dialog = self.load_unit_dialog()
        dialog.unit_box.edit.setValue(self.free_unit)

        with self.open_unit_editor(lambda editor: self.delete_in(editor, self.free_unit)):
            dialog.access_units()
        self.app.processEvents()

        self.assertEqual(self.free_unit, dialog.current.nid)
        self.assertIn(self.free_unit, DB.units)

    def test_ok_refuses_a_unit_that_no_longer_exists(self):
        from PyQt5.QtWidgets import QDialog
        dialog = self.load_unit_dialog()
        dialog.unit_box.edit.setValue(self.free_unit)
        from app.editor.data_editor import SingleDatabaseEditor
        from app.editor.unit_editor.new_unit_tab import NewUnitDatabase
        editor = SingleDatabaseEditor(NewUnitDatabase)
        self.addCleanup(editor.stop_history)
        self.delete_in(editor, self.free_unit)

        dialog.accept()

        self.assertNotEqual(QDialog.Accepted, dialog.result())
        self.assertEqual(['Unit %s no longer exists. Choose another unit.' % self.free_unit], self.messages)

    def test_a_level_unit_whose_unit_is_deleted_closes_the_dialog(self):
        level_unit = self.painter.current_level.units.get('Eirika')
        dialog = self.load_unit_dialog(level_unit)

        with patch.object(dialog, 'reject') as reject, \
                self.open_unit_editor(lambda editor: self.delete_in(editor, 'Eirika') or True):
            dialog.access_units()

        reject.assert_called_once()
        self.assertEqual(['Unit Eirika is no longer in the level.'], self.messages)

    def test_a_level_unit_is_found_again_after_cancel_rebuilds_the_level(self):
        level_unit = self.painter.current_level.units.get('Eirika')
        other = next(unit.nid for unit in self.painter.current_level.units if unit is not level_unit and not unit.generic)
        dialog = self.load_unit_dialog(level_unit)

        with self.open_unit_editor(lambda editor: self.delete_in(editor, other)):
            dialog.access_units()

        self.assertIsNot(level_unit, dialog.current)
        self.assertIs(self.painter.current_level.units.get('Eirika'), dialog.current)

    def test_a_level_unit_is_found_again_after_its_unit_is_renamed_and_the_rename_undone(self):
        level_unit = self.painter.current_level.units.get('Eirika')
        dialog = self.load_unit_dialog(level_unit)

        def rename_and_undo(editor):
            editor.tab.rename('Eirika', 'Lady')
            editor.undo()
            return True
        with self.open_unit_editor(rename_and_undo):
            dialog.access_units()

        self.assertEqual([], self.messages)
        self.assertIs(self.painter.current_level.units.get('Eirika'), dialog.current)

    def test_cancel_gives_a_level_unit_back_its_unit_with_its_groups_and_travelers(self):
        from app.data.database.level_units import UnitGroup
        level = self.painter.current_level
        level_unit = level.units.get('Eirika')
        group = UnitGroup('Eirika_Group', ['Eirika'], {'Eirika': (1, 1)})
        level.unit_groups.append(group)
        carrier = next(unit for unit in level.units if unit is not level_unit)
        carrier.starting_traveler = 'Eirika'
        team, ai = level_unit.team, level_unit.ai
        dialog = self.load_unit_dialog(level_unit)
        dialog.unit_box.edit.setValue(self.free_unit)
        dialog.team_box.edit.setValue('enemy')
        dialog.team_changed(None)
        self.assertIs(level_unit, level.units.get(self.free_unit))

        dialog.reject()

        self.assertIs(level_unit, level.units.get('Eirika'))
        self.assertNotIn(self.free_unit, level.units.keys())
        self.assertEqual(('Eirika', team, ai), (level_unit.nid, level_unit.team, level_unit.ai))
        self.assertEqual(['Eirika'], group.units)
        self.assertEqual({'Eirika': (1, 1)}, group.positions)
        self.assertEqual('Eirika', carrier.starting_traveler)

    def test_cancel_gives_a_level_unit_back_its_unit_by_the_name_the_unit_editor_gave_it(self):
        level = self.painter.current_level
        level_unit = level.units.get('Eirika')
        dialog = self.load_unit_dialog(level_unit)
        dialog.unit_box.edit.setValue(self.free_unit)

        with self.open_unit_editor(lambda editor: editor.tab.rename('Eirika', 'Lady') or True):
            dialog.access_units()
        dialog.reject()

        self.assertIs(level_unit, level.units.get('Lady'))
        self.assertEqual('Lady', level_unit.nid)
        self.assertNotIn(self.free_unit, level.units.keys())


if __name__ == '__main__':
    unittest.main()
