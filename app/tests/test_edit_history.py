import logging
import unittest
from unittest.mock import patch

from app.data.database.database import DB
from app.data.database.database_types import DatabaseType as DType
from app.data.database.items import ItemPrefab
from app.data.serialization.versions import CURRENT_SERIALIZATION_VERSION
from app.editor import edit_history
from app.editor.edit_history import HISTORY, MAX_CHANGE_SETS

# testing_proj level 0 holds the unique units Eirika and Seth and the generic unit 101
UNIT = 'Eirika'
ITEM = 'Iron_Sword'
NEW = 'Renamed'


class HistoryTestCase(unittest.TestCase):
    def setUp(self):
        logging.disable(logging.CRITICAL)
        self.addCleanup(logging.disable, logging.NOTSET)
        DB.load('testing_proj.ltproj', CURRENT_SERIALIZATION_VERSION)
        HISTORY.clear()
        self.unit = DB.units.get(UNIT)
        self.unit.starting_items = [[ITEM, False]]
        HISTORY.bind(self.unit, DB.units)


class ModifyTests(HistoryTestCase):
    def test_undo_restores_fields_in_place_and_redo_reapplies_them(self):
        self.unit.name = 'Somebody Else'
        self.unit.bases['HP'] = 99
        HISTORY.commit()

        HISTORY.undo()
        self.assertIs(self.unit, DB.units.get(UNIT))
        self.assertEqual(UNIT, self.unit.name)
        self.assertNotEqual(99, self.unit.bases['HP'])

        HISTORY.redo()
        self.assertIs(self.unit, DB.units.get(UNIT))
        self.assertEqual('Somebody Else', self.unit.name)
        self.assertEqual(99, self.unit.bases['HP'])

    def test_nothing_changed_records_nothing(self):
        HISTORY.commit()
        self.assertFalse(HISTORY.can_undo())

    def test_each_commit_is_its_own_step(self):
        self.unit.name = 'One'
        HISTORY.commit()
        self.unit.name = 'Two'
        HISTORY.commit()
        HISTORY.undo()
        self.assertEqual('One', self.unit.name)
        HISTORY.undo()
        self.assertEqual(UNIT, self.unit.name)

    def test_undo_does_not_record_itself(self):
        self.unit.name = 'One'
        HISTORY.commit()
        HISTORY.undo()
        HISTORY.commit()
        self.assertFalse(HISTORY.can_undo())
        self.assertTrue(HISTORY.can_redo())

    def test_a_new_edit_drops_what_could_be_redone(self):
        self.unit.name = 'One'
        HISTORY.commit()
        HISTORY.undo()
        self.unit.desc = 'Changed'
        HISTORY.commit()
        self.assertFalse(HISTORY.can_redo())

    def test_constants_restore_their_value(self):
        constant = DB.constants.get('num_items')
        HISTORY.bind(constant, DB.constants)
        constant.value = 12
        HISTORY.commit()
        HISTORY.undo()
        self.assertEqual(5, constant.value)


class MembershipTests(HistoryTestCase):
    def test_creating_is_undone_and_redone_with_the_same_object(self):
        item = ItemPrefab('New_Item', 'New Item', '')
        DB.items.append(item)
        HISTORY.commit()

        HISTORY.undo()
        self.assertNotIn('New_Item', DB.items)
        HISTORY.redo()
        self.assertIs(item, DB.items.get('New_Item'))

    def test_reordering_is_undone(self):
        order = DB.items.keys()
        DB.items.move_index(0, 3)
        HISTORY.commit()
        HISTORY.undo()
        self.assertEqual(order, DB.items.keys())

    def test_categories_are_restored_in_place(self):
        categories = DB.items.categories
        before = dict(categories)
        categories[ITEM] = ['Somewhere', 'Else']
        HISTORY.commit()
        HISTORY.undo()
        self.assertIs(categories, DB.items.categories)
        self.assertEqual(before, dict(categories))


class CascadeTests(HistoryTestCase):
    def test_deleting_with_its_cascade_is_one_step(self):
        item = DB.items.get(ITEM)
        level_unit = DB.levels.get('0').units.get('101')
        level_unit.starting_items = [[ITEM, True]]
        with HISTORY.change_set('Delete'):
            HISTORY.clear_references(DType.ITEMS, ITEM)
            DB.items.remove_key(ITEM)
        self.assertEqual([], self.unit.starting_items)

        HISTORY.undo()
        self.assertIs(item, DB.items.get(ITEM))
        self.assertEqual([[ITEM, False]], self.unit.starting_items)
        self.assertEqual([[ITEM, True]], DB.levels.get('0').units.get('101').starting_items)
        self.assertFalse(HISTORY.can_undo())

    def test_renaming_with_its_cascade_is_one_step(self):
        item = DB.items.get(ITEM)
        with HISTORY.change_set('Rename'), HISTORY.modifying([(item, DB.items)]):
            HISTORY.rewrite(DType.ITEMS, ITEM, NEW)
            DB.items.change_key(ITEM, NEW)

        HISTORY.undo()
        self.assertIs(item, DB.items.get(ITEM))
        self.assertNotIn(NEW, DB.items)
        self.assertEqual([[ITEM, False]], self.unit.starting_items)

        HISTORY.redo()
        self.assertIs(item, DB.items.get(NEW))
        self.assertEqual([[NEW, False]], self.unit.starting_items)

    def test_renaming_a_level_rekeys_its_events_on_undo(self):
        event = DB.events.create_new(DB, '0')
        HISTORY.commit()
        HISTORY.rewrite(DType.LEVELS, '0', NEW)
        self.assertIs(event, DB.events.get_from_nid(NEW + ' ' + event.name))

        HISTORY.undo()
        self.assertEqual('0', event.level_nid)
        self.assertIs(event, DB.events.get_from_nid('0 ' + event.name))


class MarkTests(HistoryTestCase):
    def test_undo_to_mark_undoes_everything_since_and_forgets_it(self):
        self.unit.name = 'Before'
        mark = HISTORY.mark()
        self.unit.name = 'After'
        DB.items.append(ItemPrefab('New_Item', 'New Item', ''))
        HISTORY.commit()
        self.unit.desc = 'Still uncommitted'

        HISTORY.undo_to(mark)

        self.assertEqual('Before', self.unit.name)
        self.assertNotEqual('Still uncommitted', self.unit.desc)
        self.assertNotIn('New_Item', DB.items)
        self.assertFalse(HISTORY.can_redo())

    def test_undo_to_a_mark_already_undone_redoes_up_to_it(self):
        self.unit.name = 'Before'
        mark = HISTORY.mark()
        self.unit.name = 'After'
        HISTORY.commit()
        HISTORY.undo()
        HISTORY.undo()
        self.assertEqual(UNIT, self.unit.name)

        HISTORY.undo_to(mark)

        self.assertEqual('Before', self.unit.name)
        self.assertFalse(HISTORY.can_redo())

    def test_history_keeps_its_last_hundred_steps(self):
        for idx in range(MAX_CHANGE_SETS + 5):
            self.unit.name = str(idx)
            HISTORY.commit()
        steps = 0
        while HISTORY.undo():
            steps += 1
        self.assertEqual(MAX_CHANGE_SETS, steps)
        self.assertEqual('4', self.unit.name)


class UnrecordedChangeTests(HistoryTestCase):
    def test_the_check_names_a_record_changed_behind_its_back(self):
        with patch.object(edit_history, 'CHECK_UNRECORDED', True):
            HISTORY.clear()
            HISTORY.bind(self.unit, DB.units)
            DB.classes[0].desc = 'Changed by nobody'
            with self.assertLogs(level='WARNING') as logs:
                logging.disable(logging.NOTSET)
                self.unit.name = 'Recorded'
                HISTORY.commit()
        self.assertEqual(1, len(logs.output))
        self.assertIn(DB.classes[0].nid, logs.output[0])


if __name__ == '__main__':
    unittest.main()
