import logging
import unittest
from unittest.mock import patch

from app.tests import qt_headless  # noqa: F401 -- before any QApplication

from app.data.database.database import DB
from app.data.database.database_types import DatabaseType as DType
from app.data.database.parties import PartyPrefab
from app.data.database.weapons import WeaponType, WexpGain
from app.data.resources.resources import RESOURCES
from app.data.serialization.versions import CURRENT_SERIALIZATION_VERSION
from app.editor import reference_dialogs
from app.editor.custom_widgets import ItemBox, WeaponTypeBox
from app.extensions.custom_gui import DeletionDialog

UNIT = 'Eirika'
ITEM = 'Iron_Sword'
SWAP = 'Vulnerary'


class DialogTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import sys
        from app.editor.editor_locale import init_locale
        init_locale()
        from PyQt5.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication(sys.argv)

    def setUp(self):
        logging.disable(logging.CRITICAL)
        self.addCleanup(logging.disable, logging.NOTSET)
        DB.load('testing_proj.ltproj', CURRENT_SERIALIZATION_VERSION)
        RESOURCES.load('testing_proj.ltproj', CURRENT_SERIALIZATION_VERSION)
        DB.units.get(UNIT).starting_items = [[ITEM, False]]

    def patch_dialog(self, name, result):
        dialog = patch.object(DeletionDialog, name, return_value=result)
        mock = dialog.start()
        self.addCleanup(dialog.stop)
        return mock



class CheckDeleteTests(DialogTestCase):
    def item_box(self):
        return ItemBox(None, exclude=DB.items.get(ITEM))

    def test_a_swap_points_references_at_the_chosen_record(self):
        get_swap = self.patch_dialog('get_swap', (DB.items.get(SWAP), True))

        ok = reference_dialogs.check_delete(DType.ITEMS, ITEM, 'Item', None, self.item_box)

        self.assertTrue(ok)
        tabs = get_swap.call_args[0][0]
        self.assertIn('Units', [tab.label for tab in tabs])
        self.assertEqual([[SWAP, False]], DB.units.get(UNIT).starting_items)

    def test_cancelling_changes_nothing(self):
        self.patch_dialog('get_swap', (None, False))

        ok = reference_dialogs.check_delete(DType.ITEMS, ITEM, 'Item', None, self.item_box)

        self.assertFalse(ok)
        self.assertEqual([[ITEM, False]], DB.units.get(UNIT).starting_items)

    def test_without_a_swap_references_are_removed_and_required_ones_take_the_fallback(self):
        self.patch_dialog('inform', True)
        DB.parties.append(PartyPrefab('Party', 'Party', UNIT))

        ok = reference_dialogs.check_delete(DType.UNITS, UNIT, 'Unit', None, fallback='Seth')

        self.assertTrue(ok)
        self.assertNotIn(UNIT, DB.levels.get('0').units)
        self.assertEqual('Seth', DB.parties.get('Party').leader)

    def test_per_record_entries_alone_do_not_ask(self):
        get_swap = self.patch_dialog('get_swap', (None, False))
        weapon = WeaponType('Unused', 'Unused')
        DB.weapons.append(weapon)
        for klass in DB.classes:
            klass.wexp_gain[weapon.nid] = WexpGain(True, 5)

        ok = reference_dialogs.check_delete(DType.WEAPONS, weapon.nid, 'Weapon Type', None,
                                            lambda: WeaponTypeBox(None, exclude=weapon))

        self.assertTrue(ok)
        get_swap.assert_not_called()
        self.assertFalse(any(weapon.nid in klass.wexp_gain for klass in DB.classes))


class EventMentionTests(DialogTestCase):
    """Event scripts are not rewritten: a deletion lists their lines, and a rename tells the user"""
    def event(self, *lines):
        from app.events.event_prefab import EventPrefab
        event = EventPrefab('Script')
        event.source = '\n'.join(lines)
        DB.events.append(event)
        return event

    def item_box(self):
        return ItemBox(None, exclude=DB.items.get(ITEM))

    def record_renames(self) -> list:
        from app.editor.edit_history import HISTORY
        renames = []
        listener = lambda target, old, new: renames.append((target, old, new))
        HISTORY.listen_to_renames(listener)
        self.addCleanup(HISTORY.unlisten_to_renames, listener)
        return renames

    def test_a_deletion_lists_the_event_lines_naming_it_and_leaves_them(self):
        get_swap = self.patch_dialog('get_swap', (DB.items.get(SWAP), True))
        event = self.event('give_item;Eirika;%s' % ITEM)

        reference_dialogs.check_delete(DType.ITEMS, ITEM, 'Item', None, self.item_box)

        events_tab = next(tab for tab in get_swap.call_args[0][0] if tab.label == 'Events')
        self.assertEqual(['Global Script, line 1: give_item;Eirika;%s' % ITEM],
                         [mention.label() for mention in events_tab.affected_items])
        self.assertIn('does not change event scripts', events_tab.msg)
        self.assertEqual('give_item;Eirika;%s' % ITEM, event.source)

    def test_a_record_only_events_name_still_warns_before_its_deletion(self):
        from app.data.database.items import ItemPrefab
        DB.items.append(ItemPrefab('Lonely', 'Lonely', ''))
        self.event('give_item;Eirika;Lonely')
        inform = self.patch_dialog('inform', False)
        get_swap = self.patch_dialog('get_swap', (None, False))

        ok = reference_dialogs.check_delete(DType.ITEMS, 'Lonely', 'Item', None, self.item_box)

        self.assertFalse(ok)
        get_swap.assert_not_called()
        self.assertEqual(['Events'], [tab.label for tab in inform.call_args[0][0]])

    def test_a_rename_is_heard_but_a_deletions_swap_is_not(self):
        from app.editor.edit_history import HISTORY
        renames = self.record_renames()
        self.patch_dialog('get_swap', (DB.items.get(SWAP), True))

        HISTORY.rewrite(DType.ITEMS, ITEM, 'Renamed')
        reference_dialogs.check_delete(DType.ITEMS, 'Renamed', 'Item', None, self.item_box)

        self.assertEqual([(DType.ITEMS, ITEM, 'Renamed')], renames)

    def shown_warnings(self) -> list:
        from PyQt5.QtWidgets import QApplication
        return [w for w in QApplication.topLevelWidgets()
                if isinstance(w, reference_dialogs.RenameWarning) and w.isVisible()]

    def test_a_rename_warns_of_the_event_lines_still_naming_the_old_nid(self):
        from PyQt5.QtCore import Qt
        from PyQt5.QtWidgets import QApplication
        self.event('give_item;Eirika;%s' % ITEM)

        reference_dialogs.warn_of_event_mentions(DType.ITEMS, ITEM, 'Renamed')
        QApplication.processEvents()  # The warning waits for the rename's event to finish

        warnings = self.shown_warnings()
        self.assertEqual(1, len(warnings))
        self.addCleanup(warnings[0].close)
        self.assertIn('a rename does not change event scripts', warnings[0].label.text())
        model = warnings[0].view.model()
        self.assertEqual(['Global Script, line 1: give_item;Eirika;%s' % ITEM],
                         [model.data(model.index(row), Qt.DisplayRole) for row in range(model.rowCount())])
        self.assertFalse(warnings[0].isModal())

    def test_a_rename_no_event_names_shows_nothing(self):
        from PyQt5.QtWidgets import QApplication

        reference_dialogs.warn_of_event_mentions(DType.ITEMS, ITEM, 'Renamed')
        QApplication.processEvents()

        self.assertEqual([], self.shown_warnings())


class EditorTabTests(DialogTestCase):
    """The editor tabs reach the database through the reference schema"""
    def test_renaming_in_the_item_tab_reaches_units(self):
        from app.editor.item_editor.new_item_tab import NewItemDatabase
        tab = NewItemDatabase(None, DB)
        tab.rename(ITEM, 'Renamed')
        self.assertEqual([['Renamed', False]], DB.units.get(UNIT).starting_items)

    def terrain_model(self):
        from PyQt5.QtWidgets import QListView, QWidget
        from app.editor.terrain_editor.terrain_model import TerrainModel
        window = QWidget()
        self.addCleanup(window.deleteLater)
        window.view = QListView(window)
        return TerrainModel(DB.terrain, window)

    def test_renaming_a_terrain_renames_it_in_tilemaps_and_tilesets_as_one_undo_step(self):
        from app.editor.edit_history import HISTORY
        HISTORY.clear()
        layer = RESOURCES.tilemaps.get('Prologue').layers[0]
        tileset = RESOURCES.tilesets.get('Prologue')
        tileset.terrain_grid[(0, 0)] = '21'
        HISTORY.rebaseline()
        self.assertEqual('21', layer.terrain_grid[(7, 4)])

        HISTORY.rename(DB.terrain, DB.terrain.get('21'), 'Renamed', self.terrain_model().on_nid_changed)

        self.assertEqual('Renamed', layer.terrain_grid[(7, 4)])
        self.assertEqual('Renamed', tileset.terrain_grid[(0, 0)])
        HISTORY.undo()
        self.assertFalse(HISTORY.can_undo())
        self.assertEqual('21', RESOURCES.tilemaps.get('Prologue').layers[0].terrain_grid[(7, 4)])
        self.assertEqual('21', RESOURCES.tilesets.get('Prologue').terrain_grid[(0, 0)])

    def test_deleting_a_terrain_swaps_it_in_tilemaps_as_one_undo_step(self):
        from app.editor.edit_history import HISTORY
        HISTORY.clear()
        get_swap = self.patch_dialog('get_swap', (DB.terrain.get('1'), True))
        model = self.terrain_model()
        layer = RESOURCES.tilemaps.get('Prologue').layers[0]

        model.delete(DB.terrain.keys().index('21'))

        self.assertIn('Tilemaps', [tab.label for tab in get_swap.call_args[0][0]])
        self.assertNotIn('21', DB.terrain.keys())
        self.assertEqual('1', layer.terrain_grid[(7, 4)])
        HISTORY.undo()
        self.assertFalse(HISTORY.can_undo())
        self.assertIn('21', DB.terrain.keys())
        self.assertEqual('21', RESOURCES.tilemaps.get('Prologue').layers[0].terrain_grid[(7, 4)])

    def test_deleting_in_the_unit_tab_removes_it_from_levels(self):
        from app.editor.unit_editor.new_unit_tab import NewUnitDatabase
        self.patch_dialog('inform', True)
        tab = NewUnitDatabase(None, DB, RESOURCES)
        self.assertTrue(tab.delete_from_db(UNIT))
        self.assertNotIn(UNIT, DB.units)
        self.assertNotIn(UNIT, DB.levels.get('0').units)


if __name__ == '__main__':
    unittest.main()
