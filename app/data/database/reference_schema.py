"""
Every field of every database record, and what each one names.

SCHEMA has one entry per record type, listing all of its fields. A field that
holds the nid of another record says what kind of record with Ref; a field
that names nothing is NOT_REF. Renaming, deleting and validating all read this
one schema (through references.py, which does the walking), so a field left
out here is a field renames and deletions never update. The editor logs a
warning naming any field that is missing, and test_references.py fails on it.

Adding a field to a record, say a signature item on units:

    'signature_item': Ref(DType.ITEMS),   # in UnitPrefab's entry

or, if it holds no nid (a number, some text, a flag):

    'signature_line': NOT_REF,

Ref(target, at) declares a reference. target is a DatabaseType, a ResourceType
or an OtherType; or a function of the record holding the field that returns
one, or None when this record's field names nothing, for fields whose meaning
depends on another field (a region's sub_nid names a skill or a terrain by its
region type). at says where the nids sit inside the field, when the field is
not itself the nid:

    ''          the field is the nid                  klass
    '[*]'       every element of a list (or Data)     turns_into
    '[*][1]'    index 1 of every element              learned_skills: [level, skill] pairs
    '{key}'     every key of a dict                   bases: stat -> value
    '{*}'       every value of a dict                 music: situation -> song
    '[*].rank'  an attribute of every element

A field holding more than one kind of reference takes a list of Refs.
Nested() marks a list of sub-records, which have their own entries here.
ComponentRefs() marks item and skill components, whose references come from
each component's `expose`, through COMPONENT_TARGETS.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Union

from app.data.database.ai import AIBehaviour, AIPrefab
from app.data.database.ai_groups import AIGroup
from app.data.database.components import ComponentType as CType
from app.data.database.constants import Constant, ConstantType
from app.data.database.credit import CreditEntry
from app.data.database.database_types import DatabaseType as DType
from app.data.database.difficulty_modes import DifficultyModePrefab
from app.data.database.equations import Equation
from app.data.database.factions import Faction
from app.data.database.items import ItemPrefab
from app.data.database.klass import Klass
from app.data.database.level_units import GenericUnit, UniqueUnit, UnitGroup
from app.data.database.levels import LevelPrefab
from app.data.database.lore import Lore
from app.data.database.overworld import OverworldPrefab
from app.data.database.overworld_node import OverworldNodePrefab
from app.data.database.parties import PartyPrefab
from app.data.database.raw_data import RawDataPrefab
from app.data.database.skills import SkillPrefab
from app.data.database.stats import StatPrefab
from app.data.database.supports import (Affinity, SupportPair, SupportRank,
                                        SupportRankBonus, SupportRankRequirement)
from app.data.database.tags import Tag
from app.data.database.teams import Team
from app.data.database.terrain import Terrain
from app.data.database.translations import Translation
from app.data.database.units import UnitPrefab
from app.data.database.varslot import VarSlot
from app.data.database.weapons import CombatBonus, WeaponRank, WeaponType, WexpGain
from app.data.resources.resource_types import ResourceType as RType
from app.events.event_prefab import EventPrefab
from app.events.node_events import NodeMenuEvent
from app.events.regions import Region, RegionType


class OtherType(Enum):
    """Things a nid can name that are neither a database catalog nor a resource catalog"""
    MOVEMENT_TYPES = 'movement_types'  # A column of the movement cost grid
    TERRAIN_MOVEMENT_TYPES = 'terrain_movement_types'  # A row of the movement cost grid


Target = Union[DType, RType, OtherType]
Resolver = Callable[[Any], Optional[Target]]


class ClearPolicy(Enum):
    """What deleting the record a reference names does to the reference"""
    AUTO = 0  # Drop the element of the last [*] in the path, or the dict key; otherwise set None
    REMOVE_RECORD = 1  # Remove the record holding the field from its Data, be it a sub-record or a catalog's own
    REPLACE = 2  # The field must name something: point it at the caller's fallback


@dataclass(frozen=True)
class Ref:
    target: Union[Target, Resolver]
    at: str = ''
    # The name of a Data on the top-level record whose keys also satisfy this
    # reference. Level units name their travelers and group members by level
    # unit nid, which is a generic unit's own nid as often as a unit prefab's.
    local: Optional[str] = None
    on_clear: ClearPolicy = ClearPolicy.AUTO
    # False for a dict holding an entry for every record of the target, like a
    # class's wexp gain per weapon type: a deletion drops the entry without
    # listing every class as affected
    listed: bool = True
    # True when no two elements of the list holding the reference may name the
    # same record, like a class's tags or an affinity's bonus per support rank:
    # swapping a record onto one the list already names drops the element
    # instead, as a dict key does
    unique: bool = False


@dataclass(frozen=True)
class Nested:
    """A list of sub-records, each walked by its own type's entry"""


@dataclass(frozen=True)
class ComponentRefs:
    """Item or skill components, walked by what each component exposes"""


NOT_REF = None  # A field that names no other record

Declaration = Union[Ref, Nested, ComponentRefs, None]
FieldDeclarations = Union[Declaration, List[Ref]]

# A dict from each stat's nid to a value, holding an entry for every stat
STAT_DICT = Ref(DType.STATS, '{key}', listed=False)

COMPONENT_TARGETS: Dict[CType, Target] = {
    CType.WeaponType: DType.WEAPONS,
    CType.WeaponRank: DType.WEAPON_RANKS,
    CType.Unit: DType.UNITS,
    CType.Class: DType.CLASSES,
    CType.Tag: DType.TAGS,
    CType.Item: DType.ITEMS,
    CType.Skill: DType.SKILLS,
    CType.Stat: DType.STATS,
    CType.StatFloat: DType.STATS,
    CType.StatString: DType.STATS,
    CType.Equation: DType.EQUATIONS,
    CType.MovementType: OtherType.MOVEMENT_TYPES,
    CType.AI: DType.AI,
    CType.Affinity: DType.AFFINITIES,
    CType.Terrain: DType.TERRAIN,
    CType.Lore: DType.LORE,
    CType.Event: DType.EVENTS,
    CType.MapAnimation: RType.ANIMATIONS,
    CType.Sound: RType.SFX,
    CType.Music: RType.MUSIC,
    CType.CombatAnimation: RType.COMBAT_ANIMS,
    CType.EffectAnimation: RType.COMBAT_EFFECTS,
}


# === Resolvers: fields whose meaning depends on another field ===
AI_UNIT_SPEC_TARGETS: Dict[str, DType] = {
    'Class': DType.CLASSES,
    'Tag': DType.TAGS,
    'Team': DType.TEAMS,
    'Faction': DType.FACTIONS,
    'Party': DType.PARTIES,
    'ID': DType.UNITS,
}

def _ai_unit_spec_target(behaviour: AIBehaviour) -> Optional[Target]:
    if behaviour.target in ('Enemy', 'Ally', 'Unit') and behaviour.target_spec:
        return AI_UNIT_SPEC_TARGETS.get(behaviour.target_spec[0])
    return None

def _ai_terrain_target(behaviour: AIBehaviour) -> Optional[Target]:
    return DType.TERRAIN if behaviour.target == 'Terrain' else None

def _region_target(region: Region) -> Optional[Target]:
    if region.region_type == RegionType.STATUS:
        return DType.SKILLS
    elif region.region_type == RegionType.TERRAIN:
        return DType.TERRAIN
    return None

def _credit_target(credit: CreditEntry) -> Optional[Target]:
    return credit.credit_type if isinstance(credit.credit_type, RType) else None

def _constant_target(constant: Constant) -> Optional[Target]:
    return RType.MUSIC if constant.attr == ConstantType.MUSIC else None

def _weapon_rank_target(bonus: CombatBonus) -> Optional[Target]:
    return None if bonus.weapon_rank == 'All' else DType.WEAPON_RANKS


SCHEMA: Dict[type, Dict[str, FieldDeclarations]] = {
    Constant: {
        'nid': NOT_REF,
        'name': NOT_REF,
        'attr': NOT_REF,
        'value': Ref(_constant_target),
        'tag': NOT_REF,
    },
    StatPrefab: {
        'nid': NOT_REF,
        'name': NOT_REF,
        'maximum': NOT_REF,
        'desc': NOT_REF,
        'position': NOT_REF,
        'growth_colors': NOT_REF,
        'hidden_stat': NOT_REF,
    },
    Equation: {
        'nid': NOT_REF,
        'expression': NOT_REF,
    },
    Terrain: {
        'nid': NOT_REF,
        'name': NOT_REF,
        'color': NOT_REF,
        'minimap': NOT_REF,  # a fixed engine sprite set, not an editable catalog
        'platform': NOT_REF,  # a fixed engine sprite set, not an editable catalog
        'background': Ref(RType.PANORAMAS),
        'mtype': Ref(OtherType.TERRAIN_MOVEMENT_TYPES),
        'opaque': NOT_REF,
        'status': Ref(DType.SKILLS),
    },
    WeaponRank: {
        'rank': NOT_REF,
        'requirement': NOT_REF,
    },
    WeaponType: {
        'nid': NOT_REF,
        'name': NOT_REF,
        'force_melee_anim': NOT_REF,
        'hide_from_display': NOT_REF,
        'hide_from_convoy': NOT_REF,
        'rank_bonus': Nested(),
        'advantage': Nested(),
        'disadvantage': Nested(),
        'icon_nid': Ref(RType.ICONS16),
        'icon_index': NOT_REF,
    },
    CombatBonus: {
        'weapon_type': Ref(DType.WEAPONS),
        'weapon_rank': Ref(_weapon_rank_target),
        'damage': NOT_REF,
        'resist': NOT_REF,
        'accuracy': NOT_REF,
        'avoid': NOT_REF,
        'crit': NOT_REF,
        'dodge': NOT_REF,
        'attack_speed': NOT_REF,
        'defense_speed': NOT_REF,
    },
    WexpGain: {
        'usable': NOT_REF,
        'wexp_gain': NOT_REF,
        'cap': NOT_REF,
    },
    Team: {
        'nid': NOT_REF,
        'map_sprite_palette': Ref(RType.COMBAT_PALETTES),
        'combat_variant_palette': NOT_REF,  # matched against the palette names inside each combat animation, not a palette nid
        'combat_color': NOT_REF,
        'phase_change_sound_effect': Ref(RType.SFX),
    },
    Faction: {
        'nid': NOT_REF,
        'name': NOT_REF,
        'desc': NOT_REF,
        'icon_nid': Ref(RType.ICONS32),
        'icon_index': NOT_REF,
    },
    ItemPrefab: {
        'nid': NOT_REF,
        'name': NOT_REF,
        'desc': NOT_REF,
        'icon_nid': Ref(RType.ICONS16),
        'icon_index': NOT_REF,
        'components': ComponentRefs(),
    },
    SkillPrefab: {
        'nid': NOT_REF,
        'name': NOT_REF,
        'desc': NOT_REF,
        'icon_nid': Ref(RType.ICONS16),
        'icon_index': NOT_REF,
        'components': ComponentRefs(),
    },
    Tag: {
        'nid': NOT_REF,
    },
    VarSlot: {
        'nid': NOT_REF,
        'desc': NOT_REF,
    },
    Klass: {
        'nid': NOT_REF,
        'name': NOT_REF,
        'desc': NOT_REF,
        'tier': NOT_REF,
        'movement_group': Ref(OtherType.MOVEMENT_TYPES),
        'promotes_from': Ref(DType.CLASSES),
        'turns_into': Ref(DType.CLASSES, '[*]', unique=True),
        'tags': Ref(DType.TAGS, '[*]', unique=True),
        'max_level': NOT_REF,
        'bases': STAT_DICT,
        'growths': STAT_DICT,
        'growth_bonus': STAT_DICT,
        'promotion': STAT_DICT,
        'max_stats': STAT_DICT,
        'learned_skills': Ref(DType.SKILLS, '[*][1]'),
        'wexp_gain': Ref(DType.WEAPONS, '{key}', listed=False),
        'icon_nid': Ref(RType.ICONS80),
        'icon_index': NOT_REF,
        'map_sprite_nid': Ref(RType.MAP_SPRITES),
        'combat_anim_nid': Ref(RType.COMBAT_ANIMS),
        'fields': NOT_REF,
    },
    SupportRank: {
        'nid': NOT_REF,
    },
    Affinity: {
        'nid': NOT_REF,
        'name': NOT_REF,
        'desc': NOT_REF,
        'bonus': Nested(),
        'icon_nid': Ref(RType.ICONS16),
        'icon_index': NOT_REF,
    },
    SupportRankBonus: {
        'support_rank': Ref(DType.SUPPORT_RANKS, unique=True),
        'damage': NOT_REF,
        'resist': NOT_REF,
        'accuracy': NOT_REF,
        'avoid': NOT_REF,
        'crit': NOT_REF,
        'dodge': NOT_REF,
        'attack_speed': NOT_REF,
        'defense_speed': NOT_REF,
    },
    SupportRankRequirement: {
        'support_rank': Ref(DType.SUPPORT_RANKS, unique=True),
        'requirement': NOT_REF,
        'gate': NOT_REF,
        'damage': NOT_REF,
        'resist': NOT_REF,
        'accuracy': NOT_REF,
        'avoid': NOT_REF,
        'crit': NOT_REF,
        'dodge': NOT_REF,
        'attack_speed': NOT_REF,
        'defense_speed': NOT_REF,
    },
    UnitPrefab: {
        'nid': NOT_REF,
        'name': NOT_REF,
        'desc': NOT_REF,
        'variant': NOT_REF,  # names a palette variant of the unit's own sprites, not a record
        'level': NOT_REF,
        'klass': Ref(DType.CLASSES),
        'tags': Ref(DType.TAGS, '[*]', unique=True),
        'bases': STAT_DICT,
        'growths': STAT_DICT,
        'stat_cap_modifiers': STAT_DICT,
        'starting_items': Ref(DType.ITEMS, '[*][0]'),
        'learned_skills': Ref(DType.SKILLS, '[*][1]'),
        'unit_notes': NOT_REF,
        'wexp_gain': Ref(DType.WEAPONS, '{key}', listed=False),
        'alternate_classes': Ref(DType.CLASSES, '[*]', unique=True),
        'portrait_nid': Ref(RType.PORTRAITS),
        'affinity': Ref(DType.AFFINITIES),
        'fields': NOT_REF,
    },
    SupportPair: {
        'unit1': Ref(DType.UNITS),
        'unit2': Ref(DType.UNITS),
        'one_way': NOT_REF,
        'requirements': Nested(),
    },
    AIPrefab: {
        'nid': NOT_REF,
        'behaviours': Nested(),
        'priority': NOT_REF,
        'offense_bias': NOT_REF,
        'roam_ai': NOT_REF,
    },
    AIBehaviour: {
        'action': NOT_REF,
        'target': NOT_REF,
        # A unit spec is a (kind, value) pair; a terrain target is the terrain nid itself
        'target_spec': [Ref(_ai_unit_spec_target, '[1]'), Ref(_ai_terrain_target)],
        'view_range': NOT_REF,
        'invert_targeting': NOT_REF,
        'roam_speed': NOT_REF,
        'desired_proximity': NOT_REF,
        'condition': NOT_REF,
    },
    PartyPrefab: {
        'nid': NOT_REF,
        'name': NOT_REF,
        'leader': Ref(DType.UNITS, on_clear=ClearPolicy.REPLACE),
    },
    DifficultyModePrefab: {
        'nid': NOT_REF,
        'name': NOT_REF,
        'color': NOT_REF,
        'permadeath_choice': NOT_REF,
        'growths_choice': NOT_REF,
        'rng_choice': NOT_REF,
        'player_bases': STAT_DICT,
        'enemy_bases': STAT_DICT,
        'boss_bases': STAT_DICT,
        'player_growths': STAT_DICT,
        'enemy_growths': STAT_DICT,
        'boss_growths': STAT_DICT,
        'player_autolevels': NOT_REF,
        'enemy_autolevels': NOT_REF,
        'boss_autolevels': NOT_REF,
        'promoted_autolevels_fraction': NOT_REF,
        'start_locked': NOT_REF,
    },
    CreditEntry: {
        'nid': NOT_REF,
        'sub_nid': Ref(_credit_target),
        'credit_type': NOT_REF,
        'category': NOT_REF,
        'custom_header': NOT_REF,
        'icon_index': NOT_REF,
        'contrib': NOT_REF,
    },
    Translation: {
        'nid': NOT_REF,
        'text': NOT_REF,
    },
    Lore: {
        'nid': NOT_REF,
        'name': NOT_REF,
        'title': NOT_REF,
        'category': NOT_REF,
        'text': NOT_REF,
    },
    LevelPrefab: {
        'nid': NOT_REF,
        'name': NOT_REF,
        'tilemap': Ref(RType.TILEMAPS),
        'bg_tilemap': Ref(RType.TILEMAPS),
        'party': Ref(DType.PARTIES),
        'music': Ref(RType.MUSIC, '{*}'),
        'objective': NOT_REF,
        'roam': NOT_REF,
        'roam_unit': Ref(DType.UNITS),
        'go_to_overworld': NOT_REF,
        'should_record': NOT_REF,
        'tags': Ref(DType.TAGS, '[*]', unique=True),
        'units': Nested(),
        'regions': Nested(),
        'unit_groups': Nested(),
        'ai_groups': Nested(),
    },
    GenericUnit: {
        'nid': NOT_REF,  # a level-local name
        'variant': NOT_REF,
        'level': NOT_REF,
        'klass': Ref(DType.CLASSES),
        'faction': Ref(DType.FACTIONS),
        'starting_items': Ref(DType.ITEMS, '[*][0]'),
        'starting_skills': Ref(DType.SKILLS, '[*]'),
        'team': Ref(DType.TEAMS),
        'ai': Ref(DType.AI),
        'roam_ai': Ref(DType.AI),
        'ai_group': NOT_REF,  # a level-local name; the level rebuilds its ai_groups from its units on load
        'starting_position': NOT_REF,
        'starting_traveler': Ref(DType.UNITS, local='units'),
        'generic': NOT_REF,
    },
    UniqueUnit: {
        'nid': Ref(DType.UNITS, on_clear=ClearPolicy.REMOVE_RECORD),
        'team': Ref(DType.TEAMS),
        'ai': Ref(DType.AI),
        'roam_ai': Ref(DType.AI),
        'ai_group': NOT_REF,  # a level-local name; the level rebuilds its ai_groups from its units on load
        'faction': NOT_REF,  # always None on a unique unit
        'starting_position': NOT_REF,
        'starting_traveler': Ref(DType.UNITS, local='units'),
        'generic': NOT_REF,
    },
    UnitGroup: {
        'nid': NOT_REF,
        'units': Ref(DType.UNITS, '[*]', local='units', unique=True),
        'positions': Ref(DType.UNITS, '{key}', local='units'),
    },
    AIGroup: {
        'nid': NOT_REF,
        'trigger_threshold': NOT_REF,
    },
    Region: {
        'nid': NOT_REF,
        'region_type': NOT_REF,
        'position': NOT_REF,
        'size': NOT_REF,
        'sub_nid': Ref(_region_target),
        'highlight': NOT_REF,
        'condition': NOT_REF,
        'time_left': NOT_REF,
        'only_once': NOT_REF,
        'interrupt_move': NOT_REF,
        'hide_time': NOT_REF,
    },
    EventPrefab: {
        'name': NOT_REF,
        'trigger': NOT_REF,
        'level_nid': Ref(DType.LEVELS, on_clear=ClearPolicy.REMOVE_RECORD),  # a level's events go with it
        'condition': NOT_REF,
        'commands': NOT_REF,  # event scripts name records in free text; they are searched, not rewritten
        'only_once': NOT_REF,
        'priority': NOT_REF,
        '_source': NOT_REF,
    },
    OverworldPrefab: {
        'nid': NOT_REF,
        'name': NOT_REF,
        'tilemap': Ref(RType.TILEMAPS),
        'music': Ref(RType.MUSIC),
        'overworld_nodes': Nested(),
        'map_paths': NOT_REF,
        'border_tile_width': NOT_REF,
    },
    OverworldNodePrefab: {
        'nid': NOT_REF,
        'name': NOT_REF,
        'pos': NOT_REF,
        'icon': Ref(RType.MAP_ICONS, on_clear=ClearPolicy.REPLACE),
        'level': Ref(DType.LEVELS),
        'menu_options': Nested(),
    },
    NodeMenuEvent: {
        'nid': NOT_REF,
        'event': Ref(DType.EVENTS),
        'option_name': NOT_REF,
        'visible': NOT_REF,
        'enabled': NOT_REF,
    },
    RawDataPrefab: {
        'nid': NOT_REF,
        'dtype': NOT_REF,
        'svalue': NOT_REF,
        'kvvalue': NOT_REF,
        'oattrs': NOT_REF,
        'lovalue': NOT_REF,
    },
}
