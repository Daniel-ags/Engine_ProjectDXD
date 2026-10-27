from enum import Enum
import inspect
import logging
import unittest

import app.engine.item_component_access as ICA
from app.data.database import references
from app.data.database.components import Component
from app.data.database.database import DB
from app.data.database.database_types import DatabaseType as DType
from app.data.database.level_units import UniqueUnit, UnitGroup
from app.data.database.parties import PartyPrefab
from app.data.database.reference_schema import SCHEMA
from app.data.database.units import UnitPrefab
from app.data.database.supports import SupportPair, SupportRankRequirementList
from app.data.resources.resource_types import ResourceType as RType
from app.data.resources.resources import RESOURCES
from app.data.serialization.versions import CURRENT_SERIALIZATION_VERSION
from app.events.event_prefab import EventPrefab
from app.events.regions import Region, RegionType
from app.utilities.data import Data

# testing_proj level 0 holds the unique units Eirika and Seth and the generic unit 101
LEVEL = '0'
UNIT = 'Eirika'
ITEM = 'Iron_Sword'
SKILL = 'Steal'
NEW = 'Renamed'

def blank(record_type):
    """A record of the type with only its constructor's defaults"""
    try:
        return record_type.default()
    except (AttributeError, TypeError):  # No default(), or one that needs arguments
        required = [p for p in inspect.signature(record_type).parameters.values()
                    if p.default is inspect.Parameter.empty]
        return record_type(*[None] * len(required))


class SchemaCompletenessTests(unittest.TestCase):
    def test_every_field_of_every_record_type_is_in_the_schema(self):
        problems = []
        for record_type in SCHEMA:
            problems += references.schema_problems(record_type, vars(blank(record_type)))
        self.assertEqual([], problems, '\n' + '\n'.join(problems))

    def test_a_new_field_is_named_with_where_to_declare_it(self):
        fields = list(vars(blank(UnitPrefab))) + ['signature_item']
        problems = references.schema_problems(UnitPrefab, fields)
        self.assertEqual(1, len(problems))
        self.assertIn('UnitPrefab.signature_item', problems[0])
        self.assertIn(references.SCHEMA_FILE, problems[0])

    def test_the_sample_projects_match_the_schema(self):
        logging.disable(logging.CRITICAL)
        self.addCleanup(logging.disable, logging.NOTSET)
        for project in ('default.ltproj', 'testing_proj.ltproj'):
            DB.load(project, CURRENT_SERIALIZATION_VERSION)
            self.assertEqual([], references.check_schema(DB), project)

    def test_the_check_on_project_load_names_a_field_added_by_hand(self):
        logging.disable(logging.CRITICAL)
        self.addCleanup(logging.disable, logging.NOTSET)
        DB.load('testing_proj.ltproj', CURRENT_SERIALIZATION_VERSION)
        DB.units[0].signature_item = ITEM
        problems = references.check_schema(DB)
        self.assertEqual(1, len(problems))
        self.assertIn('UnitPrefab.signature_item', problems[0])

    def test_every_catalog_holds_a_declared_type(self):
        logging.disable(logging.CRITICAL)
        self.addCleanup(logging.disable, logging.NOTSET)
        DB.load('testing_proj.ltproj', CURRENT_SERIALIZATION_VERSION)
        for owner_type in references.OWNER_TYPES:
            for record in references.catalog(DB, owner_type):
                self.assertIn(type(record), SCHEMA, owner_type)

    def test_every_sub_record_holds_a_declared_type(self):
        """Records found inside the fields of loaded records are declared too,
        so a new kind of sub-record cannot hide references"""
        logging.disable(logging.CRITICAL)
        self.addCleanup(logging.disable, logging.NOTSET)
        DB.load('default.ltproj', CURRENT_SERIALIZATION_VERSION)
        known = set(SCHEMA)

        def scan(value, where):
            if isinstance(value, (Data, list, tuple, set)):
                for v in value:
                    scan(v, where)
            elif isinstance(value, dict):
                for v in value.values():
                    scan(v, where)
            elif isinstance(value, (Component, Enum)):
                pass  # Components are read through ComponentRefs
            elif hasattr(value, '__dict__') and not isinstance(value, type):
                self.assertIn(type(value), known, where)

        for owner_type in references.OWNER_TYPES:
            for record in references.catalog(DB, owner_type):
                for name, value in vars(record).items():
                    scan(value, '%s.%s' % (owner_type.name, name))


class ReferenceTestCase(unittest.TestCase):
    def setUp(self):
        logging.disable(logging.CRITICAL)
        self.addCleanup(logging.disable, logging.NOTSET)
        DB.load('testing_proj.ltproj', CURRENT_SERIALIZATION_VERSION)
        RESOURCES.load('testing_proj.ltproj', CURRENT_SERIALIZATION_VERSION)
        self.level = DB.levels.get(LEVEL)

    def rename(self, data, target, old_nid, new_nid):
        """Renames the way the editor does: references first, then the record"""
        references.rewrite(DB, target, old_nid, new_nid)
        data.change_key(old_nid, new_nid)

    def assert_no_references(self, target, nid):
        self.assertEqual([], [s.where for s in references.find_referrers(DB, target, nid)])


class RenameTests(ReferenceTestCase):
    def test_renaming_an_item_reaches_units_level_units_and_components(self):
        unit = DB.units.get(UNIT)
        unit.starting_items.append([ITEM, False])
        generic = self.level.units.get('101')
        generic.starting_items.append([ITEM, True])
        multi = DB.items.get('Vulnerary')
        multi.components.append(ICA.restore_component(('multi_item', [ITEM, 'Vulnerary'])))
        skill = DB.skills.get(SKILL)
        skill.components.get('ability').value = ITEM

        self.rename(DB.items, DType.ITEMS, ITEM, NEW)

        self.assertIn([NEW, False], unit.starting_items)
        self.assertIn([NEW, True], generic.starting_items)
        self.assertEqual([NEW, 'Vulnerary'], multi.components.get('multi_item').value)
        self.assertEqual(NEW, skill.components.get('ability').value)
        self.assert_no_references(DType.ITEMS, ITEM)

    def test_renaming_a_skill_reaches_terrain_and_status_regions(self):
        terrain = DB.terrain[0]
        terrain.status = SKILL
        region = Region('Healing Ground')
        region.region_type = RegionType.STATUS
        region.sub_nid = SKILL
        self.level.regions.append(region)
        event_region = Region('Talk Here')
        event_region.region_type = RegionType.EVENT
        event_region.sub_nid = SKILL  # An event trigger name, not a skill
        self.level.regions.append(event_region)

        self.rename(DB.skills, DType.SKILLS, SKILL, NEW)

        self.assertEqual(NEW, terrain.status)
        self.assertEqual(NEW, region.sub_nid)
        self.assertEqual(SKILL, event_region.sub_nid)

    def test_renaming_a_class_reaches_class_components(self):
        klass = DB.units.get(UNIT).klass
        item = DB.items.get(ITEM)
        item.components.append(ICA.restore_component(('prf_class', [klass])))

        self.rename(DB.classes, DType.CLASSES, klass, NEW)

        self.assertEqual([NEW], item.components.get('prf_class').value)
        self.assertEqual(NEW, DB.units.get(UNIT).klass)
        self.assert_no_references(DType.CLASSES, klass)

    def test_renaming_a_unit_rekeys_it_in_levels_and_reaches_groups_parties_and_supports(self):
        seth = 'Seth'
        group = UnitGroup('Group', [UNIT, seth], {UNIT: (1, 1)})
        self.level.unit_groups.append(group)
        DB.parties.append(PartyPrefab('Party', 'Party', UNIT))
        pair = SupportPair(UNIT, 'Nobody', False, SupportRankRequirementList())
        DB.support_pairs.append(pair)
        old_pair_nid = pair.nid

        self.rename(DB.units, DType.UNITS, UNIT, NEW)

        level_unit = self.level.units.get(NEW)
        self.assertIsInstance(level_unit, UniqueUnit)
        self.assertNotIn(UNIT, self.level.units)
        self.assertEqual([NEW, seth], group.units)
        self.assertEqual({NEW: (1, 1)}, group.positions)
        self.assertEqual(NEW, DB.parties.get('Party').leader)
        self.assertEqual(NEW, pair.unit1)
        # A support pair's nid is made from its units, so its catalog is re-keyed
        self.assertIs(pair, DB.support_pairs.get(pair.nid))
        self.assertIsNone(DB.support_pairs.get(old_pair_nid))

    def test_renaming_a_stat_rekeys_stat_dicts_in_place(self):
        stat = DB.stats[0].nid
        klass = DB.classes[0]
        order = list(klass.bases)
        value = klass.bases[stat]

        self.rename(DB.stats, DType.STATS, stat, NEW)

        self.assertEqual([NEW if k == stat else k for k in order], list(klass.bases))
        self.assertEqual(value, klass.bases[NEW])
        self.assertNotIn(stat, DB.units.get(UNIT).bases)

    def test_renaming_a_level_rekeys_its_events(self):
        event = EventPrefab('Intro')
        event.level_nid = LEVEL
        DB.events.append(event)

        self.rename(DB.levels, DType.LEVELS, LEVEL, NEW)

        self.assertEqual(NEW, event.level_nid)
        self.assertIs(event, DB.events.get_from_nid(NEW + ' Intro'))

    def test_renaming_a_team_reaches_alliances(self):
        DB.teams.alliance_pairs = {('other', 'player')}

        references.rewrite(DB, DType.TEAMS, 'player', NEW)

        self.assertEqual({('other', NEW)}, DB.teams.alliance_pairs)

    def test_swapping_a_team_onto_its_ally_drops_the_alliance(self):
        DB.teams.alliance_pairs = {('other', 'player')}

        references.rewrite(DB, DType.TEAMS, 'other', 'player')

        self.assertEqual(set(), DB.teams.alliance_pairs)

    def test_renaming_a_portrait_reaches_units(self):
        portrait = DB.units.get(UNIT).portrait_nid

        references.rewrite(DB, RType.PORTRAITS, portrait, NEW)

        self.assertEqual(NEW, DB.units.get(UNIT).portrait_nid)

    def test_renaming_a_faction_reaches_generic_units_and_ai_targets(self):
        behaviour = DB.ai.get('Attack').behaviours[0]
        behaviour.target_spec = ['Faction', 'Soldier']

        self.rename(DB.factions, DType.FACTIONS, 'Soldier', NEW)

        self.assertEqual(NEW, self.level.units.get('101').faction)
        self.assertEqual(['Faction', NEW], behaviour.target_spec)
        self.assert_no_references(DType.FACTIONS, 'Soldier')

    def test_renaming_an_ai_reaches_level_units_and_components(self):
        self.level.units.get('101').roam_ai = 'Pursue'
        self.assertTrue(references.find_referrers(DB, DType.AI, 'Pursue'))

        self.rename(DB.ai, DType.AI, 'Pursue', NEW)

        self.assertEqual(NEW, self.level.units.get('101').roam_ai)
        self.assert_no_references(DType.AI, 'Pursue')

    def test_renaming_a_weapon_type_rekeys_weapon_experience_in_place_and_reaches_bonuses(self):
        klass = DB.classes.get('Eirika_Lord')
        order = list(klass.wexp_gain)
        gain = klass.wexp_gain['Sword']

        self.rename(DB.weapons, DType.WEAPONS, 'Sword', NEW)

        self.assertEqual([NEW if k == 'Sword' else k for k in order], list(klass.wexp_gain))
        self.assertIs(gain, klass.wexp_gain[NEW])
        self.assertEqual([NEW], [bonus.weapon_type for bonus in DB.weapons.get('Lance').advantage])
        self.assert_no_references(DType.WEAPONS, 'Sword')

    def test_renaming_a_terrain_reaches_ai_targets_and_terrain_regions(self):
        behaviour = DB.ai.get('Attack').behaviours[1]
        behaviour.target, behaviour.target_spec = 'Terrain', '1'
        region = Region('Lava')
        region.region_type = RegionType.TERRAIN
        region.sub_nid = '1'
        self.level.regions.append(region)

        self.rename(DB.terrain, DType.TERRAIN, '1', NEW)

        self.assertEqual(NEW, behaviour.target_spec)
        self.assertEqual(NEW, region.sub_nid)
        self.assert_no_references(DType.TERRAIN, '1')

    def test_renaming_a_tilemap_reaches_levels_and_overworlds(self):
        self.level.bg_tilemap = 'Magvel'

        self.rename(RESOURCES.tilemaps, RType.TILEMAPS, 'Magvel', NEW)

        self.assertEqual(NEW, self.level.bg_tilemap)
        self.assertEqual(NEW, DB.overworlds.get('0').tilemap)
        self.assert_no_references(RType.TILEMAPS, 'Magvel')

    def test_renaming_a_sound_effect_reaches_teams(self):
        DB.teams.get('player').phase_change_sound_effect = 'Aircalibur'

        self.rename(RESOURCES.sfx, RType.SFX, 'Aircalibur', NEW)

        self.assertEqual(NEW, DB.teams.get('player').phase_change_sound_effect)
        self.assert_no_references(RType.SFX, 'Aircalibur')

    def test_renaming_a_song_reaches_level_phases_and_overworlds(self):
        self.level.music['player_phase'] = 'Distant Roads'

        self.rename(RESOURCES.music, RType.MUSIC, 'Distant Roads', NEW)

        self.assertEqual(NEW, self.level.music['player_phase'])
        self.assertIsNone(self.level.music['enemy_phase'])
        self.assertEqual(NEW, DB.overworlds.get('0').music)
        self.assert_no_references(RType.MUSIC, 'Distant Roads')

    def test_rewrite_returns_what_it_changed(self):
        DB.units.get(UNIT).starting_items = [[ITEM, False]]
        sites = references.rewrite(DB, DType.ITEMS, ITEM, NEW)
        self.assertIn(DB.units.get(UNIT), references.owners(sites)[DType.UNITS])


class SwapTests(ReferenceTestCase):
    def test_swapping_a_stat_onto_one_already_present_keeps_that_entry(self):
        stats = DB.stats.keys()
        klass = DB.classes[0]
        klass.bases[stats[0]], klass.bases[stats[1]] = 5, 7

        references.rewrite(DB, DType.STATS, stats[0], stats[1])

        self.assertNotIn(stats[0], klass.bases)
        self.assertEqual(7, klass.bases[stats[1]])

    def test_swapping_a_faction_moves_its_generic_units(self):
        references.rewrite(DB, DType.FACTIONS, 'Soldier', 'Bandit')

        self.assertEqual('Bandit', self.level.units.get('101').faction)
        self.assertEqual('Bandit', self.level.units.get('102').faction)

    def test_swapping_an_ai_moves_the_units_using_it(self):
        references.rewrite(DB, DType.AI, 'Attack', 'Guard')

        self.assertEqual('Guard', self.level.units.get('101').ai)
        self.assertEqual('Guard', self.level.units.get("O'Neill").ai)

    def test_swapping_a_weapon_type_onto_one_already_present_keeps_that_entry(self):
        klass = DB.classes.get('Eirika_Lord')
        lance = klass.wexp_gain['Lance']

        references.rewrite(DB, DType.WEAPONS, 'Sword', 'Lance')

        self.assertNotIn('Sword', klass.wexp_gain)
        self.assertIs(lance, klass.wexp_gain['Lance'])

    def test_swapping_a_terrain_moves_its_regions(self):
        region = Region('Lava')
        region.region_type = RegionType.TERRAIN
        region.sub_nid = '1'
        self.level.regions.append(region)

        references.rewrite(DB, DType.TERRAIN, '1', '2')

        self.assertEqual('2', region.sub_nid)

    def test_swapping_a_tilemap_moves_the_levels_using_it(self):
        references.rewrite(DB, RType.TILEMAPS, 'Prologue', 'Test')

        self.assertEqual('Test', self.level.tilemap)
        self.assertEqual('Test', DB.levels.get('1').tilemap)

    def test_swapping_a_song_moves_every_phase_playing_it(self):
        self.level.music['player_phase'] = 'Distant Roads'
        self.level.music['enemy_phase'] = 'Distant Roads'

        references.rewrite(DB, RType.MUSIC, 'Distant Roads', 'Other Song')

        self.assertEqual('Other Song', self.level.music['player_phase'])
        self.assertEqual('Other Song', self.level.music['enemy_phase'])
        self.assertEqual('Other Song', DB.overworlds.get('0').music)


class ClearTests(ReferenceTestCase):
    def test_clearing_a_unit_removes_it_from_levels_groups_and_lists(self):
        group = UnitGroup('Group', [UNIT, 'Seth'], {UNIT: (1, 1)})
        self.level.unit_groups.append(group)
        DB.parties.append(PartyPrefab('Party', 'Party', UNIT))

        references.clear(DB, DType.UNITS, UNIT, fallback='Seth')

        self.assertNotIn(UNIT, self.level.units)
        self.assertEqual(['Seth'], group.units)
        self.assertEqual({}, group.positions)
        # A party must have a leader, so it takes the fallback
        self.assertEqual('Seth', DB.parties.get('Party').leader)
        self.assert_no_references(DType.UNITS, UNIT)

    def test_clearing_an_item_drops_whole_starting_item_entries(self):
        unit = DB.units.get(UNIT)
        unit.starting_items = [[ITEM, False], ['Vulnerary', True]]

        references.clear(DB, DType.ITEMS, ITEM)

        self.assertEqual([['Vulnerary', True]], unit.starting_items)


class DanglingTests(ReferenceTestCase):
    def test_a_traveler_may_name_a_generic_unit_of_the_same_level(self):
        self.level.units.get(UNIT).starting_traveler = '101'
        self.assertEqual([], [s for s in references.dangling(DB, RESOURCES) if s.where.endswith('starting_traveler')])

    def test_a_reference_to_nothing_is_dangling(self):
        DB.units.get(UNIT).affinity = 'Nothing_By_This_Name'
        sites = [s for s in references.dangling(DB, RESOURCES) if s.target == DType.AFFINITIES]
        self.assertEqual(['affinity'], [s.where for s in sites])


if __name__ == '__main__':
    unittest.main()
