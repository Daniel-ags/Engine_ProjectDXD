"""
Undo and redo for edits to the database, one record at a time.

The history never snapshots the whole database. It records three kinds of delta:

- RecordChange: a record's saved form before and after an edit. Undo restores
  the fields in place on the same object, so anything holding the record keeps
  holding the right one.
- CatalogChange: a catalog's members and order (object references, not copies),
  plus its categories and, for teams, the alliances. Creating, deleting,
  duplicating, pasting and reordering are all changes of membership.

Editors bind the record they are showing. At each commit point (a change of
selection or of focus, a structural edit, closing, undo) the history compares
each bound record with its baseline and each catalog's members with the last
ones it saw, and turns whatever differs into one change set. Records changed
without being shown, like those a rename cascades into, are recorded by
running the change inside `modifying`; rewrite and clear here do that for the
reference cascades.

After every change set it records, undoes or redoes, the history tells its
listeners, so every open view can show the database again. A change set
remembers its origin, the view that made it and so already shows it.

Set LT_EDITOR_CHECK=1 to log any record that changed without being recorded.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
import logging
import os
from typing import Any, Callable, Dict, Iterable, Iterator, List, Optional, Tuple

from app.data.category import CategorizedCatalog
from app.data.database import references
from app.data.database.constants import Constant
from app.data.database.database import DB
from app.data.database.teams import TeamCatalog
from app.utilities.data import Data
from app.utilities.typing import NID

MAX_CHANGE_SETS = 100
CHECK_UNRECORDED = bool(os.environ.get('LT_EDITOR_CHECK'))


def saved(record) -> Any:
    """A record's saved form, sharing nothing with the record"""
    return copy.deepcopy(record.save())

def restore_in_place(record, saved_form) -> None:
    if isinstance(record, Constant):
        # A constant saves only its value; the rest is fixed by the engine
        record.value = copy.deepcopy(saved_form[1])
        return
    fresh = type(record).restore(copy.deepcopy(saved_form))
    record.__dict__.clear()
    record.__dict__.update(fresh.__dict__)

def rebuild_keys(data: Data) -> None:
    """Re-keys a Data from its members' current nids, keeping their order"""
    members = list(data)
    data.clear()
    for member in members:
        data.append(member)


@dataclass(eq=False)
class RecordChange:
    catalog: Data
    record: Any
    before: Any
    after: Any

    def undo(self):
        restore_in_place(self.record, self.before)

    def redo(self):
        restore_in_place(self.record, self.after)


@dataclass(frozen=True)
class CatalogState:
    members: Tuple[Any, ...]
    extras: Tuple[Tuple[str, Any], ...]  # Catalog-level attributes, by name

    @classmethod
    def of(cls, data: Data) -> CatalogState:
        extras = []
        if isinstance(data, CategorizedCatalog):
            extras.append(('categories', {nid: list(path) for nid, path in data.categories.items()}))
        if isinstance(data, TeamCatalog):
            extras.append(('alliance_pairs', frozenset(data.alliance_pairs)))
        return cls(tuple(data), tuple(extras))

    def same_as(self, other: CatalogState) -> bool:
        return len(self.members) == len(other.members) and \
            all(a is b for a, b in zip(self.members, other.members)) and \
            self.extras == other.extras

    def apply_to(self, data: Data) -> None:
        data.clear()
        for member in self.members:
            data.append(member)
        for name, value in self.extras:
            if name == 'categories':
                # In place: tabs hold on to the categories object
                data.categories.clear()
                data.categories.update({nid: list(path) for nid, path in value.items()})
            elif name == 'alliance_pairs':
                data.alliance_pairs = set(value)


@dataclass(eq=False)
class CatalogChange:
    catalog: Data
    before: CatalogState
    after: CatalogState

    def undo(self):
        self.before.apply_to(self.catalog)

    def redo(self):
        self.after.apply_to(self.catalog)


Delta = Any  # RecordChange | CatalogChange


@dataclass(eq=False)
class ChangeSet:
    label: str
    origin: Any = None  # The view that made these edits, if one did
    deltas: List[Delta] = field(default_factory=list)

    def catalogs(self) -> List[Data]:
        seen = []
        for delta in self.deltas:
            if not any(delta.catalog is c for c in seen):
                seen.append(delta.catalog)
        return seen

    def undo(self):
        for delta in reversed(self.deltas):
            delta.undo()
        for data in self.catalogs():
            rebuild_keys(data)

    def redo(self):
        for delta in self.deltas:
            delta.redo()
        for data in self.catalogs():
            rebuild_keys(data)


class EditHistory:
    def __init__(self, db):
        self.db = db
        self._undo: List[ChangeSet] = []
        self._redo: List[ChangeSet] = []
        self._open: List[ChangeSet] = []  # Nested change sets merge into the outermost
        # id(owner) -> id(record) -> (catalog, record, baseline). An owner is
        # whatever shows the records, usually an editor tab
        self._bound: Dict[int, Dict[int, Tuple[Data, Any, Any]]] = {}
        self._catalogs: Dict[int, Tuple[Data, CatalogState]] = {}
        self._shadow: Dict[int, dict] = {}  # LT_EDITOR_CHECK only
        self._listeners: List[Callable[[Any], None]] = []
        self.clear()

    # === Lifetime ===
    def clear(self):
        """Forgets everything. Called when a project loads."""
        self._undo.clear()
        self._redo.clear()
        self._open.clear()
        self._bound.clear()
        self._catalogs = {id(data): (data, CatalogState.of(data)) for data in self.watched_catalogs()}
        if CHECK_UNRECORDED:
            self._shadow = self._saved_records()

    def watched_catalogs(self) -> List[Data]:
        return [references.catalog(self.db, dtype) for dtype in references.OWNER_TYPES]

    def is_watched(self, data: Data) -> bool:
        return id(data) in self._catalogs

    # === Listening ===
    def listen(self, listener: Callable[[Any], None]) -> None:
        """Calls listener(origin) after each change set is recorded, undone or redone.
        origin is the view that made the change and already shows it, or None when
        every view needs to show the database again, as after an undo."""
        self._listeners.append(listener)

    def unlisten(self, listener: Callable[[Any], None]) -> None:
        self._listeners.remove(listener)

    def _announce(self, origin) -> None:
        for listener in self._listeners[:]:
            listener(origin)

    # === Recording ===
    def bind(self, record, data: Data, owner=None) -> None:
        """Starts watching a record an editor shows, in place of the one its owner showed
        before. Without an owner the record stays bound until the history is cleared.
        Commits whatever changed first.

        Bind once the record is on show: some forms tidy a record as they show it
        (a terrain's color loses its alpha), and that is not an edit to undo."""
        watched = record is not None and self.is_watched(data)
        if watched and CHECK_UNRECORDED:
            self._shadow[id(record)] = saved(record)
        self.commit(origin=owner)
        bindings = self._bound.setdefault(id(owner), {})
        if owner is not None:
            bindings.clear()
        if watched:
            bindings[id(record)] = (data, record, saved(record))

    def bind_all(self, records: Iterable[Any], data: Data, owner) -> None:
        """Watches every one of these records at once"""
        self.commit(origin=owner)
        bindings = self._bound.setdefault(id(owner), {})
        bindings.clear()
        if self.is_watched(data):
            for record in records:
                bindings[id(record)] = (data, record, saved(record))

    def unbind(self, owner) -> None:
        """Stops watching what owner shows, as when its editor closes"""
        self.commit(origin=owner)
        self._bound.pop(id(owner), None)

    def _is_bound(self, record) -> bool:
        return any(id(record) in bindings for bindings in self._bound.values())

    def _all_bound(self) -> Iterator[Tuple[Dict[int, Tuple[Data, Any, Any]], int]]:
        for bindings in self._bound.values():
            for key in list(bindings):
                yield bindings, key

    def begin(self, label: str = 'Edit', origin=None) -> None:
        if not self._open:
            change_set = ChangeSet(label, origin)
            self._open.append(change_set)
            # Whatever changed since the last commit belongs with this edit
            self._collect(change_set)
        else:
            self._open.append(self._open[0])

    def end(self) -> None:
        change_set = self._open.pop()
        if self._open:
            return
        self._collect(change_set)
        if change_set.deltas:
            self._push(change_set)
        if CHECK_UNRECORDED:
            self._check_unrecorded(change_set)
        if change_set.deltas:
            self._announce(change_set.origin)

    def change_set(self, label: str = 'Edit', origin=None) -> _ChangeSetContext:
        """with history.change_set('Delete Iron Sword'): ... records everything inside as one undo step.
        origin is the view making the change, when it shows the change by itself."""
        return _ChangeSetContext(self, label, origin)

    def commit(self, label: str = 'Edit', origin=None) -> None:
        """Records whatever changed since the last commit as one undo step"""
        if self._open:
            return  # The open change set picks it up when it ends
        self.begin(label, origin)
        self.end()

    def modifying(self, records: Iterable[Tuple[Any, Data]]) -> _ModifyingContext:
        """with history.modifying([(record, catalog), ...]): changes records nobody has bound"""
        return _ModifyingContext(self, list(records))

    # === References ===
    def rewrite(self, target: references.Target, old_nid: NID, new_nid: NID) -> List[references.RefSite]:
        """references.rewrite, recorded"""
        sites = references.find_referrers(self.db, target, old_nid)
        with self.change_set('Rename %s' % old_nid), self.modifying(self._owners(sites)):
            return references.rewrite(self.db, target, old_nid, new_nid)

    def clear_references(self, target: references.Target, nid: NID,
                         fallback: Optional[NID] = None) -> List[references.RefSite]:
        """references.clear, recorded"""
        sites = references.find_referrers(self.db, target, nid)
        with self.change_set('Delete %s' % nid), self.modifying(self._owners(sites)):
            return references.clear(self.db, target, nid, fallback)

    def rename(self, data: Data, record, new_nid: NID,
               cascade: Optional[Callable[[NID, NID], Any]] = None) -> None:
        """Renames a record in its catalog, and with cascade(old_nid, new_nid) whatever
        names it, as one undo step"""
        old_nid = record.nid
        if new_nid == old_nid:
            return
        with self.change_set('Rename %s' % old_nid), self.modifying([(record, data)]):
            if cascade:
                cascade(old_nid, new_nid)
            data.update_nid(record, new_nid)

    def _owners(self, sites: List[references.RefSite]) -> Iterator[Tuple[Any, Data]]:
        for owner_type, records in references.owners(sites).items():
            data = references.catalog(self.db, owner_type)
            for record in records:
                yield record, data

    # === Undo ===
    def can_undo(self) -> bool:
        return bool(self._undo)

    def can_redo(self) -> bool:
        return bool(self._redo)

    def undo(self, floor: Optional[ChangeSet] = None) -> Optional[ChangeSet]:
        """Undoes the last change set, unless that is floor (a mark): an editor
        steps back through its own edits only"""
        self.commit()
        if not self._undo or self._undo[-1] is floor:
            return None
        change_set = self._undo.pop()
        change_set.undo()
        self._redo.append(change_set)
        self._rebaseline()
        self._announce(None)
        return change_set

    def redo(self) -> Optional[ChangeSet]:
        self.commit()
        if not self._redo:
            return None
        change_set = self._redo.pop()
        change_set.redo()
        self._undo.append(change_set)
        self._rebaseline()
        self._announce(None)
        return change_set

    def mark(self) -> ChangeSet | None:
        """A point to come back to with undo_to"""
        self.commit()
        return self._undo[-1] if self._undo else None

    def undo_to(self, mark: Optional[ChangeSet]) -> None:
        """Puts everything back as it was at mark and forgets what came after.
        A mark that history has since dropped off its end undoes as far as
        history goes."""
        self.commit()
        changed = False
        if mark is not None and any(change_set is mark for change_set in self._redo):
            # Undone past the mark: redo up to it
            while self._undo[-1:] != [mark]:
                change_set = self._redo.pop()
                change_set.redo()
                self._undo.append(change_set)
                changed = True
        else:
            while self._undo and self._undo[-1] is not mark:
                self._undo.pop().undo()
                changed = True
        self._redo.clear()
        self._rebaseline()
        if changed:
            self._announce(None)

    # === Internals ===
    def _push(self, change_set: ChangeSet) -> None:
        self._undo.append(change_set)
        del self._undo[:-MAX_CHANGE_SETS]
        self._redo.clear()

    def _collect(self, change_set: ChangeSet) -> None:
        recorded = set()
        for bindings, key in self._all_bound():
            data, record, baseline = bindings[key]
            now = saved(record)
            if now != baseline:
                if key not in recorded:  # Two owners may show the same record
                    change_set.deltas.append(RecordChange(data, record, baseline, now))
                    recorded.add(key)
                bindings[key] = (data, record, now)
        for key, (data, state) in list(self._catalogs.items()):
            now = CatalogState.of(data)
            if not now.same_as(state):
                change_set.deltas.append(CatalogChange(data, state, now))
                self._catalogs[key] = (data, now)

    def _rebaseline(self) -> None:
        for bindings, key in self._all_bound():
            data, record, _ = bindings[key]
            bindings[key] = (data, record, saved(record))
        for key, (data, _) in list(self._catalogs.items()):
            self._catalogs[key] = (data, CatalogState.of(data))
        if CHECK_UNRECORDED:
            self._shadow = self._saved_records()

    def _saved_records(self) -> Dict[int, dict]:
        return {id(record): saved(record) for data in self.watched_catalogs() for record in data}

    def _check_unrecorded(self, change_set: ChangeSet) -> None:
        recorded = {id(delta.record) for delta in change_set.deltas if isinstance(delta, RecordChange)}
        now = self._saved_records()
        for data in self.watched_catalogs():
            for record in data:
                key = id(record)
                if key in self._shadow and key not in recorded and now[key] != self._shadow[key]:
                    logging.warning("LT_EDITOR_CHECK: %s %s changed without being recorded",
                                    type(record).__name__, record.nid)
        self._shadow = now


class _ChangeSetContext:
    def __init__(self, history: EditHistory, label: str, origin):
        self.history, self.label, self.origin = history, label, origin

    def __enter__(self):
        self.history.begin(self.label, self.origin)
        return self

    def __exit__(self, *exc):
        self.history.end()
        return False


class _ModifyingContext:
    def __init__(self, history: EditHistory, records: List[Tuple[Any, Data]]):
        self.history = history
        # Resources are not recorded yet
        self.records = [(record, data) for record, data in records if history.is_watched(data)]

    def __enter__(self):
        self.history.begin()
        self.before = [(record, data, saved(record)) for record, data in self.records]
        return self

    def __exit__(self, *exc):
        change_set = self.history._open[0]
        for record, data, before in self.before:
            if self.history._is_bound(record):
                continue  # A bound record is diffed against its baseline when the set ends
            after = saved(record)
            if after != before:
                change_set.deltas.append(RecordChange(data, record, before, after))
        self.history.end()
        return False


# The editor's one history, of the one database it edits
HISTORY = EditHistory(DB)
