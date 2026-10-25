import logging
import unittest
from unittest.mock import patch

from app.tests import qt_headless  # noqa: F401 -- before any QApplication

from app.data.database.database import DB
from app.data.resources.resources import RESOURCES
from app.data.serialization.versions import CURRENT_SERIALIZATION_VERSION

UNIT = 'Eirika'
CLASS = 'Eirika_Lord'
SWAP_CLASS = 'Ephraim_Lord'


class ChangeBusTests(unittest.TestCase):
    """Two editors open on one database: what one changes, the other shows"""
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
        from app.editor.data_editor import SingleDatabaseEditor
        from app.editor.class_editor.new_class_tab import NewClassDatabase
        from app.editor.unit_editor.new_unit_tab import NewUnitDatabase
        self.class_dialog = self.open(SingleDatabaseEditor, NewClassDatabase)
        self.class_tab = self.class_dialog.tab
        self.unit_dialog = self.open(SingleDatabaseEditor, NewUnitDatabase)
        self.unit_tab = self.unit_dialog.tab
        self.unit_tab.on_select(UNIT)

    def open(self, dialog_type, tab_type):
        dialog = dialog_type(tab_type)
        self.addCleanup(dialog.stop_history)
        self.addCleanup(dialog.hide)
        return dialog

    def choices(self, box):
        return [box.edit.itemText(i) for i in range(box.edit.count())]

    def delete_class(self, nid, swap):
        from app.extensions.custom_gui import DeletionDialog
        with patch.object(DeletionDialog, 'get_swap', return_value=(DB.classes.get(swap), True)):
            self.assertTrue(self.class_tab.delete_from_db(nid))

    def test_a_rename_in_one_editor_shows_in_the_other(self):
        self.class_tab.rename(CLASS, 'Lady')
        self.app.processEvents()

        class_box = self.unit_tab.right_frame.class_box
        self.assertEqual('Lady', class_box.edit.currentText())
        self.assertIn('Lady', self.choices(class_box))
        self.assertNotIn(CLASS, self.choices(class_box))

    def test_a_delete_in_one_editor_shows_in_the_other(self):
        self.delete_class(CLASS, SWAP_CLASS)
        self.app.processEvents()

        class_box = self.unit_tab.right_frame.class_box
        self.assertEqual(SWAP_CLASS, class_box.edit.currentText())
        self.assertNotIn(CLASS, self.choices(class_box))

    def test_an_undo_in_one_editor_shows_in_the_other(self):
        self.class_tab.rename(CLASS, 'Lady')
        self.app.processEvents()

        self.class_dialog.undo()
        self.app.processEvents()

        class_box = self.unit_tab.right_frame.class_box
        self.assertEqual(CLASS, class_box.edit.currentText())
        self.assertNotIn('Lady', self.choices(class_box))

    def test_the_shown_record_deleted_elsewhere_gives_way_to_another(self):
        from app.editor.data_editor import SingleDatabaseEditor
        from app.editor.unit_editor.new_unit_tab import NewUnitDatabase
        other_tab = self.open(SingleDatabaseEditor, NewUnitDatabase).tab
        other_tab.on_select(UNIT)
        eirika = DB.units.get(UNIT)

        from app.extensions.custom_gui import DeletionDialog
        with patch.object(DeletionDialog, 'inform', return_value=True):
            self.assertTrue(self.unit_tab.delete_from_db(UNIT))
        self.app.processEvents()

        self.assertIsNot(eirika, other_tab.right_frame.current)
        self.assertIn(other_tab.right_frame.current, list(DB.units))

    def test_an_edit_does_not_redraw_the_editor_that_made_it(self):
        self.app.processEvents()
        with patch.object(self.unit_tab, 'reset') as unit_reset, \
                patch.object(self.class_tab, 'reset') as class_reset:
            self.unit_tab.right_frame.name_box.edit.setText('Somebody')
            self.history.commit(origin=self.unit_tab)  # As a change of focus within it would
            self.app.processEvents()

        unit_reset.assert_not_called()
        class_reset.assert_called_once()

    def test_a_box_keeps_its_choice_when_a_record_above_it_is_deleted(self):
        # As the level editor's Load Unit dialog does, while the unit editor opened from it deletes
        from app.editor.custom_widgets import UnitBox
        box = UnitBox()
        self.addCleanup(box.deleteLater)
        box.edit.setValue('Gilliam')
        self.assertLess(DB.units.index('Franz'), DB.units.index('Gilliam'))

        from app.extensions.custom_gui import DeletionDialog
        with patch.object(DeletionDialog, 'inform', return_value=True):
            self.assertTrue(self.unit_tab.delete_from_db('Franz'))
        box.refresh()

        self.assertEqual('Gilliam', box.edit.currentText())

    def test_a_box_shows_its_choice_again_when_an_undo_brings_it_back(self):
        from app.editor.custom_widgets import UnitBox
        box = UnitBox()
        self.addCleanup(box.deleteLater)
        box.edit.setValue('Gilliam')
        from app.extensions.custom_gui import DeletionDialog
        with patch.object(DeletionDialog, 'inform', return_value=True):
            self.assertTrue(self.unit_tab.delete_from_db('Gilliam'))
        box.refresh()
        self.assertEqual('', box.edit.currentText())

        self.unit_dialog.undo()
        box.refresh()

        self.assertEqual('Gilliam', box.edit.currentText())

    def test_a_legacy_editor_shows_a_delete_made_in_another(self):
        from app.editor.data_editor import SingleDatabaseEditor
        from app.editor.party_editor.party_tab import PartyDatabase
        party_tab = self.open(SingleDatabaseEditor, PartyDatabase).tab
        leader_box = party_tab.right_frame.leader_box
        self.assertIn(UNIT, self.choices(leader_box))

        from app.extensions.custom_gui import DeletionDialog
        with patch.object(DeletionDialog, 'inform', return_value=True):
            self.assertTrue(self.unit_tab.delete_from_db(UNIT))
        self.app.processEvents()

        self.assertNotIn(UNIT, self.choices(leader_box))
        self.assertEqual(DB.parties.get('Eirika').leader, leader_box.edit.currentText())


if __name__ == '__main__':
    unittest.main()
