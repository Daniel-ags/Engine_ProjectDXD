"""
Finding, rewriting and clearing the references that reference_schema.py declares.

The schema says which fields of which records hold nids. This module walks
the database by it: find_referrers lists every reference to a record, rewrite
points them at a new nid when the record is renamed, clear removes them when
it is deleted, and dangling finds the ones that name nothing. check_schema
reports any field the schema leaves out.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Callable, Dict, Iterable, Iterator, List, Optional, Set, Tuple

from app.data.database.components import Component, ComponentType as CType
from app.data.database.database_types import DatabaseType as DType
from app.data.database.reference_schema import (COMPONENT_TARGETS, SCHEMA, ClearPolicy, ComponentRefs,
                                                Declaration, FieldDeclarations, Nested, OtherType, Ref,
                                                Target)
from app.data.resources.resource_types import ResourceType as RType
from app.utilities.data import Data
from app.utilities.typing import NID

SCHEMA_FILE = 'app/data/database/reference_schema.py'

# The movement cost grid and the minimap types are not lists of records
OWNER_TYPES: Tuple[DType, ...] = tuple(dtype for dtype in DType if dtype not in (DType.MCOST, DType.MINIMAP))


def catalog(db, dtype: DType) -> Data:
    return getattr(db, dtype.name.lower())


# === How the walk works ===
# iter_refs goes through every record of every catalog. For each record,
# _record_sites reads the record type's schema entry: each Ref's field and at
# make a path, parsed into steps, and _locate follows those steps through the
# record to every place
# a nid is stored, making a slot for each. A slot reads and writes the nid at
# its place without the caller knowing what holds it. Each slot is wrapped in a
# RefSite, which adds what the reference is (its target, its owner, a readable
# path) and is what find_referrers, rewrite, clear and dangling work on.


# === Paths ===
_TOKEN = re.compile(r'(\w+)|\[\*\]|\[(\d+)\]|\{key\}|\{\*\}|\.')
_ATTR, _EACH, _INDEX, _KEYS, _VALUES = 'attr', 'each', 'index', 'keys', 'values'
Step = Tuple[str, Any]

_parsed: Dict[str, Tuple[Step, ...]] = {}

def parse_path(path: str) -> Tuple[Step, ...]:
    """Splits a path into steps, each a (kind, argument) pair:
    'learned_skills[*][1]' -> (attr, 'learned_skills'), (each, None), (index, 1).
    The dots between attributes only separate them and make no step. Paths are
    parsed once and cached, since the walk reads the same few dozen paths for
    every record."""
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

def declarations(field_declarations: FieldDeclarations) -> List[Declaration]:
    """A field's declarations as a list: none for NOT_REF, one, or several Refs"""
    if field_declarations is None:
        return []
    if isinstance(field_declarations, list):
        return field_declarations
    return [field_declarations]


# === Slots: one place a nid is stored ===
# A path ends at slots, one per stored nid. Each kind of slot knows how to read
# and replace the nid in one kind of holder: an attribute, a list or tuple
# position or dict value, a dict key, or one end of a team alliance pair.
# rewrite and clear only ever call get, set and drop, so they work the same on
# every record shape.
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
    """A nid held in an attribute: unit.klass"""
    def __init__(self, holder, name: str):
        self.holder, self.name = holder, name

    def get(self):
        return getattr(self.holder, self.name)

    def set(self, value):
        setattr(self.holder, self.name, value)

class _ItemSlot(_Slot):
    """A nid held at a position of a list or tuple, or as a value of a dict:
    klass.turns_into[0], unit.learned_skills[0][1], level.music['player_phase'].

    A tuple can't be changed in place, so setting into one builds a new tuple
    and passes it to replace_holder, which stores it wherever the old tuple
    was held."""
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
    """A nid used as a dict key: the stat nids of klass.bases, the weapon type
    nids of unit.wexp_gain.

    Renaming a key rebuilds the dict so the entry keeps its position in the
    dict's order. Renaming onto a key the dict already has (a deletion swapping
    one stat for another the class also has) keeps the existing entry and drops
    this one."""
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
    """One end of a team alliance. Alliances are a set of (team, team) pairs held
    by the team catalog itself rather than by any team, so they have no path
    and iter_refs makes these slots directly. A set's members can't change in
    place, so setting swaps the old pair for a new one."""
    def __init__(self, teams, pair: Tuple[NID, NID], index: int):
        self.teams, self.pair, self.index = teams, pair, index

    def get(self):
        return self.pair[self.index]

    def set(self, value):
        new_pair = list(self.pair)
        new_pair[self.index] = value
        self.teams.alliance_pairs.discard(self.pair)
        self.pair = tuple(new_pair)
        # A team is always its own ally, so a pair swapped onto one team is dropped
        if self.pair[0] != self.pair[1]:
            self.teams.alliance_pairs.add(self.pair)

    def drop(self):
        self.teams.alliance_pairs.discard(self.pair)
        return True


def _locate(holder, steps: Tuple[Step, ...], rekey: Tuple[Element, ...],
            replace_holder: Optional[Callable[[Any], None]] = None,
            element: Optional[Element] = None) -> Iterator[_Slot]:
    """Every slot that the steps reach from holder.

    Takes the first step, then recurses on the rest from where it led; the last
    step makes the slot. Three things ride along the way:

    - rekey: each Data the walk passed through, paired with the element of it
      the walk went into. A Data is keyed by its elements' nids, and some nids
      are built from the very fields being rewritten (an event's nid includes
      its level's), so RefSite.set re-keys these elements after writing.
    - replace_holder: how to store a new value in place of the current holder,
      for when the slot's holder is a tuple and setting has to replace it.
    - element: the (container, element) of the last [*] passed. Clearing a
      reference removes this whole element, so a deleted item takes its whole
      [item, droppable] starting-item entry with it, not just the nid.

    A missing value ends the walk quietly: a None attribute holds no nid, and a
    list too short for an [n] step holds none at that position."""
    kind, arg = steps[0]
    rest = steps[1:]
    if kind == _ATTR:
        # 'klass': the attribute holds the nid. 'bonus.support_rank' (rest
        # remaining): move into the attribute's value and keep walking
        if not rest:
            slot = _AttrSlot(holder, arg)
        else:
            child = getattr(holder, arg)
            if child is not None:
                yield from _locate(child, rest, rekey, lambda v: setattr(holder, arg, v), element)
            return
    elif kind == _INDEX:
        # '[1]': one position of a list or tuple
        if not isinstance(holder, (list, tuple)) or len(holder) <= arg:
            return
        if not rest:
            slot = _ItemSlot(holder, arg, replace_holder)
        else:
            yield from _locate(holder[arg], rest, rekey, None, element)
            return
    elif kind == _EACH:
        # '[*]': every element. The loop runs over a copy, because clearing a
        # reference may remove elements from holder while the walk is suspended
        for idx, child in enumerate(list(holder)):
            child_rekey = rekey + ((holder, child),) if isinstance(holder, Data) else rekey
            if not rest:
                slot = _ItemSlot(holder, idx, replace_holder)
                slot.rekey, slot.element = child_rekey, (holder, child)
                yield slot
            elif child is not None:
                # A child that is a tuple is replaced at this index when one
                # of its nids is set
                def replace(v, holder=holder, idx=idx):
                    holder[idx] = v
                yield from _locate(child, rest, child_rekey, replace, (holder, child))
        return
    elif kind == _KEYS:
        # '{key}': every key of the dict is a nid. Nothing walks on from a key
        for key in list(holder.keys()):
            slot = _KeySlot(holder, key)
            slot.rekey, slot.element = rekey, element
            yield slot
        return
    elif kind == _VALUES:
        # '{*}': every value of the dict, as the nid itself or as the next holder
        for key in list(holder.keys()):
            if not rest:
                slot = _ItemSlot(holder, key, replace_holder)
                slot.rekey, slot.element = rekey, element
                yield slot
            elif holder[key] is not None:
                yield from _locate(holder[key], rest, rekey, None, element)
        return
    # The attribute and index cases fall through here with their one slot
    slot.rekey, slot.element = rekey, element
    yield slot


def _component_slots(components) -> Iterator[Tuple[_Slot, Target]]:
    """Slots for the nids in item and skill components, each with its target.

    Components aren't declared here one by one: each says what its value holds
    through its expose, and COMPONENT_TARGETS maps those types to targets. An
    expose is a single type (CType.Item), a (container, type) pair such as
    (CType.List, CType.Item), or NewMultipleOptions, whose value is a dict of
    named options that each have a type of their own."""
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
        # The same steps a declared path would take, minus its leading
        # attribute: the walk starts at the value itself
        if container == CType.List:
            steps = parse_path('x[*]')[1:]
        elif container in (CType.Dict, CType.FloatDict, CType.StringDict):
            # A dict-typed component value is a list of [key, value] pairs,
            # and only the keys are nids
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
    """One reference found in the database: a slot plus what it means. Sites are
    made fresh by each walk and are only good until the database next changes."""
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

    @property
    def entry(self) -> Element:
        """The (container, element) the reference is part of: the element of the
        last [*] in its path, or else the sub-record holding the field"""
        return self._slot.element or self.record

    @property
    def unique(self) -> bool:
        """Whether no two elements of the reference's container may name the same record"""
        if self.ref:
            return self.ref.unique
        # A list or dict in a component; a component holding one nid is in no list
        return self._slot.element is not None

    @property
    def listed(self) -> bool:
        """Whether a deletion warning should name this reference's owner"""
        return self.owner is not None and (self.ref is None or self.ref.listed)

    def set(self, value: Any) -> None:
        self._slot.set(value)
        # Any Data on the way to the slot whose element's nid was built from
        # the value just written now has that element under a stale key
        for container, element in self._slot.rekey:
            _rekey(container, element)

    def clear(self, fallback: Optional[NID] = None) -> None:
        """Removes the reference: the list element or dict key that holds it, or the
        sub-record itself when the reference says so; otherwise sets it to None.
        A reference that must name something is pointed at fallback instead."""
        policy = self.ref.on_clear if self.ref else ClearPolicy.AUTO
        if policy == ClearPolicy.REPLACE:
            self.set(fallback)
        elif policy == ClearPolicy.REMOVE_RECORD:
            _remove(*self.record)
        elif self._slot.drop():
            pass
        elif self._slot.element:
            _remove(*self._slot.element)
        else:
            self.set(None)

def _rekey(data: Data, element) -> None:
    """Files element under its current nid in data's lookup dict. The dict's key
    is found by identity, since the element's nid is what changed"""
    d = data.as_dict()
    old_key = next((k for k, v in d.items() if v is element), None)
    if old_key is not None and old_key != element.nid:
        del d[old_key]
        d[element.nid] = element

def _remove(container, element) -> None:
    """Removes element from a Data or a list, finding it by identity"""
    if isinstance(container, Data):
        container.delete(element)
        return
    for idx, e in enumerate(container):
        if e is element:
            del container[idx]
            return


def _record_sites(owner_type: DType, owner, record, record_elem: Element, rekey: Tuple[Element, ...],
                  prefix: str) -> Iterator[RefSite]:
    """The references in record, by its type's schema entry, and in the
    sub-records its Nested fields hold.

    owner is the top-level catalog record all of these belong to, which is what
    the editor records for undo and lists in deletion warnings. record_elem is
    the (container, record) of the record actually holding the fields, which
    ClearPolicy.REMOVE_RECORD removes. prefix builds the readable path of
    sub-record references, like 'units[*].team'."""
    for field, field_declarations in SCHEMA.get(type(record), {}).items():
        for declaration in declarations(field_declarations):
            if isinstance(declaration, Ref):
                target = declaration.target
                if callable(target):
                    # A resolver: what this field names depends on another
                    # field of this record, and may be nothing at all
                    target = target(record)
                    if target is None:
                        continue
                path = field + declaration.at
                for slot in _locate(record, parse_path(path), rekey):
                    yield RefSite(owner_type, owner, prefix + path, target, declaration, record_elem, slot)
            elif isinstance(declaration, ComponentRefs):
                for slot, target in _component_slots(getattr(record, field)):
                    yield RefSite(owner_type, owner, prefix + field, target, None, record_elem, slot)
            elif isinstance(declaration, Nested):
                # Each sub-record is walked by its own type's entry, under the
                # same owner
                container = getattr(record, field)
                for child in list(container):
                    child_rekey = rekey + ((container, child),) if isinstance(container, Data) else rekey
                    yield from _record_sites(owner_type, owner, child, (container, child), child_rekey,
                                             prefix + field + '[*].')

def iter_refs(db, owner_types: Iterable[DType] = OWNER_TYPES) -> Iterator[RefSite]:
    """Every reference in the database, whatever its value"""
    for owner_type in owner_types:
        data = catalog(db, owner_type)
        for owner in list(data):
            # The catalog itself is the first Data on the way: a record whose
            # nid is built from a field it holds is re-keyed in its catalog
            yield from _record_sites(owner_type, owner, owner, (data, owner), ((data, owner),), '')
        # Alliances live on the team catalog, not on any team, so no
        # declaration reaches them
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

def removed_records(sites: Iterable[RefSite]) -> List[Tuple[DType, Any]]:
    """The catalog records that clearing these references removes outright, like a
    deleted level's events, by catalog, each listed once"""
    result: List[Tuple[DType, Any]] = []
    seen: Set[int] = set()
    for site in sites:
        if site.ref and site.ref.on_clear == ClearPolicy.REMOVE_RECORD and site.record[1] is site.owner \
                and id(site.owner) not in seen:
            seen.add(id(site.owner))
            result.append((site.owner_type, site.owner))
    return result

def rewrite(db, target: Target, old_nid: NID, new_nid: NID) -> List[RefSite]:
    """Points every reference to old_nid at new_nid instead. Returns the references changed.

    In a unique list that already names new_nid, as a swap onto a tag the class
    also has makes, the element naming old_nid is removed instead, so the list
    keeps the one it had."""
    if not old_nid or old_nid == new_nid:
        return []
    sites = find_referrers(db, target, old_nid)
    taken = set()  # The unique lists already naming new_nid
    if any(site.unique for site in sites):
        taken = {id(site.entry[0]) for site in find_referrers(db, target, new_nid) if site.unique}
    for site in sites:
        # Re-reading the value: a swap onto a dict key that already existed
        # removed an entry another site might have pointed at
        if site.value == old_nid:
            if site.unique and id(site.entry[0]) in taken:
                _remove(*site.entry)
            else:
                site.set(new_nid)
                if site.unique:
                    taken.add(id(site.entry[0]))
    return sites

def clear(db, target: Target, nid: NID, fallback: Optional[NID] = None) -> List[RefSite]:
    """Removes every reference to nid, pointing those that must name something at
    fallback. Returns the references removed."""
    if not nid:
        return []
    sites = find_referrers(db, target, nid)
    for site in sites:
        site.clear(fallback)
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


# === Checking the schema ===
def schema_problems(record_type: type, fields: Iterable[str]) -> List[str]:
    """Where the schema's entry for a record type disagrees with the fields the
    record has, each as a message saying what to change"""
    name = record_type.__name__
    fields = list(fields)
    entry = SCHEMA.get(record_type)
    if entry is None:
        return ['%s has no entry in %s, so renames and deletions never look inside it. '
                'Add one listing each of its fields (%s), as a Ref if it holds a nid or NOT_REF if not.'
                % (name, SCHEMA_FILE, ', '.join(fields))]
    problems = []
    for field in fields:
        if field not in entry:
            problems.append("%s.%s is not in %s, so renames and deletions will not update it. "
                            "Add it to %s's entry: '%s': Ref(<what it names>) if it holds a nid, "
                            "or '%s': NOT_REF if it does not."
                            % (name, field, SCHEMA_FILE, name, field, field))
    for field in entry:
        if field not in fields:
            problems.append("%s's entry in %s lists %s, which %s does not have. Remove it."
                            % (name, SCHEMA_FILE, field, name))
    return problems

def check_schema(db) -> List[str]:
    """Problems with the schema for the records in db, each as a message saying
    what to change. Each record type is checked once, by the first record of it
    found, down through the sub-records of Nested fields."""
    checked: Set[type] = set()
    problems: List[str] = []

    def check(record):
        if type(record) not in checked:
            checked.add(type(record))
            # Items and skills also hold each component under its own nid,
            # beside their components field, which ComponentRefs covers
            fields = [name for name, value in vars(record).items() if not isinstance(value, Component)]
            problems.extend(schema_problems(type(record), fields))
        for field, field_declarations in SCHEMA.get(type(record), {}).items():
            if any(isinstance(declaration, Nested) for declaration in declarations(field_declarations)):
                for child in getattr(record, field):
                    check(child)

    for owner_type in OWNER_TYPES:
        for record in catalog(db, owner_type):
            check(record)
    return problems
