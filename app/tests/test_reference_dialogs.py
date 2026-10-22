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

        ok = reference_dialogs.check_delete(DB, DType.ITEMS, ITEM, 'Item', None, self.item_box)

        self.assertTrue(ok)
        tabs = get_swap.call_args[0][0]
        self.assertIn('Units', [tab.label for tab in tabs])
        self.assertEqual([[SWAP, False]], DB.units.get(UNIT).starting_items)

    def test_cancelling_changes_nothing(self):
        self.patch_dialog('get_swap', (None, False))

        ok = reference_dialogs.check_delete(DB, DType.ITEMS, ITEM, 'Item', None, self.item_box)

        self.assertFalse(ok)
        self.assertEqual([[ITEM, False]], DB.units.get(UNIT).starting_items)

    def test_without_a_swap_references_are_removed_and_required_ones_take_the_fallback(self):
        self.patch_dialog('inform', True)
        DB.parties.append(PartyPrefab('Party', 'Party', UNIT))

        ok = reference_dialogs.check_delete(DB, DType.UNITS, UNIT, 'Unit', None, fallback='Seth')

        self.assertTrue(ok)
        self.assertNotIn(UNIT, DB.levels.get('0').units)
        self.assertEqual('Seth', DB.parties.get('Party').leader)

    def test_per_record_entries_alone_do_not_ask(self):
        get_swap = self.patch_dialog('get_swap', (None, False))
        weapon = WeaponType('Unused', 'Unused')
        DB.weapons.append(weapon)
        for klass in DB.classes:
            klass.wexp_gain[weapon.nid] = WexpGain(True, 5)

        ok = reference_dialogs.check_delete(DB, DType.WEAPONS, weapon.nid, 'Weapon Type', None,
                                       lambda: WeaponTypeBox(None, exclude=weapon))

        self.assertTrue(ok)
        get_swap.assert_not_called()
        self.assertFalse(any(weapon.nid in klass.wexp_gain for klass in DB.classes))


class EditorTabTests(DialogTestCase):
    """The editor tabs reach the database through the reference schema"""
    def test_renaming_in_the_item_tab_reaches_units(self):
        from app.editor.item_editor.new_item_tab import NewItemDatabase
        tab = NewItemDatabase(None, DB)
        tab.rename(ITEM, 'Renamed')
        self.assertEqual([['Renamed', False]], DB.units.get(UNIT).starting_items)

    def test_deleting_in_the_unit_tab_removes_it_from_levels(self):
        from app.editor.unit_editor.new_unit_tab import NewUnitDatabase
        self.patch_dialog('inform', True)
        tab = NewUnitDatabase(None, DB, RESOURCES)
        self.assertTrue(tab.delete_from_db(UNIT))
        self.assertNotIn(UNIT, DB.units)
        self.assertNotIn(UNIT, DB.levels.get('0').units)


if __name__ == '__main__':
    unittest.main()
