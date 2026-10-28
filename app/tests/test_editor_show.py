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


def show_every_record(tab) -> int:
    """Selects each record of the tab in turn, as a user clicking down its list would.
    Returns how many it showed."""
    from app.editor.constant_tab import ConstantDatabase
    from app.editor.support_editor.support_constants_tab import SupportConstantDatabase
    if isinstance(tab, (ConstantDatabase, SupportConstantDatabase)):
        return len(tab._data)  # Shown all at once as the tab opens
    shown = 0
    if hasattr(tab, 'tree_list'):
        for record in list(tab.data):
            tab.tree_list.select_item(record.nid)
            settle()
            shown += 1
        return shown
    view = tab.left_frame.view if hasattr(tab, 'left_frame') else tab.view
    for row in range(view.model().rowCount()):
        view.setCurrentIndex(view.model().index(row, 0))
        settle()
        shown += 1
    return shown


class ShowingChangesNothingCase(unittest.TestCase):
    """Every editor window the main window opens shows each of its records without
    changing anything. A change made by showing is never recorded, so undo never
    takes it back, and the next window to commit records it as its own edit."""
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

    def snapshot(self) -> dict:
        from app.editor.edit_history import saved
        records = {id(record): ('%s %s' % (type(record).__name__, record.nid), saved(record))
                   for data in self.history.watched_catalogs() for record in data}
        records['mcost'] = ('the movement cost grid', DB.mcost.save())
        return records

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


if __name__ == '__main__':
    unittest.main()
