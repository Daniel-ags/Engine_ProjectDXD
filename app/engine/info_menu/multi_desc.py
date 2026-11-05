from __future__ import annotations

from app.engine.utils.ltcache import ltcached
import logging

from app.engine import engine, item_system, skill_system, text_funcs
from app.engine.dialog import DialogState
from app.engine.graphics.text.text_renderer import render_text
from app.engine.help_menu import HelpDialog, ItemHelpDialog, SkillHelpDialog
from app.engine.info_menu.multi_desc_utils import InfoSource, Page, PageType, RawPages
from app.utilities.enums import HAlignment

from typing import Optional, TYPE_CHECKING
if TYPE_CHECKING:
    from app.utilities.typing import NID
    from app.engine.objects.item import ItemObject
    from app.engine.objects.skill import SkillObject
    from app.engine.objects.unit import UnitObject

@ltcached
def build_dialog_list(obj: SkillObject | ItemObject,
                        page_type: PageType,
                        unit: Optional[UnitObject]=None) -> list[HelpDialog]:
    """
        Builds a tree of HelpDialog objects from the root object.
        Ltcached for better latency while scrolling through units.
        Args:
            obj: The object that the player hovered on and pressed R to initiate the help dialog.
            page_type: The type of page that the initial object corresponds to.
            unit: The unit used in the context of this help dialog.
    """
    root: InfoSource = InfoSource(obj, page_type)
    root_box = get_dlg_box(root, page_type, unit, is_first=True)
    return [root_box] + _build_further_pages(root, page_type, unit)

def _build_further_pages(root: InfoSource, page_type: PageType, unit: Optional[UnitObject]) -> list[HelpDialog]:
    """The help boxes of every page the root's multi desc components lead to, without the root's own."""
    boxes: list[HelpDialog] = []
    local_seen: set[Page] = {(root.nid, page_type)}

    for nid, p_type in _collect(root, page_type, unit):
        if nid is None:
            continue
        if (nid, p_type) in local_seen:
            continue
        
        box = get_dlg_box(InfoSource(nid, p_type), p_type, unit)
        if box:
            boxes.append(box)
        local_seen.add((nid, p_type))
    
    return boxes

def _collect(entry: InfoSource | NID, page_type: PageType, unit: Optional[UnitObject], visited:Optional[set[Page]]=None) -> list[Page]:
    """Recursively collect all pages from the first entry."""
    
    visited = visited or set()
    stack: list[Page] = []
        
    # coerce NID into an InfoSource so we exclusively deal with InfoSource objects inside the tree
    # well, if the entry is somehow None, there's no point in trying to eke out more nodes from it
    # so just return the stack
    if not isinstance(entry, InfoSource):
        entry: InfoSource = InfoSource(entry, page_type)
        if entry.type is None:
            return stack
    
    # if the entry has already been seen, then it will build the same tree, so just return the stack
    entry_id = (entry.nid, page_type)
    if entry_id in visited:
        return stack
    visited.add(entry_id)
    
    pages: list[RawPages] = _get_pages(entry, page_type, unit)
    
    for nid_list, page_type in pages:
        # solves python shadowing shenanigans!
        current_page_type = PageType(page_type) if page_type else page_type
        for nid in nid_list:
            if nid is None:
                continue
            stack.append((nid, current_page_type))
            stack.extend(_collect(nid, current_page_type, unit, visited))
        
    return stack

def _get_pages(source: InfoSource, page_type: PageType, unit: Optional[UnitObject]) -> list[RawPages]:
    """Returns the raw pages of the obj sourced from hooks, including itself."""
    pages: list[RawPages] = [([source.nid], page_type.value)]
    
    if source.type is None:
        return pages
    
    if page_type == PageType.SKILL:
        pages.extend(skill_system.get_multi_desc(source, unit))
    elif page_type == PageType.ITEM:
        pages.extend(item_system.get_multi_desc(source, unit))
    else: # if ever anything else gains pages, need to update logic
        pass
    
    return pages

def get_dlg_box(source: InfoSource, page_type: PageType, unit: Optional[UnitObject], is_first:bool=False) -> Optional[HelpDialog]:
    """
        Get the help box from a live instance of the object.
        Won't work in all cases, since we could be using eval.
    """
    if source.type is None:
        logging.warning(f"Cannot find Source: {source.origin} for Unit: {unit} in database, skipping...")
        return None
        
    if page_type == PageType.ITEM:
        if item_system.is_weapon(unit, source) or item_system.is_spell(unit, source):
            return ItemHelpDialog(source, first=is_first, unit_override=unit)
        else:
            return HelpDialog(text_funcs.translate_and_text_evaluate(source.desc, unit=unit, self=source))
    elif page_type == PageType.SKILL:
        return SkillHelpDialog(source, first=is_first, unit_override=unit)
    # TODO: Someday make specialized HelpDialog classes for these? Requires some refactors in other places.
    elif page_type == PageType.LORE:
        return HelpDialog(text_funcs.translate_and_text_evaluate(source.desc, unit=unit), source.name)
    elif page_type == PageType.AFFINITY:
        return HelpDialog(text_funcs.translate_and_text_evaluate(source.desc))
    elif page_type == PageType.KLASS:
        return HelpDialog(text_funcs.translate_and_text_evaluate(source.desc, unit=unit), source.name)
    else:
        return HelpDialog(text_funcs.translate_and_text_evaluate(source.desc, unit=unit), name=source.name)

def draw_page_number(surf, help_box: HelpDialog, top_left: tuple[int, int], box_at_top: bool, page: int, num_pages: int) -> None:
    """Numbers the page of a help box drawn at top_left, once the box's text has started."""
    if help_box.dlg and help_box.dlg.state == DialogState.TRANSITION_IN:
        return
    x = top_left[0] + help_box.get_width() - 16
    y = top_left[1] + help_box.get_height() - 8 if box_at_top else top_left[1] - 4
    render_text(surf, ['small-yellow'], ['%d/%d' % (page + 1, num_pages)], [], (x, y), HAlignment.RIGHT)

class PagedHelpDialog(HelpDialog):
    """
    The help box of a menu option: the option's own box, followed by the pages
    the object's multi desc components lead to.

    Menus build the help box of every option up front, and laying out a help box is
    slow, so the further pages are only built once the help box is first shown.
    """
    def __init__(self, first_page: HelpDialog, obj: SkillObject | ItemObject, page_type: PageType, unit: Optional[UnitObject]):
        self.first_page = first_page
        self.obj = obj
        self.page_type = page_type
        self.unit = unit
        self.pages: Optional[list[HelpDialog]] = None
        self.page = 0
        self.last_time = 0

    def get_pages(self) -> list[HelpDialog]:
        if self.pages is None:
            self.pages = [self.first_page] + _build_further_pages(InfoSource(self.obj, self.page_type), self.page_type, self.unit)
        return self.pages

    def next_page(self) -> bool:
        pages = self.get_pages()
        if len(pages) <= 1:
            return False
        self.page = (self.page + 1) % len(pages)
        self.last_time = engine.get_time()
        return True

    def draw(self, surf, pos, right=False):
        time = engine.get_time()
        if time > self.last_time + 1000:  # Not shown for a while, so the player has moved on from it
            self.page = 0
        self.last_time = time

        pages = self.get_pages()
        help_box = pages[self.page]
        surf = help_box.draw(surf, pos, right)
        if len(pages) > 1:
            top_left = help_box.top_left(pos, right)
            draw_page_number(surf, help_box, top_left, top_left[1] != pos[1], self.page, len(pages))
        return surf
