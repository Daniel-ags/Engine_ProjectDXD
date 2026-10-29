import logging
import os
import unittest
from unittest.mock import patch

from app.tests import qt_headless  # noqa: F401 -- before any QApplication

from PyQt5.QtCore import QEvent
from PyQt5.QtWidgets import QApplication

from app.data.database.database import DB
from app.data.resources.resources import RESOURCES
from app.data.serialization.versions import CURRENT_SERIALIZATION_VERSION


def settle():
    QApplication.processEvents()
    # A window closed is deleted once the event loop gets back to it
    QApplication.sendPostedEvents(None, QEvent.DeferredDelete)


def show_every_record(tab, after_each=lambda: None) -> int:
    """Selects each record of the tab in turn, as a user clicking down its list would,
    calling after_each once each is shown. Returns how many it showed."""
    from app.editor.constant_tab import ConstantDatabase
    from app.editor.support_editor.support_constants_tab import SupportConstantDatabase
    if isinstance(tab, (ConstantDatabase, SupportConstantDatabase)):
        after_each()
        return len(tab._data)  # Shown all at once as the tab opens
    shown = 0
    if hasattr(tab, 'tree_list'):
        for record in list(tab.data):
            tab.tree_list.select_item(record.nid)
            settle()
            after_each()
            shown += 1
        return shown
    view = tab.left_frame.view if hasattr(tab, 'left_frame') else tab.view
    for row in range(view.model().rowCount()):
        view.setCurrentIndex(view.model().index(row, 0))
        settle()
        after_each()
        shown += 1
    return shown


class EditorWindowsCase(unittest.TestCase):
    """Opens the editor windows of the main window on project"""
    project = 'testing_proj.ltproj'

    @classmethod
    def setUpClass(cls):
        import sys
        from app.editor.editor_locale import init_locale
        init_locale()
        cls.app = QApplication.instance() or QApplication(sys.argv)

    def setUp(self):
        from app.editor.edit_history import HISTORY
        from app.editor.settings import MainSettingsController
        logging.disable(logging.CRITICAL)
        self.addCleanup(logging.disable, logging.NOTSET)
        for patcher in (patch.object(MainSettingsController, 'get_current_project', lambda _: self.project),
                        # A message box would wait forever for someone to close it
                        patch('PyQt5.QtWidgets.QMessageBox.critical'),
                        patch('PyQt5.QtWidgets.QMessageBox.warning'),
                        patch('PyQt5.QtWidgets.QMessageBox.information')):
            patcher.start()
            self.addCleanup(patcher.stop)
        RESOURCES.load(self.project, CURRENT_SERIALIZATION_VERSION)
        DB.load(self.project, CURRENT_SERIALIZATION_VERSION)
        HISTORY.clear()
        self.history = HISTORY

    def windows(self) -> dict:
        """Each editor window the main window opens, by its menu name"""
        from app.editor import main_editor as m
        return {
            'Units': m.NewUnitDatabase.edit, 'Teams': m.TeamDatabase.edit, 'Factions': m.FactionDatabase.edit,
            'Parties': m.PartyDatabase.edit, 'Classes': m.NewClassDatabase.edit, 'Weapon Types': m.WeaponDatabase.edit,
            'Items': m.NewItemDatabase.edit, 'Skills': m.NewSkillDatabase.edit, 'AI': m.AIDatabase.edit,
            'Terrain': m.TerrainDatabase.edit, 'Stats': m.StatTypeDatabase.edit, 'Constants': m.ConstantDatabase.edit,
            'Difficulty Modes': m.DifficultyModeDatabase.edit, 'Supports': m.support_pair_tab.get_full_editor,
            'Lore': m.NewLoreDatabase.edit, 'Raw Data': m.RawDataDatabase.edit, 'Credit': m.NewCreditDatabase.edit,
            'Icons': m.icon_tab.get_full_editor, 'Portraits': m.NewPortraitDatabase.edit,
            'Map Animations': m.MapAnimationDatabase.edit, 'Backgrounds': m.PanoramaDatabase.edit,
            'Map Sprites': m.NewMapSpriteDatabase.edit, 'Combat Animations': m.new_combat_animation_tab.get_full_editor,
            'Tilemaps': m.tile_tab.get_full_editor, 'Sounds': m.sound_tab.get_full_editor, 'Fonts': m.FontDatabase.edit,
        }


class ShowingChangesNothingCase(EditorWindowsCase):
    """Every editor window the main window opens shows each of its records without
    changing anything. A change made by showing is never recorded, so undo never
    takes it back, and the next window to commit records it as its own edit."""
    def snapshot(self) -> dict:
        from app.editor.edit_history import saved
        records = {id(record): ('%s %s' % (type(record).__name__, record.nid), saved(record))
                   for data in self.history.watched_catalogs() for record in data}
        records['mcost'] = ('the movement cost grid', DB.mcost.save())
        return records

    def test_showing_every_record_in_every_editor_window_changes_nothing(self):
        for name, make in self.windows().items():
            with self.subTest(name):
                before = self.snapshot()
                steps = len(self.history._undo)
                window = make(None)
                window.show()
                settle()
                for tab in window.history_tabs():
                    show_every_record(tab)
                window.close()
                settle()
                self.history.commit()

                after = self.snapshot()
                changed = [label for key, (label, form) in after.items() if key in before and before[key][1] != form]
                self.assertEqual([], changed)
                self.assertEqual(steps, len(self.history._undo))


@unittest.skipUnless(os.environ.get('LT_SLOW_TESTS'), "a slow test: set LT_SLOW_TESTS=1, or run_tests_parallel.py --slow")
class ShowingChangesNothingInTheSampleProjectTests(ShowingChangesNothingCase):
    project = 'default.ltproj'


class ShowingChangesNothingTests(ShowingChangesNothingCase):
    pass


del ShowingChangesNothingCase  # Its subclasses run its test, each on its project


class MapReadsCase(EditorWindowsCase):
    """An editor window leaves its tab as it is after an edit to the fields of the main
    window's maps, unless the tab says it reads them (reads_maps). So every tab that
    reads a level, overworld or tilemap as it shows the database again, shows each of
    its records and draws them must say so. What a window reads only as it opens, it
    would not show again anyway. A read of a nid is left out: a rename always shows."""
    def events_window(self, parent):
        from types import SimpleNamespace
        from PyQt5.QtWidgets import QWidget
        from app.editor.event_editor.event_tab import EventDatabase
        from app.editor.settings import MainSettingsController
        # The event editor reaches back to the main editor for the selected level
        main_editor = QWidget()
        self.addCleanup(main_editor.deleteLater)
        main_editor.app_state_manager = SimpleNamespace(state=SimpleNamespace(selected_level=DB.levels[0].nid))
        with patch('app.editor.event_editor.event_properties.MainSettingsController',
                   lambda: MainSettingsController('lt_maker_tests', 'editor_show')):
            return EventDatabase.edit(main_editor)

    def test_every_tab_reading_maps_says_so(self):
        from app.data.database.levels import LevelPrefab
        from app.data.database.overworld import OverworldPrefab
        from app.data.resources.tiles import TileMapPrefab
        from app.editor import timer
        # A tick redraws by itself, without showing the database again
        timer.get_timer().main_timer.stop()
        self.addCleanup(timer.get_timer().main_timer.start)
        reads = None  # The reads of the tab being checked, while one is

        def counting(cls):
            original = cls.__getattribute__

            def __getattribute__(record, name):
                if reads is not None and name != 'nid' and not name.startswith('__'):
                    reads.add('%s.%s' % (cls.__name__, name))
                return original(record, name)
            return __getattribute__
        for cls in (LevelPrefab, OverworldPrefab, TileMapPrefab):
            patcher = patch.object(cls, '__getattribute__', counting(cls))
            patcher.start()
            self.addCleanup(patcher.stop)

        undeclared = {}
        for make in dict(self.windows(), Events=self.events_window).values():
            window = make(None)
            window.show()
            settle()
            for tab in window.history_tabs():
                reads = set()
                tab.reset()
                settle()
                tab.grab()
                show_every_record(tab, tab.grab)
                if reads and not tab.reads_maps:
                    undeclared[type(tab).__name__] = sorted(reads)
                reads = None
            window.close()
            settle()
        self.assertEqual({}, undeclared)

    def test_the_check_on_a_skipped_tab_reads_every_tab(self):
        """LT_EDITOR_CHECK compares what a tab shows before and after showing the
        database again, which it can read in every tab, the same each time"""
        from app.editor.data_editor import widget_state
        for name, make in dict(self.windows(), Events=self.events_window).items():
            window = make(None)
            window.show()
            settle()
            for tab in window.history_tabs():
                with self.subTest(name, tab=type(tab).__name__):
                    self.assertEqual(widget_state(tab), widget_state(tab))
            window.close()
            settle()


class MapReadsTests(MapReadsCase):
    pass


@unittest.skipUnless(os.environ.get('LT_SLOW_TESTS'), "a slow test: set LT_SLOW_TESTS=1, or run_tests_parallel.py --slow")
class MapReadsInTheSampleProjectTests(MapReadsCase):
    # Its events check their commands against their levels' units and regions
    project = 'default.ltproj'


del MapReadsCase


if __name__ == '__main__':
    unittest.main()
