"""
The editor's side of renaming and deleting a record that others name.

Which records name which lives in app.data.database.references; this module
only shows the user what a deletion would touch and carries out their choice.
"""
from __future__ import annotations

import importlib
from types import SimpleNamespace
from typing import Any, Callable, List, Optional

from PyQt5.QtCore import QAbstractListModel, Qt

from app.data.database import references
from app.data.database.database_types import DatabaseType as DType
from app.editor.custom_widgets import ObjBox
from app.editor.edit_history import HISTORY
from app.extensions.custom_gui import ComboBox, DeletionDialog, DeletionTab
from app.utilities.typing import NID

# How to list the records of each catalog in a deletion warning, as module and class
OWNER_MODELS = {
    DType.ITEMS: ('app.editor.item_editor.item_model', 'ItemModel'),
    DType.SKILLS: ('app.editor.skill_editor.skill_model', 'SkillModel'),
    DType.UNITS: ('app.editor.unit_editor.unit_model', 'UnitModel'),
    DType.CLASSES: ('app.editor.class_editor.class_model', 'ClassModel'),
    DType.LEVELS: ('app.editor.global_editor.level_menu', 'LevelModel'),
    DType.AI: ('app.editor.ai_editor.ai_model', 'AIModel'),
    DType.TERRAIN: ('app.editor.terrain_editor.terrain_model', 'TerrainModel'),
    DType.WEAPONS: ('app.editor.weapon_editor.weapon_model', 'WeaponModel'),
    DType.AFFINITIES: ('app.editor.support_editor.affinity_model', 'AffinityModel'),
    DType.FACTIONS: ('app.editor.faction_editor.faction_model', 'FactionModel'),
    DType.PARTIES: ('app.editor.party_editor.party_model', 'PartyModel'),
    DType.TEAMS: ('app.editor.team_editor.team_model', 'TeamModel'),
}


class NidListModel(QAbstractListModel):
    """Lists records by nid, for catalogs without a model of their own"""
    def __init__(self, data: List[Any], parent=None):
        super().__init__(parent)
        self._data = data

    def rowCount(self, parent=None):
        return len(self._data)

    def data(self, index, role):
        if index.isValid() and role == Qt.DisplayRole:
            return str(self._data[index.row()].nid)
        return None


def nid_box(title: str, nids: List[NID], parent) -> ObjBox:
    """A choice of one of these nids, as a swap for a target whose nids name no
    records, like the movement types"""
    return ObjBox(title, NidListModel, lambda: [SimpleNamespace(nid=nid) for nid in nids], parent)


def owner_model(owner_type: DType):
    if owner_type in OWNER_MODELS:
        module, name = OWNER_MODELS[owner_type]
        return getattr(importlib.import_module(module), name)
    return NidListModel


def deletion_tabs(sites: List[references.RefSite], kind: str, nid: NID) -> List[DeletionTab]:
    tabs = []
    for owner_type, records in references.owners(site for site in sites if site.listed).items():
        label = owner_type.name.replace('_', ' ').title()
        msg = "Deleting %s <b>%s</b> would affect these %s." % (kind, nid, label.lower())
        tabs.append(DeletionTab(records, owner_model(owner_type), msg, label))
    return tabs


def check_delete(target: references.Target, nid: NID, kind: str, parent,
                 make_swap_box: Optional[Callable[[], ComboBox]] = None, fallback: Optional[NID] = None,
                 extra_tabs: List[DeletionTab] = (), on_swap: Optional[Callable[[NID], None]] = None) -> bool:
    """
    Shows the user every record that names nid and asks whether to go ahead.
    With a swap box, those references are pointed at the record the user picks;
    without one they are removed, and those that must name something take fallback.
    References not worth listing are removed without asking.
    extra_tabs and on_swap cover references kept outside the database (in resources).
    Returns whether the deletion should go ahead.
    """
    sites = references.find_referrers(HISTORY.db, target, nid)
    tabs = deletion_tabs(sites, kind, nid) + list(extra_tabs)
    if not tabs:
        HISTORY.clear_references(target, nid, fallback)
        return True
    if make_swap_box:
        swap, ok = DeletionDialog.get_swap(tabs, make_swap_box(), parent)
        if not ok:
            return False
        HISTORY.rewrite(target, nid, swap.nid)
        if on_swap:
            on_swap(swap.nid)
        # Whatever the swap could not take over, such as an entry of a dict
        # that already has one for the swap, goes with the record
        HISTORY.clear_references(target, nid, fallback)
        return True
    if not DeletionDialog.inform(tabs, parent):
        return False
    HISTORY.clear_references(target, nid, fallback)
    return True
