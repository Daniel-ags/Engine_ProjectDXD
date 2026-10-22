"""
Every place one database record names another by nid.

REFERENCES lists, for each record type, the fields that hold a nid and what
kind of record that nid names. Renaming, deleting and validating all read this
one list, so none of them keeps its own idea of where references live. A field
that names nothing is listed in NOT_REFERENCES instead; the completeness test
fails on any field that is in neither.

A path names where the nids sit inside a record:

    klass                 the attribute itself
    turns_into[*]         every element of a list (or Data)
    learned_skills[*][1]  index 1 of every element
    bases{key}            every key of a dict
    music{*}              every value of a dict
    bonus[*].support_rank an attribute of every element

Ref(path, target) declares references. Its target is a DatabaseType, a
ResourceType or an OtherType, or a function of the record holding the field
that returns one (or None when this record's field names nothing), for fields
whose meaning depends on another field. Nested(path) walks into sub-records,
which have their own entry. ComponentRefs(path) reads each component's
`expose` to find the nids in item and skill components.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import re
from typing import Any, Callable, Dict, Iterable, Iterator, List, Optional, Set, Tuple, Type, Union

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
from app.utilities.data import Data
from app.utilities.typing import NID


class OtherType(Enum):
    """Things a nid can name that are neither a database catalog nor a resource catalog"""
    MOVEMENT_TYPES = 'movement_types'  # A column of the movement cost grid
    TERRAIN_MOVEMENT_TYPES = 'terrain_movement_types'  # A row of the movement cost grid


Target = Union[DType, RType, OtherType]
Resolver = Callable[[Any], Optional[Target]]


class ClearPolicy(Enum):
    AUTO = 0  # Drop the element of the last [*] in the path, or the dict key; otherwise set None
    REMOVE_RECORD = 1  # Remove the sub-record holding the field from its Data


@dataclass(frozen=True)
class Ref:
    path: str
    target: Union[Target, Resolver]
    # The name of a Data on the top-level record whose keys also satisfy this
    # reference. Level units name their travelers and group members by level
    # unit nid, which is a generic unit's own nid as often as a unit prefab's.
    local: Optional[str] = None
    on_clear: ClearPolicy = ClearPolicy.AUTO


@dataclass(frozen=True)
class Nested:
    path: str


@dataclass(frozen=True)
class ComponentRefs:
    path: str = 'components'


Declaration = Union[Ref, Nested, ComponentRefs]

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

def _stat_dicts(*names: str) -> List[Ref]:
    return [Ref('%s{key}' % name, DType.STATS) for name in names]


REFERENCES: Dict[type, List[Declaration]] = {
    Constant: [Ref('value', _constant_target)],
    Terrain: [Ref('background', RType.PANORAMAS),
              Ref('mtype', OtherType.TERRAIN_MOVEMENT_TYPES),
              Ref('status', DType.SKILLS)],
    WeaponType: [Nested('rank_bonus[*]'), Nested('advantage[*]'), Nested('disadvantage[*]'),
                 Ref('icon_nid', RType.ICONS16)],
    CombatBonus: [Ref('weapon_type', DType.WEAPONS), Ref('weapon_rank', _weapon_rank_target)],
    Team: [Ref('map_sprite_palette', RType.COMBAT_PALETTES),
           Ref('phase_change_sound_effect', RType.SFX)],
    Faction: [Ref('icon_nid', RType.ICONS32)],
    ItemPrefab: [Ref('icon_nid', RType.ICONS16), ComponentRefs('components')],
    SkillPrefab: [Ref('icon_nid', RType.ICONS16), ComponentRefs('components')],
    Klass: [Ref('movement_group', OtherType.MOVEMENT_TYPES),
            Ref('promotes_from', DType.CLASSES),
            Ref('turns_into[*]', DType.CLASSES),
            Ref('tags[*]', DType.TAGS),
            *_stat_dicts('bases', 'growths', 'growth_bonus', 'promotion', 'max_stats'),
            Ref('learned_skills[*][1]', DType.SKILLS),
            Ref('wexp_gain{key}', DType.WEAPONS),
            Ref('icon_nid', RType.ICONS80),
            Ref('map_sprite_nid', RType.MAP_SPRITES),
            Ref('combat_anim_nid', RType.COMBAT_ANIMS)],
    Affinity: [Nested('bonus[*]'), Ref('icon_nid', RType.ICONS16)],
    SupportRankBonus: [Ref('support_rank', DType.SUPPORT_RANKS)],
    SupportRankRequirement: [Ref('support_rank', DType.SUPPORT_RANKS)],
    UnitPrefab: [Ref('klass', DType.CLASSES),
                 Ref('tags[*]', DType.TAGS),
                 *_stat_dicts('bases', 'growths', 'stat_cap_modifiers'),
                 Ref('starting_items[*][0]', DType.ITEMS),
                 Ref('learned_skills[*][1]', DType.SKILLS),
                 Ref('wexp_gain{key}', DType.WEAPONS),
                 Ref('alternate_classes[*]', DType.CLASSES),
                 Ref('portrait_nid', RType.PORTRAITS),
                 Ref('affinity', DType.AFFINITIES)],
    SupportPair: [Ref('unit1', DType.UNITS), Ref('unit2', DType.UNITS), Nested('requirements[*]')],
    AIPrefab: [Nested('behaviours[*]')],
    AIBehaviour: [Ref('target_spec[1]', _ai_unit_spec_target), Ref('target_spec', _ai_terrain_target)],
    PartyPrefab: [Ref('leader', DType.UNITS)],
    DifficultyModePrefab: _stat_dicts('player_bases', 'enemy_bases', 'boss_bases',
                                      'player_growths', 'enemy_growths', 'boss_growths'),
    CreditEntry: [Ref('sub_nid', _credit_target)],
    LevelPrefab: [Ref('tilemap', RType.TILEMAPS),
                  Ref('bg_tilemap', RType.TILEMAPS),
                  Ref('party', DType.PARTIES),
                  Ref('music{*}', RType.MUSIC),
                  Ref('roam_unit', DType.UNITS),
                  Ref('tags[*]', DType.TAGS),
                  Nested('units[*]'), Nested('regions[*]'), Nested('unit_groups[*]'), Nested('ai_groups[*]')],
    GenericUnit: [Ref('klass', DType.CLASSES),
                  Ref('faction', DType.FACTIONS),
                  Ref('starting_items[*][0]', DType.ITEMS),
                  Ref('starting_skills[*]', DType.SKILLS),
                  Ref('team', DType.TEAMS),
                  Ref('ai', DType.AI),
                  Ref('roam_ai', DType.AI),
                  Ref('starting_traveler', DType.UNITS, local='units')],
    UniqueUnit: [Ref('nid', DType.UNITS, on_clear=ClearPolicy.REMOVE_RECORD),
                 Ref('team', DType.TEAMS),
                 Ref('ai', DType.AI),
                 Ref('roam_ai', DType.AI),
                 Ref('starting_traveler', DType.UNITS, local='units')],
    UnitGroup: [Ref('units[*]', DType.UNITS, local='units'),
                Ref('positions{key}', DType.UNITS, local='units')],
    Region: [Ref('sub_nid', _region_target)],
    EventPrefab: [Ref('level_nid', DType.LEVELS)],
    OverworldPrefab: [Ref('tilemap', RType.TILEMAPS), Ref('music', RType.MUSIC), Nested('overworld_nodes[*]')],
    OverworldNodePrefab: [Ref('icon', RType.MAP_ICONS), Ref('level', DType.LEVELS), Nested('menu_options[*]')],
    NodeMenuEvent: [Ref('event', DType.EVENTS)],
}

NOT_REFERENCES: Dict[type, Set[str]] = {
    Constant: {'nid', 'name', 'attr', 'tag'},
    StatPrefab: {'nid', 'name', 'maximum', 'desc', 'position', 'growth_colors', 'hidden_stat'},
    Equation: {'nid', 'expression'},
    # minimap and platform name fixed engine sprite sets, not editable catalogs
    Terrain: {'nid', 'name', 'color', 'minimap', 'platform', 'opaque'},
    WeaponRank: {'rank', 'requirement'},
    WeaponType: {'nid', 'name', 'force_melee_anim', 'hide_from_display', 'hide_from_convoy', 'icon_index'},
    CombatBonus: {'damage', 'resist', 'accuracy', 'avoid', 'crit', 'dodge', 'attack_speed', 'defense_speed'},
    WexpGain: {'usable', 'wexp_gain', 'cap'},
    # combat_variant_palette is matched against the palette names inside each
    # combat animation, not a palette nid
    Team: {'nid', 'combat_variant_palette', 'combat_color'},
    Faction: {'nid', 'name', 'desc', 'icon_index'},
    ItemPrefab: {'nid', 'name', 'desc', 'icon_index'},
    SkillPrefab: {'nid', 'name', 'desc', 'icon_index'},
    Tag: {'nid'},
    VarSlot: {'nid', 'desc'},
    Klass: {'nid', 'name', 'desc', 'tier', 'max_level', 'icon_index', 'fields'},
    SupportRank: {'nid'},
    Affinity: {'nid', 'name', 'desc', 'icon_index'},
    SupportRankBonus: {'damage', 'resist', 'accuracy', 'avoid', 'crit', 'dodge', 'attack_speed', 'defense_speed'},
    SupportRankRequirement: {'requirement', 'gate', 'damage', 'resist', 'accuracy', 'avoid', 'crit', 'dodge',
                             'attack_speed', 'defense_speed'},
    # variant names a palette variant of the unit's own sprites, not a record
    UnitPrefab: {'nid', 'name', 'desc', 'variant', 'level', 'unit_notes', 'fields'},
    SupportPair: {'one_way'},
    AIPrefab: {'nid', 'priority', 'offense_bias', 'roam_ai'},
    AIBehaviour: {'action', 'target', 'view_range', 'invert_targeting', 'roam_speed', 'desired_proximity',
                  'condition'},
    PartyPrefab: {'nid', 'name'},
    DifficultyModePrefab: {'nid', 'name', 'color', 'permadeath_choice', 'growths_choice', 'rng_choice',
                           'player_autolevels', 'enemy_autolevels', 'boss_autolevels',
                           'promoted_autolevels_fraction', 'start_locked'},
    CreditEntry: {'nid', 'credit_type', 'category', 'custom_header', 'icon_index', 'contrib'},
    Translation: {'nid', 'text'},
    Lore: {'nid', 'name', 'title', 'category', 'text'},
    LevelPrefab: {'nid', 'name', 'objective', 'roam', 'go_to_overworld', 'should_record'},
    # A generic unit's nid and its ai_group are level-local names; the level
    # rebuilds its ai_groups from its units on load
    GenericUnit: {'nid', 'variant', 'level', 'ai_group', 'starting_position', 'generic'},
    # faction is always None on a unique unit
    UniqueUnit: {'ai_group', 'faction', 'starting_position', 'generic'},
    UnitGroup: {'nid'},
    AIGroup: {'nid', 'trigger_threshold'},
    Region: {'nid', 'region_type', 'position', 'size', 'highlight', 'condition', 'time_left', 'only_once',
             'interrupt_move', 'hide_time'},
    # Event scripts name records in free text; they are searched, not rewritten
    EventPrefab: {'name', 'trigger', 'condition', 'commands', 'only_once', 'priority', '_source'},
    OverworldPrefab: {'nid', 'name', 'map_paths', 'border_tile_width'},
    OverworldNodePrefab: {'nid', 'name', 'pos'},
    NodeMenuEvent: {'nid', 'option_name', 'visible', 'enabled'},
    RawDataPrefab: {'nid', 'dtype', 'svalue', 'kvvalue', 'oattrs', 'lovalue'},
}

# The movement cost grid and the minimap types are not lists of records
OWNER_TYPES: Tuple[DType, ...] = tuple(dtype for dtype in DType if dtype not in (DType.MCOST, DType.MINIMAP))


def catalog(db, dtype: DType) -> Data:
    return getattr(db, dtype.name.lower())


# === Paths ===
_TOKEN = re.compile(r'(\w+)|\[\*\]|\[(\d+)\]|\{key\}|\{\*\}|\.')
_ATTR, _EACH, _INDEX, _KEYS, _VALUES = 'attr', 'each', 'index', 'keys', 'values'
Step = Tuple[str, Any]

_parsed: Dict[str, Tuple[Step, ...]] = {}

def parse_path(path: str) -> Tuple[Step, ...]:
    if path in _parsed:
        return _parsed[path]
    steps: List[Step] = []
    pos = 0
    while pos < len(path):
        match = _TOKEN.match(path, pos)
        if not match:
            raise ValueError('Bad reference path %r at %d' % (path, pos))
        token = match.group(0)
        if match.group(1):
            steps.append((_ATTR, token))
        elif match.group(2):
            steps.append((_INDEX, int(match.group(2))))
        elif token == '[*]':
            steps.append((_EACH, None))
        elif token == '{key}':
            steps.append((_KEYS, None))
        elif token == '{*}':
            steps.append((_VALUES, None))
        pos = match.end()
    _parsed[path] = tuple(steps)
    return _parsed[path]

def field_name(declaration: Declaration) -> str:
    """The attribute of the record that a declaration starts from"""
    return parse_path(declaration.path)[0][1]


# === Slots: one place a nid is stored ===
Element = Tuple[Any, Any]  # (container, element)

class _Slot:
    # Data containers on the way to this slot, each with the element of it the
    # path went through; an element whose nid changes is re-keyed in its Data
    rekey: Tuple[Element, ...] = ()
    # The element of the last [*] in the reference's own path
    element: Optional[Element] = None

    def get(self) -> Any:
        raise NotImplementedError

    def set(self, value: Any) -> None:
        raise NotImplementedError

    def drop(self) -> bool:
        """Removes the nid outright where its container allows that. Returns whether it did."""
        return False

class _AttrSlot(_Slot):
    def __init__(self, holder, name: str):
        self.holder, self.name = holder, name

    def get(self):
        return getattr(self.holder, self.name)

    def set(self, value):
        setattr(self.holder, self.name, value)

class _ItemSlot(_Slot):
    def __init__(self, holder, key, replace_holder: Optional[Callable[[Any], None]]):
        self.holder, self.key = holder, key
        self.replace_holder = replace_holder

    def get(self):
        return self.holder[self.key]

    def set(self, value):
        if isinstance(self.holder, tuple):
            new_holder = list(self.holder)
            new_holder[self.key] = value
            self.holder = tuple(new_holder)
            self.replace_holder(self.holder)
        else:
            self.holder[self.key] = value

class _KeySlot(_Slot):
    def __init__(self, holder: dict, key):
        self.holder, self.key = holder, key

    def get(self):
        return self.key

    def set(self, value):
        old = self.key
        self.key = value
        if value in self.holder:
            # Swapped onto a key that already has an entry; that entry wins
            del self.holder[old]
            return
        items = list(self.holder.items())
        self.holder.clear()
        for k, v in items:
            self.holder[value if k == old else k] = v

    def drop(self):
        del self.holder[self.key]
        return True

class _AlliancePairSlot(_Slot):
    def __init__(self, teams, pair: Tuple[NID, NID], index: int):
        self.teams, self.pair, self.index = teams, pair, index

    def get(self):
        return self.pair[self.index]

    def set(self, value):
        new_pair = list(self.pair)
        new_pair[self.index] = value
        self.teams.alliance_pairs.discard(self.pair)
        self.pair = tuple(new_pair)
        self.teams.alliance_pairs.add(self.pair)

    def drop(self):
        self.teams.alliance_pairs.discard(self.pair)
        return True


def _locate(holder, steps: Tuple[Step, ...], rekey: Tuple[Element, ...],
            replace_holder: Optional[Callable[[Any], None]] = None,
            element: Optional[Element] = None) -> Iterator[_Slot]:
    """Every slot that the steps reach from holder"""
    kind, arg = steps[0]
    rest = steps[1:]
    if kind == _ATTR:
        if not rest:
            slot = _AttrSlot(holder, arg)
        else:
            child = getattr(holder, arg)
            if child is not None:
                yield from _locate(child, rest, rekey, lambda v: setattr(holder, arg, v), element)
            return
    elif kind == _INDEX:
        if not isinstance(holder, (list, tuple)) or len(holder) <= arg:
            return
        if not rest:
            slot = _ItemSlot(holder, arg, replace_holder)
        else:
            yield from _locate(holder[arg], rest, rekey, None, element)
            return
    elif kind == _EACH:
        for idx, child in enumerate(list(holder)):
            child_rekey = rekey + ((holder, child),) if isinstance(holder, Data) else rekey
            if not rest:
                slot = _ItemSlot(holder, idx, replace_holder)
                slot.rekey, slot.element = child_rekey, (holder, child)
                yield slot
            elif child is not None:
                def replace(v, holder=holder, idx=idx):
                    holder[idx] = v
                yield from _locate(child, rest, child_rekey, replace, (holder, child))
        return
    elif kind == _KEYS:
        for key in list(holder.keys()):
            slot = _KeySlot(holder, key)
            slot.rekey, slot.element = rekey, element
            yield slot
        return
    elif kind == _VALUES:
        for key in list(holder.keys()):
            if not rest:
                slot = _ItemSlot(holder, key, replace_holder)
                slot.rekey, slot.element = rekey, element
                yield slot
            elif holder[key] is not None:
                yield from _locate(holder[key], rest, rekey, None, element)
        return
    slot.rekey, slot.element = rekey, element
    yield slot


def _component_slots(components) -> Iterator[Tuple[_Slot, Target]]:
    for component in components:
        expose = component.expose
        if expose == CType.NewMultipleOptions:
            for key, option_type in component.options.items():
                yield from _typed_slots(component.value, key, option_type)
        elif expose:
            yield from _typed_slots(component, 'value', expose)

def _typed_slots(holder, key, expose) -> Iterator[Tuple[_Slot, Target]]:
    """Slots for one value whose type is described by an expose"""
    value = holder[key] if isinstance(holder, dict) else getattr(holder, key)
    if isinstance(expose, tuple):
        container, inner = expose
        target = COMPONENT_TARGETS.get(inner) if isinstance(inner, CType) else None
        if not target or not value:
            return
        if container == CType.List:
            steps = parse_path('x[*]')[1:]
        elif container in (CType.Dict, CType.FloatDict, CType.StringDict):
            steps = parse_path('x[*][0]')[1:]
        else:
            return
        for slot in _locate(value, steps, ()):
            yield slot, target
    else:
        target = COMPONENT_TARGETS.get(expose)
        if target:
            if isinstance(holder, dict):
                yield _ItemSlot(holder, key, None), target
            else:
                yield _AttrSlot(holder, key), target


# === Walking the database ===
@dataclass(eq=False)
class RefSite:
    owner_type: DType
    owner: Any  # The top-level record holding the reference
    where: str  # Path of the reference within the owner, for messages
    target: Target
    ref: Optional[Ref]  # None for component references
    record: Element  # (Data, sub-record) holding the field, or (catalog, owner)
    _slot: _Slot

    @property
    def value(self) -> Any:
        return self._slot.get()

    def set(self, value: Any) -> None:
        self._slot.set(value)
        for container, element in self._slot.rekey:
            _rekey(container, element)

    def clear(self) -> None:
        """Removes the reference: the list element or dict key that holds it, or the
        sub-record itself when the reference says so; otherwise sets it to None"""
        if self.ref and self.ref.on_clear == ClearPolicy.REMOVE_RECORD:
            _remove(*self.record)
        elif self._slot.drop():
            pass
        elif self._slot.element:
            _remove(*self._slot.element)
        else:
            self.set(None)

def _rekey(data: Data, element) -> None:
    d = data.as_dict()
    old_key = next((k for k, v in d.items() if v is element), None)
    if old_key is not None and old_key != element.nid:
        del d[old_key]
        d[element.nid] = element

def _remove(container, element) -> None:
    if isinstance(container, Data):
        container.delete(element)
        return
    for idx, e in enumerate(container):
        if e is element:
            del container[idx]
            return


def _record_sites(owner_type: DType, owner, record, record_elem: Element, rekey: Tuple[Element, ...],
                  prefix: str) -> Iterator[RefSite]:
    for declaration in REFERENCES.get(type(record), ()):
        where = prefix + declaration.path
        if isinstance(declaration, Ref):
            target = declaration.target
            if callable(target):
                target = target(record)
                if target is None:
                    continue
            for slot in _locate(record, parse_path(declaration.path), rekey):
                yield RefSite(owner_type, owner, where, target, declaration, record_elem, slot)
        elif isinstance(declaration, ComponentRefs):
            for slot, target in _component_slots(getattr(record, declaration.path)):
                yield RefSite(owner_type, owner, where, target, None, record_elem, slot)
        elif isinstance(declaration, Nested):
            steps = parse_path(declaration.path)
            container = getattr(record, steps[0][1])
            if steps[1:] != ((_EACH, None),):
                raise ValueError('Nested path must be "field[*]": %r' % declaration.path)
            for child in list(container):
                child_rekey = rekey + ((container, child),) if isinstance(container, Data) else rekey
                yield from _record_sites(owner_type, owner, child, (container, child), child_rekey, where + '.')

def iter_refs(db, owner_types: Iterable[DType] = OWNER_TYPES) -> Iterator[RefSite]:
    """Every reference in the database, whatever its value"""
    for owner_type in owner_types:
        data = catalog(db, owner_type)
        for owner in list(data):
            yield from _record_sites(owner_type, owner, owner, (data, owner), ((data, owner),), '')
        if owner_type == DType.TEAMS:
            for pair in list(data.alliance_pairs):
                for idx in range(2):
                    yield RefSite(owner_type, None, 'alliance_pairs', DType.TEAMS, None, (data, None),
                                  _AlliancePairSlot(data, pair, idx))

def find_referrers(db, target: Target, nid: NID) -> List[RefSite]:
    return [site for site in iter_refs(db) if site.target == target and site.value == nid]

def owners(sites: Iterable[RefSite]) -> Dict[DType, List[Any]]:
    """The records holding these references, by catalog, each listed once in order.
    Catalog-level references (team alliances) have no owner record and are left out."""
    result: Dict[DType, List[Any]] = {}
    seen: Set[int] = set()
    for site in sites:
        if site.owner is not None and id(site.owner) not in seen:
            seen.add(id(site.owner))
            result.setdefault(site.owner_type, []).append(site.owner)
    return result

def rewrite(db, target: Target, old_nid: NID, new_nid: NID) -> List[RefSite]:
    """Points every reference to old_nid at new_nid instead. Returns the references changed."""
    if not old_nid or old_nid == new_nid:
        return []
    sites = find_referrers(db, target, old_nid)
    for site in sites:
        # Re-reading the value: a swap onto a dict key that already existed
        # removed an entry another site might have pointed at
        if site.value == old_nid:
            site.set(new_nid)
    return sites

def clear(db, target: Target, nid: NID) -> List[RefSite]:
    """Removes every reference to nid. Returns the references removed."""
    if not nid:
        return []
    sites = find_referrers(db, target, nid)
    for site in sites:
        site.clear()
    return sites

def known_nids(db, resources, target: Target) -> Set[NID]:
    if isinstance(target, DType):
        return set(catalog(db, target).keys())
    elif isinstance(target, RType):
        return set(getattr(resources, target.name.lower()).keys())
    elif target == OtherType.MOVEMENT_TYPES:
        return set(db.mcost.unit_types)
    elif target == OtherType.TERRAIN_MOVEMENT_TYPES:
        return set(db.mcost.terrain_types)
    raise ValueError('Unknown reference target %s' % target)

def dangling(db, resources) -> List[RefSite]:
    """Every reference whose nid names nothing"""
    nids: Dict[Target, Set[NID]] = {}
    result = []
    for site in iter_refs(db):
        value = site.value
        if not value:
            continue
        if site.target not in nids:
            nids[site.target] = known_nids(db, resources, site.target)
        if value in nids[site.target]:
            continue
        if site.ref and site.ref.local and value in getattr(site.owner, site.ref.local):
            continue
        result.append(site)
    return result
