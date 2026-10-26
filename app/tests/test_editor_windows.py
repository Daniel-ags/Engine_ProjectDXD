from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.tests import qt_headless  # noqa: F401 -- before any QApplication

from PyQt5 import sip
from PyQt5.QtCore import QEvent
from PyQt5.QtGui import QCloseEvent
from PyQt5.QtWidgets import QApplication, QWidget

from app.tests.test_staging import StagingEditorCase


class EditorWindowTests(StagingEditorCase):
    """The main window's editors open as windows beside it, one of each at a time"""
    project = 'default.ltproj'  # Its metadata names its serialization version, which a load reads

    def setUp(self):
        super().setUp()
        from app.editor.editor_windows import EditorWindows
        self.windows = EditorWindows()
        self.addCleanup(self.close_all)

    def close_all(self):
        self.windows.close_all()
        self.settle()

    def settle(self):
        QApplication.processEvents()
        # A window closed is deleted once the event loop gets back to it
        QApplication.sendPostedEvents(None, QEvent.DeferredDelete)

    def units(self):
        from app.editor.unit_editor.new_unit_tab import NewUnitDatabase
        return self.windows.open(NewUnitDatabase.edit, None)

    def items(self):
        from app.editor.item_editor.new_item_tab import NewItemDatabase
        return self.windows.open(NewItemDatabase.edit, None)

    def test_an_editor_opens_without_blocking_the_rest(self):
        window = self.units()
        self.settle()

        self.assertTrue(window.isVisible())
        self.assertFalse(window.isModal())
        self.assertIsNone(QApplication.activeModalWidget())

    def test_two_editors_are_open_at_once(self):
        units, items = self.units(), self.items()
        self.settle()

        self.assertTrue(units.isVisible())
        self.assertTrue(items.isVisible())

    def test_opening_an_open_editor_brings_back_the_same_window(self):
        window = self.units()
        self.items()

        self.assertIs(window, self.units())
        self.assertEqual(2, len(self.windows.windows))

    def test_a_closed_editor_is_deleted_and_opens_anew(self):
        for close in ('close', 'accept', 'reject'):
            window = self.units()
            getattr(window, close)()
            self.settle()

            self.assertTrue(sip.isdeleted(window), close)
            self.assertEqual({}, self.windows.windows, close)
            reopened = self.units()
            self.assertIsNot(window, reopened)
            reopened.close()
            self.settle()

    def portraits(self):
        from app.editor.portrait_editor.new_portrait_tab import NewPortraitDatabase
        return self.windows.open(NewPortraitDatabase.edit, None)

    def test_an_editor_window_has_only_close_and_a_picker_ok_and_cancel(self):
        from PyQt5.QtWidgets import QDialogButtonBox
        from app.editor.data_editor import SingleDatabaseEditor, SingleResourceEditor
        from app.editor.portrait_editor.new_portrait_tab import NewPortraitDatabase
        from app.editor.unit_editor.new_unit_tab import NewUnitDatabase
        for window in (self.units(), self.portraits()):
            self.assertEqual(QDialogButtonBox.Close, window.buttonbox.standardButtons())
        for picker in (SingleDatabaseEditor(NewUnitDatabase, picker=True),
                       SingleResourceEditor(NewPortraitDatabase, ['portraits'], picker=True)):
            self.addCleanup(picker.stop_history)
            self.assertEqual(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, picker.buttonbox.standardButtons())

    def test_closing_an_editor_window_keeps_its_edits(self):
        from app.data.database.database import DB
        from app.data.resources.resources import RESOURCES
        units, portraits = self.units(), self.portraits()
        unit, portrait = DB.units.get('Eirika'), RESOURCES.portraits.get('Eirika')
        units.tab.rename('Eirika', 'Lady')
        portraits.tab.rename('Eirika', 'Lady')

        units.close()
        portraits.close()
        self.settle()

        self.assertIs(unit, DB.units.get('Lady'))
        self.assertIs(portrait, RESOURCES.portraits.get('Lady'))

    def test_undo_in_one_window_takes_back_an_edit_made_in_another_before_it_opened(self):
        from app.data.database.database import DB
        units = self.units()
        unit = DB.units.get('Eirika')
        units.tab.tree_list.select_item('Eirika')
        units.tab.rename('Eirika', 'Lady')
        items = self.items()

        items.undo()
        self.settle()

        self.assertIs(unit, DB.units.get('Eirika'))
        self.assertEqual('Eirika', units.tab.right_frame.current.nid)

    def test_close_all_closes_every_editor(self):
        units, items = self.units(), self.items()

        self.windows.close_all()
        self.settle()

        self.assertTrue(sip.isdeleted(units))
        self.assertTrue(sip.isdeleted(items))
        self.assertEqual({}, self.windows.windows)

    def test_loading_a_project_closes_the_editor_windows(self):
        from app.editor.file_manager.project_file_backend import ProjectFileBackend
        from app.editor.settings import MainSettingsController
        window = self.units()
        main = QWidget()
        self.addCleanup(main.deleteLater)
        main.editor_windows = self.windows
        backend = ProjectFileBackend(main, None)
        backend.current_proj = self.proj

        with patch.object(MainSettingsController, 'append_or_bump_project', lambda _, name, path: None):
            self.assertTrue(backend.load())
        self.settle()

        self.assertTrue(sip.isdeleted(window))
        self.assertEqual({}, self.windows.windows)

    def quit(self, save_answer: bool) -> QCloseEvent:
        from app.editor.main_editor import MainEditor
        main = SimpleNamespace(settings=MagicMock(), saveGeometry=lambda: None,
                               project_save_load_handler=MagicMock(),
                               editor_windows=self.windows)
        main.project_save_load_handler.maybe_save.return_value = save_answer
        event = QCloseEvent()
        MainEditor.closeEvent(main, event)
        self.settle()
        return event

    def test_cancelling_quit_leaves_the_editor_windows_open(self):
        window = self.units()

        event = self.quit(save_answer=False)

        self.assertFalse(event.isAccepted())
        self.assertFalse(sip.isdeleted(window))
        self.assertTrue(window.isVisible())

    def test_quitting_closes_the_editor_windows(self):
        window = self.units()

        event = self.quit(save_answer=True)

        self.assertTrue(event.isAccepted())
        self.assertTrue(sip.isdeleted(window))


if __name__ == '__main__':
    import unittest
    unittest.main()
