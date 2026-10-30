import logging
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.tests import qt_headless  # noqa: F401 -- before any QApplication

from PyQt5.QtWidgets import QApplication

from app.data.database.database import DB
from app.data.resources.resources import RESOURCES
from app.data.serialization.versions import CURRENT_SERIALIZATION_VERSION


class MapEditCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import sys
        from app.editor.editor_locale import init_locale
        init_locale()
        cls.app = QApplication.instance() or QApplication(sys.argv)

    def setUp(self):
        from app.editor.edit_history import HISTORY
        logging.disable(logging.CRITICAL)
        self.addCleanup(logging.disable, logging.NOTSET)
        DB.load('testing_proj.ltproj', CURRENT_SERIALIZATION_VERSION)
        RESOURCES.load('testing_proj.ltproj', CURRENT_SERIALIZATION_VERSION)
        HISTORY.clear()
        self.history = HISTORY
        self.level = next(level for level in DB.levels if level.units)
        # The main window's level editor, which binds the level it shows
        self.main_window = object()
        self.history.bind(self.level, DB.levels, self.main_window)
        self.addCleanup(self.history.unbind, self.main_window)

    def move_unit(self):
        """A unit moved on the main window's map, the click's release committing it"""
        unit = self.level.units[0]
        x, y = unit.starting_position or (0, 0)
        unit.starting_position = (x, y + 1)
        self.history.commit(origin=self.main_window)
        return self.history.last_change()


class ChangeSetTests(MapEditCase):
    """Which change sets only edit the fields of the main window's maps"""
    def only_maps(self, change_set) -> bool:
        from app.editor.data_editor import map_catalogs
        return change_set.only_edits_fields_of(map_catalogs())

    def test_a_unit_moved_on_the_map_only_edits_a_level(self):
        self.assertTrue(self.only_maps(self.move_unit()))

    def test_a_unit_added_to_a_level_only_edits_a_level(self):
        from app.data.database.level_units import GenericUnit
        unit = GenericUnit('Added', None, 1, DB.classes[0].nid, DB.factions[0].nid,
                           [], [], 'player', DB.ai[0].nid)
        self.level.units.append(unit)
        self.history.commit(origin=self.main_window)
        self.assertTrue(self.only_maps(self.history.last_change()))

    def test_a_level_renamed_is_more(self):
        self.level.nid = 'Renamed'
        self.history.commit(origin=self.main_window)
        self.assertFalse(self.only_maps(self.history.last_change()))

    def test_a_level_added_is_more(self):
        from app.data.database.levels import LevelPrefab
        DB.levels.append(LevelPrefab('New_Level', 'New Level'))
        self.history.commit(origin=self.main_window)
        self.assertFalse(self.only_maps(self.history.last_change()))

    def test_an_item_edited_alongside_is_more(self):
        item = DB.items[0]
        with self.history.modifying([(item, DB.items)]):
            item.desc = 'Changed'
            self.level.units[0].starting_position = (5, 5)
        self.assertFalse(self.only_maps(self.history.last_change()))

    def test_undoing_a_map_edit_hands_on_what_it_undid(self):
        heard = []
        self.history.listen(lambda origin, change_set: heard.append((origin, change_set)))
        moved = self.move_unit()
        self.history.undo()
        origin, change_set = heard[-1]
        self.assertIsNone(origin)
        self.assertIs(moved, change_set)
        self.assertTrue(self.only_maps(change_set))


class WindowTests(MapEditCase):
    """An editor window leaves its tab as it is after a map edit, unless the tab
    reads maps, and shows the database again after any other change"""
    def open(self, tab_type, parent=None):
        from app.editor.data_editor import SingleDatabaseEditor
        dialog = SingleDatabaseEditor(tab_type, parent)
        self.addCleanup(dialog.stop_history)
        self.addCleanup(dialog.hide)
        QApplication.processEvents()
        return dialog

    def resets(self, dialog, change) -> int:
        with patch.object(dialog.tab, 'reset') as reset:
            change()
            QApplication.processEvents()  # The window shows changes once the event making them is done
        return reset.call_count

    def test_a_map_edit_leaves_the_items_window_alone(self):
        from app.editor.item_editor.new_item_tab import NewItemDatabase
        items = self.open(NewItemDatabase)
        self.assertEqual(0, self.resets(items, self.move_unit))

    def test_undoing_a_map_edit_leaves_the_items_window_alone(self):
        from app.editor.item_editor.new_item_tab import NewItemDatabase
        items = self.open(NewItemDatabase)
        self.move_unit()
        QApplication.processEvents()
        self.assertEqual(0, self.resets(items, self.history.undo))

    def test_an_item_edit_elsewhere_shows_in_the_items_window(self):
        from app.editor.item_editor.new_item_tab import NewItemDatabase
        items = self.open(NewItemDatabase)
        item = DB.items[1]

        def edit_item():
            with self.history.modifying([(item, DB.items)]):
                item.desc = 'Changed'
        self.assertEqual(1, self.resets(items, edit_item))

    def open_events(self, event):
        """The events window, showing event"""
        from PyQt5.QtWidgets import QWidget
        from app.editor.event_editor.event_tab import EventDatabase
        from app.editor.settings import MainSettingsController
        # The event editor reaches back to the main editor for the selected level
        main_editor = QWidget()
        self.addCleanup(main_editor.deleteLater)
        main_editor.app_state_manager = SimpleNamespace(state=SimpleNamespace(selected_level=self.level.nid))
        with patch('app.editor.event_editor.event_properties.MainSettingsController',
                   lambda: MainSettingsController('lt_maker_tests', 'map_edit_skips')):
            events = self.open(EventDatabase, main_editor)
        events.tab.left_frame.filter_to_level_of(event)
        events.tab.left_frame.view.setCurrentIndex(events.tab.view_index_of(event))
        self.assertIs(event, events.tab.right_frame.current)
        return events

    def test_a_map_edit_to_the_shown_events_level_shows_in_the_events_window(self):
        event = next(event for event in DB.events if event.level_nid)
        level = DB.levels.get(event.level_nid)
        events = self.open_events(event)

        def rename_level():
            with self.history.modifying([(level, DB.levels)]):
                level.name = 'Changed'
        self.assertEqual(1, self.resets(events, rename_level))

    def test_a_map_edit_to_the_shown_events_tilemap_shows_in_the_events_window(self):
        event = next(event for event in DB.events if event.level_nid)
        tilemap = RESOURCES.tilemaps.get(DB.levels.get(event.level_nid).tilemap)
        events = self.open_events(event)

        def resize_tilemap():
            with self.history.modifying([(tilemap, RESOURCES.tilemaps)]):
                tilemap.width += 1
        self.assertEqual(1, self.resets(events, resize_tilemap))

    def test_a_map_edit_to_another_level_leaves_the_events_window_alone(self):
        event = next(event for event in DB.events if event.level_nid and event.level_nid != self.level.nid)
        events = self.open_events(event)
        self.assertEqual(0, self.resets(events, self.move_unit))

    def test_a_map_edit_leaves_the_events_window_showing_a_global_event_alone(self):
        event = next(event for event in DB.events if not event.level_nid)
        events = self.open_events(event)
        self.assertEqual(0, self.resets(events, self.move_unit))

    def test_an_overworld_edit_shows_in_the_events_window(self):
        # Its script's overworld nodes are checked against every overworld
        event = next(event for event in DB.events if not event.level_nid)
        overworld = DB.overworlds[0]
        events = self.open_events(event)

        def rename_overworld():
            with self.history.modifying([(overworld, DB.overworlds)]):
                overworld.name = 'Changed'
        self.assertEqual(1, self.resets(events, rename_overworld))

    def test_the_check_reports_a_tab_left_showing_something_else(self):
        from app.editor import data_editor
        from app.editor.item_editor.new_item_tab import NewItemDatabase
        items = self.open(NewItemDatabase)
        logging.disable(logging.NOTSET)
        # As though the level's units showed in the item form
        unit = self.level.units[0]
        reset = items.tab.reset
        name_box = items.tab.right_frame.name_box.edit

        def reset_showing_the_unit():
            reset()
            name_box.setText(str(unit.starting_position))
        with patch.object(data_editor, 'CHECK_UNRECORDED', True), \
                patch.object(items.tab, 'reset', reset_showing_the_unit), \
                self.assertLogs(level='WARNING') as logs:
            self.move_unit()
            QApplication.processEvents()
        self.assertIn('NewItemDatabase', '\n'.join(logs.output))


if __name__ == '__main__':
    unittest.main()
