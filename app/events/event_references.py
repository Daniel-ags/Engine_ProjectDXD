"""
Where event scripts name a record, for warning the user before a rename or deletion.

The reference schema covers the database's own fields; event scripts are text,
so renames and deletions leave them as they are and only report what they
name. A command argument whose type names records of the target's kind and
holds the nid is a certain mention. Anywhere else, a line holding the nid as a
quoted string (Python code, an `if;` condition, an `{eval:}`) may name it: there
is no telling a unit from a portrait or a party of the same name there. A Python
event's `$` command lines are read like classic commands, but an argument
computed in Python names nothing knowable.
"""
from __future__ import annotations

from dataclasses import dataclass
import functools
import re
from typing import Dict, Iterator, List, Optional, Set, Tuple

from app.data.database.database_types import DatabaseType as DType
from app.data.database.reference_schema import Target
from app.data.resources.resource_types import ResourceType as RType
from app.events import event_commands
from app.events.event_version import EventVersion
from app.utilities.typing import NID

# What each event argument type names
KEYWORD_TARGETS: Dict[str, Tuple[Target, ...]] = {
    'Ability': (DType.ITEMS, DType.SKILLS),
    'AI': (DType.AI,),
    'Affinity': (DType.AFFINITIES,),
    'Chapter': (DType.LEVELS,),
    'DifficultyMode': (DType.DIFFICULTY_MODES,),
    'Event': (DType.EVENTS,),
    'Faction': (DType.FACTIONS,),
    'GlobalUnit': (DType.UNITS,),
    'GlobalUnitOrConvoy': (DType.UNITS,),
    'Item': (DType.ITEMS,),
    'ItemList': (DType.ITEMS,),
    'Klass': (DType.CLASSES,),
    'KlassList': (DType.CLASSES,),
    'Lore': (DType.LORE,),
    'MapAnim': (RType.ANIMATIONS,),
    'Music': (RType.MUSIC,),
    'Palette': (RType.COMBAT_PALETTES,),
    'Panorama': (RType.PANORAMAS,),
    'Party': (DType.PARTIES,),
    'Portrait': (RType.PORTRAITS, DType.UNITS),
    'PortraitNid': (RType.PORTRAITS,),
    'Position': (DType.UNITS,),  # A unit's nid stands for where that unit is
    'Skill': (DType.SKILLS,),
    'Sound': (RType.SFX,),
    'Speaker': (DType.UNITS,),
    'StatList': (DType.STATS,),
    'SupportRank': (DType.SUPPORT_RANKS,),
    'Tag': (DType.TAGS,),
    'Team': (DType.TEAMS,),
    'Tilemap': (RType.TILEMAPS,),
    'UniqueUnit': (DType.UNITS,),
    'Unit': (DType.UNITS,),
    'WeaponType': (DType.WEAPONS,),
}
# Argument types holding several nids, delimited by commas
LIST_TYPES = {'ItemList', 'KlassList'}
# Argument types holding nid, value pairs, delimited by commas: `STR,2,DEF,-1`
PAIR_LIST_TYPES = {'StatList'}

CONDITION_LINE = 0  # The line number of a mention in the event's trigger condition


@dataclass(frozen=True)
class EventMention:
    event: NID
    line: int  # Counted from 1, or CONDITION_LINE
    text: str
    certain: bool  # A command argument naming it, rather than a quoted string that may

    def label(self) -> str:
        where = 'condition' if self.line == CONDITION_LINE else 'line %d' % self.line
        return '%s, %s: %s%s' % (self.event, where, self.text.strip(),
                                 '' if self.certain else '  (may name it)')


@functools.lru_cache(maxsize=20000)
def _command(line: str, python: bool) -> Optional[event_commands.EventCommand]:
    """The event command a line holds, if any. Cached, since a project's lines are
    read again on every rename and most never change"""
    if python:
        if not line.strip().startswith('$'):
            return None
        from app.events.python_eventing.swscomp.swscompv1 import SWSCompilerV1
        from app.events.python_eventing.utils import event_command_from_pyev_tokens
        return event_command_from_pyev_tokens(SWSCompilerV1.parse_line(line))
    return event_commands.parse_text_to_command(line)[0]

def _named(command: event_commands.EventCommand, target: Target) -> Iterator[str]:
    """The nids command's arguments name of target's kind"""
    keywords = command.keywords + command.optional_keywords
    for keyword, kind in zip(keywords, command.get_keyword_types()):
        if target not in KEYWORD_TARGETS.get(kind, ()):
            continue
        value = command.parameters.get(keyword)
        if not isinstance(value, str):
            continue
        if kind in LIST_TYPES:
            yield from (part.strip() for part in value.split(','))
        elif kind in PAIR_LIST_TYPES:
            yield from (part.strip() for part in value.split(',')[::2])
        else:
            yield value

def find_mentions(db, target: Target, nid: Optional[NID]) -> List[EventMention]:
    """Every event line that names, or may name, the record of target's kind called nid"""
    if not nid:
        return []
    names: Set[str] = {nid}
    if target == DType.EVENTS and ' ' in nid:
        # An event is run by its name as often as by its nid, which is its level's
        # nid or Global, then its name. Read off the nid, since a renamed event's
        # old nid is in the catalog no longer
        names.add(nid.split(' ', 1)[1])
    quoted = re.compile('|'.join(r'''(['"])%s\%d''' % (re.escape(name), idx + 1)
                                 for idx, name in enumerate(sorted(names))))
    mentions = []
    for event in db.events:
        if event.condition and quoted.search(event.condition):
            mentions.append(EventMention(event.nid, CONDITION_LINE, event.condition, False))
        python = event.version() != EventVersion.EVENT
        for idx, line in enumerate(event.source.split('\n')):
            command = _command(line, python)
            if command and any(name in names for name in _named(command, target)):
                mentions.append(EventMention(event.nid, idx + 1, line, True))
            elif quoted.search(line):
                mentions.append(EventMention(event.nid, idx + 1, line, False))
    return mentions
