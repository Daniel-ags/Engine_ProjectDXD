from unittest.mock import patch

from app.tests import qt_headless  # noqa: F401 -- before any QApplication

from PyQt5.QtWidgets import QApplication

from app.tests.test_staging import StagingEditorCase


class EditorTickTests(StagingEditorCase):
    """The editor's animation tick reaches only the window being worked in. Windows in
    the background, and windows closed, don't redraw"""
    def setUp(self):
        super().setUp()
        from app.editor import timer
        # Only the ticks the test sends
        timer.get_timer().main_timer.stop()
        self.addCleanup(timer.get_timer().main_timer.start)

    def open_shown(self, tab_type, resource_type):
        dialog = self.open(tab_type, resource_type)
        dialog.show()
        QApplication.processEvents()  # A window shown takes focus once its events are done
        return dialog

    def tick(self):
        from app.editor import timer
        timer.get_timer().tick_elapsed.emit()

    def test_only_the_active_window_hears_the_tick(self):
        from app.editor.map_sprite_editor.new_map_sprite_properties import NewMapSpriteProperties
        from app.editor.map_sprite_editor.new_map_sprite_tab import NewMapSpriteDatabase
        from app.editor.portrait_editor.new_portrait_properties import NewPortraitProperties
        from app.editor.portrait_editor.new_portrait_tab import NewPortraitDatabase
        with patch.object(NewPortraitProperties, 'tick') as portrait_tick, \
                patch.object(NewMapSpriteProperties, 'tick') as map_sprite_tick:
            portraits = self.open_shown(NewPortraitDatabase, 'portraits')
            map_sprites = self.open_shown(NewMapSpriteDatabase, 'map_sprites')
            QApplication.setActiveWindow(portraits)
            QApplication.processEvents()

            self.tick()

            self.assertEqual(1, portrait_tick.call_count)
            self.assertEqual(0, map_sprite_tick.call_count)

    def test_a_closed_window_stops_hearing_the_tick(self):
        from app.editor.portrait_editor.new_portrait_properties import NewPortraitProperties
        from app.editor.portrait_editor.new_portrait_tab import NewPortraitDatabase
        with patch.object(NewPortraitProperties, 'tick') as portrait_tick:
            portraits = self.open_shown(NewPortraitDatabase, 'portraits')
            portraits.close()
            QApplication.processEvents()

            self.tick()

            self.assertEqual(0, portrait_tick.call_count)

    def test_a_hidden_widget_hears_the_tick_only_once_shown_again(self):
        # As the main window's global editor map sits hidden behind the level editor's
        from app.editor.portrait_editor.new_portrait_properties import NewPortraitProperties
        from app.editor.portrait_editor.new_portrait_tab import NewPortraitDatabase
        with patch.object(NewPortraitProperties, 'tick') as portrait_tick:
            portraits = self.open_shown(NewPortraitDatabase, 'portraits')
            QApplication.setActiveWindow(portraits)
            QApplication.processEvents()
            properties = portraits.tab.right_frame
            properties.hide()

            self.tick()
            self.assertEqual(0, portrait_tick.call_count)

            properties.show()
            self.tick()
            self.assertEqual(1, portrait_tick.call_count)


    def test_the_class_list_redraws_its_map_sprites_only_when_their_frame_changes(self):
        from unittest.mock import PropertyMock
        from app.counters import GenericAnimCounter
        from app.editor.class_editor.new_class_tab import NewClassDatabase
        from app.editor.data_editor import SingleDatabaseEditor
        dialog = SingleDatabaseEditor(NewClassDatabase)
        self.addCleanup(dialog.stop_history)
        self.addCleanup(dialog.hide)
        dialog.show()
        QApplication.processEvents()
        QApplication.setActiveWindow(dialog)
        QApplication.processEvents()
        with patch.object(dialog.tab.tree_list, 'regenerate_icons') as regenerate, \
                patch.object(GenericAnimCounter, 'count', new_callable=PropertyMock, return_value=0) as count:
            self.tick()
            self.tick()
            self.assertEqual(1, regenerate.call_count)
            count.return_value = 1
            self.tick()
            self.assertEqual(2, regenerate.call_count)


class UndoKeyTests(StagingEditorCase):
    """An editor watches for its undo keys without filtering every event the editor
    sends, which slowed every click and redraw"""
    def test_an_editor_dialog_leaves_other_widgets_events_alone(self):
        from PyQt5.QtCore import QEvent
        from PyQt5.QtWidgets import QWidget
        from app.editor.data_editor import EditHistoryDialog
        from app.editor.portrait_editor.new_portrait_tab import NewPortraitDatabase
        with patch.object(EditHistoryDialog, 'eventFilter', return_value=False) as event_filter:
            dialog = self.open(NewPortraitDatabase, 'portraits')
            dialog.show()
            QApplication.processEvents()
            event_filter.reset_mock()
            elsewhere = QWidget()
            self.addCleanup(elsewhere.deleteLater)

            QApplication.sendEvent(elsewhere, QEvent(QEvent.User))

            self.assertEqual(0, event_filter.call_count)

    def test_ctrl_z_in_an_editor_still_undoes(self):
        from PyQt5.QtCore import Qt
        from PyQt5.QtTest import QTest
        from app.data.resources.resources import RESOURCES
        from app.editor.portrait_editor.new_portrait_tab import NewPortraitDatabase
        dialog = self.open(NewPortraitDatabase, 'portraits')
        dialog.show()
        QApplication.processEvents()
        portrait = RESOURCES.portraits[0]
        dialog.tab.tree_list.select_item(portrait.nid)
        offset = portrait.blinking_offset
        dialog.tab.right_frame.blinking_offset.edit.set_current(offset[0] + 1, offset[1])
        dialog.tab.right_frame.blinking_changed(offset[0] + 1, offset[1])
        dialog.tab.tree_list.tree_widget.setFocus()
        QApplication.setActiveWindow(dialog)
        QApplication.processEvents()

        QTest.keyClick(QApplication.focusWidget(), Qt.Key_Z, Qt.ControlModifier)

        self.assertEqual(tuple(offset), tuple(portrait.blinking_offset))


if __name__ == '__main__':
    import unittest
    unittest.main()
