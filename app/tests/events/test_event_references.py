import logging
import unittest

from app.data.database.database import DB
from app.data.database.database_types import DatabaseType as DType
from app.data.resources.resource_types import ResourceType as RType
from app.data.serialization.versions import CURRENT_SERIALIZATION_VERSION
from app.events.event_prefab import EventPrefab
from app.events.event_references import CONDITION_LINE, find_mentions

# testing_proj's own events name Eirika in level 1's New Event, and nothing else below


class EventMentionTests(unittest.TestCase):
    def setUp(self):
        logging.disable(logging.CRITICAL)
        self.addCleanup(logging.disable, logging.NOTSET)
        DB.load('testing_proj.ltproj', CURRENT_SERIALIZATION_VERSION)

    def event(self, name, *lines, condition='True'):
        event = EventPrefab(name)
        event.level_nid = '0'
        event.source = '\n'.join(lines)
        event.condition = condition
        DB.events.append(event)
        return event

    def mentions(self, target, nid, event='0 Script'):
        """Each line of the event naming nid, as (line, certain)"""
        return [(m.line, m.certain) for m in find_mentions(DB, target, nid) if m.event == event]

    def test_a_command_argument_of_the_target_kind_is_a_certain_mention(self):
        self.event('Script', 'give_item;Eirika;Iron_Sword', 'give_item;Seth;Slim_Sword')

        self.assertEqual([(1, True)], self.mentions(DType.ITEMS, 'Iron_Sword'))
        self.assertEqual([(1, True)], self.mentions(DType.UNITS, 'Eirika'))

    def test_fonts_overworlds_and_overworld_entities_are_certain_mentions(self):
        self.event('Script', 'textbox;Box;Hello;FontType=convo', 'overworld_cinematic;Magvel',
                   'overworld_move_unit;Eirika_Party')

        self.assertEqual([(1, True)], self.mentions(RType.FONTS, 'convo'))
        self.assertEqual([(2, True)], self.mentions(DType.OVERWORLDS, 'Magvel'))
        self.assertEqual([(3, True)], self.mentions(DType.PARTIES, 'Eirika_Party'))

    def test_an_argument_of_another_kind_is_no_mention(self):
        # A unit and a portrait share Eirika's nid; change_music takes neither
        self.event('Script', 'give_item;Eirika;Iron_Sword', 'change_music;player_phase;Eirika')

        self.assertEqual([], self.mentions(RType.PORTRAITS, 'Eirika'))
        self.assertEqual([], self.mentions(DType.ITEMS, 'Eirika'))

    def test_an_argument_naming_several_kinds_mentions_each(self):
        self.event('Script', 'add_portrait;Eirika;Left')

        self.assertEqual([(1, True)], self.mentions(DType.UNITS, 'Eirika'))
        self.assertEqual([(1, True)], self.mentions(RType.PORTRAITS, 'Eirika'))

    def test_list_arguments_are_read_entry_by_entry(self):
        self.event('Script', 'shop;{unit};Slim_Sword,Iron_Sword', 'change_stats;Eirika;STR,2,DEF,-1')

        self.assertEqual([(1, True)], self.mentions(DType.ITEMS, 'Iron_Sword'))
        self.assertEqual([(2, True)], self.mentions(DType.STATS, 'DEF'))
        # A stat change's value is not a stat
        self.assertEqual([], self.mentions(DType.STATS, '2'))

    def test_a_quoted_string_may_name_it(self):
        self.event('Script', "if;has_item('Iron_Sword')", 'speak;Seth;I carry an Iron_Sword', 'end')

        # The speech is text, not a quoted name
        self.assertEqual([(1, False)], self.mentions(DType.ITEMS, 'Iron_Sword'))

    def test_a_quoted_string_must_be_the_whole_name(self):
        self.event('Script', "if;has_item('Iron_Sword_2')")

        self.assertEqual([], self.mentions(DType.ITEMS, 'Iron_Sword'))

    def test_a_python_event_command_line_is_read_like_a_classic_one(self):
        self.event('Script', '#pyev1', '$give_item "Eirika" "Iron_Sword"', 'sword = "Iron_Sword"', '$give_item "Seth" sword')

        self.assertEqual([(2, True), (3, False)], self.mentions(DType.ITEMS, 'Iron_Sword'))

    def test_the_trigger_condition_may_name_it(self):
        self.event('Script', 'end', condition="game.get_unit('Seth')")

        self.assertEqual([(CONDITION_LINE, False)], self.mentions(DType.UNITS, 'Seth'))

    def test_an_event_is_named_by_its_nid_or_its_name(self):
        self.event('Called', 'end')
        self.event('Script', 'trigger_script;Called', 'trigger_script;0 Called', 'trigger_script;Other')

        self.assertEqual([(1, True), (2, True)], self.mentions(DType.EVENTS, '0 Called'))

    def test_a_mention_says_where_it_is(self):
        self.event('Script', 'end', "if;has_item('Iron_Sword')")

        labels = [m.label() for m in find_mentions(DB, DType.ITEMS, 'Iron_Sword')]
        self.assertEqual(["0 Script, line 2: if;has_item('Iron_Sword')  (may name it)"], labels)


if __name__ == '__main__':
    unittest.main()
