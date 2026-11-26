from dataclasses import asdict, dataclass, field
import os
import json
from pathlib import Path
from typing import Dict, List, Optional, override, Set

from app.data.category import CategorizedCatalog
from app.data.resources.base_catalog import ManifestCatalog
from app.data.resources.resource_prefab import WithResources
from app.data.serialization.dataclass_serialization import dataclass_from_dict
from app.utilities.data import Prefab
from app.utilities.typing import Color4, NestedPrimitiveDict

# Default mapping of semantic in-game font roles
DEFAULT_FONT_ASSIGNMENTS: Dict[str, str] = {
    # 1. Global & System
    'text': 'text',
    'narrow': 'narrow',
    'small': 'small',
    'number': 'number_small2',
    'chapter': 'chapter',
    'system_debug': 'small',

    # 2. Narrative & Dialogues
    'convo': 'convo',
    'convo_bold': 'bconvo',
    'convo_italic': 'iconvo',
    'convo_narrow': 'nconvo',
    'chapter_title': 'chapter',

    # 3. Menus & Navigation
    'ui_choice': 'text',
    'ui_prep': 'text',
    'ui_save_load': 'text',

    # 4. Unit Info & Stats
    'ui_info': 'text',
    'ui_stat_bonus': 'small',
    'ui_stat_buff': 'small',
    'ui_stat_debuff': 'small',
    'ui_weapon_rank': 'rank',
    'ui_help': 'info',

    # 5. Combat & Battle HUD
    'ui_combat': 'text',
    'combat_numbers': 'number_small2',
    'combat_multipliers': 'small',
    'combat_multiplier_2': 'small',
    'combat_multiplier_3': 'small',
    'combat_multiplier_4': 'small',
    'combat_multiplier_5': 'small',
    'health_bar': 'number_small2',

    # 6. Progression, Promotion & Banners
    'ui_level_up': 'text',
    'ui_level_up_bonus': 'stat',
    'ui_promo': 'text',
    'ui_banner': 'text',

    # 7. Post-Game, Records & Credits
    'ui_record_book': 'text',
    'ui_victory': 'text',
    'ui_credits_title': 'credit_title',
    'ui_credits_body': 'credit',
}

DEFAULT_COLOR_ASSIGNMENTS: Dict[str, str] = {
    # 1. Global & System
    'text': 'white',
    'narrow': 'white',
    'small': 'white',
    'number': 'white',
    'chapter': 'white',
    'system_debug': 'white',

    # 2. Narrative & Dialogues
    'convo': 'black',
    'convo_bold': 'black',
    'convo_italic': 'black',
    'convo_narrow': 'black',
    'chapter_title': 'white',

    # 3. Menus & Navigation
    'ui_choice': 'white',
    'ui_prep': 'white',
    'ui_save_load': 'white',

    # 4. Unit Info & Stats
    'ui_info': 'white',
    'ui_stat_bonus': 'green',
    'ui_stat_buff': 'green',
    'ui_stat_debuff': 'red',
    'ui_weapon_rank': 'blue',
    'ui_help': 'white',

    # 5. Combat & Battle HUD
    'ui_combat': 'white',
    'combat_numbers': 'yellow',
    'combat_multipliers': 'green',
    'combat_multiplier_2': 'green',
    'combat_multiplier_3': 'yellow',
    'combat_multiplier_4': 'red',
    'combat_multiplier_5': 'purple',
    'health_bar': 'white',

    # 6. Progression, Promotion & Banners
    'ui_level_up': 'white',
    'ui_level_up_bonus': 'yellow',
    'ui_promo': 'white',
    'ui_banner': 'white',

    # 7. Post-Game, Records & Credits
    'ui_record_book': 'white',
    'ui_victory': 'white',
    'ui_credits_title': 'white',
    'ui_credits_body': 'white',
}

def get_default_font_for_role(role_key: str) -> str:
    """Returns the default font for any UI role, including dynamic weapon ranks."""
    if role_key in DEFAULT_FONT_ASSIGNMENTS:
        return DEFAULT_FONT_ASSIGNMENTS[role_key]
    if role_key.startswith('weapon_rank_'):
        return DEFAULT_FONT_ASSIGNMENTS.get('ui_weapon_rank', 'rank')
    return 'text'

def get_default_color_for_role(role_key: str) -> str:
    """Returns the default color palette for any UI element, including dynamic weapon ranks."""
    if role_key in DEFAULT_COLOR_ASSIGNMENTS:
        return DEFAULT_COLOR_ASSIGNMENTS[role_key]
    if role_key.startswith('weapon_rank_'):
        rank_nid = role_key[len('weapon_rank_'):]
        if rank_nid in ('S', 'SS'):
            return 'yellow'
        elif rank_nid in ('A', 'B'):
            return 'green'
        return DEFAULT_COLOR_ASSIGNMENTS.get('ui_weapon_rank', 'blue')
    return 'white'

# Default project global palettes separated by contrast and color profiles
# UI (3 Colors): Light text on dark window and menu backgrounds
# Slot 0: Light / Primary Body
# Slot 1: Dark Shadow
# Slot 2: Midtone / Antialiasing
DEFAULT_UI_PALETTES: Dict[str, List[Color4]] = {
    'white': [(248, 248, 248, 255), (56, 48, 40, 255), (160, 136, 216, 255)],
    'blue': [(192, 248, 248, 255), (24, 24, 88, 255), (80, 112, 248, 255)],
    'green': [(72, 232, 32, 255), (24, 88, 24, 255), (112, 160, 72, 255)],
    'red': [(224, 96, 80, 255), (88, 24, 24, 255), (160, 88, 72, 255)],
    'orange': [(248, 168, 88, 255), (138, 64, 0, 255), (160, 100, 85, 255)],
    'grey': [(184, 176, 176, 255), (56, 48, 40, 255), (136, 128, 120, 255)],
    'gray': [(184, 176, 176, 255), (56, 48, 40, 255), (136, 128, 120, 255)],
    'yellow': [(248, 240, 136, 255), (72, 64, 8, 255), (168, 168, 72, 255)],
    'brown': [(248, 248, 248, 255), (80, 40, 0, 255), (144, 112, 88, 255)],
    'purple': [(199, 155, 232, 255), (62, 37, 82, 255), (147, 61, 212, 255)],
    'navy': [(24, 123, 205, 255), (0, 0, 128, 255), (32, 14, 244, 255)],
    'red-orange': [(248, 64, 64, 255), (80, 24, 32, 255), (152, 72, 96, 255)],
    'light-red': [(248, 88, 96, 255), (80, 24, 32, 255), (152, 72, 96, 255)],
    'pink-orange': [(248, 128, 96, 255), (80, 24, 32, 255), (152, 72, 96, 255)],
    'light-orange': [(248, 168, 88, 255), (80, 24, 32, 255), (152, 72, 96, 255)],
    'corn-yellow': [(232, 248, 112, 255), (64, 56, 24, 255), (80, 152, 72, 255)],
    'light-green': [(200, 232, 136, 255), (24, 88, 24, 255), (80, 152, 72, 255)],
    'olive-green': [(168, 208, 96, 255), (24, 88, 24, 255), (80, 152, 72, 255)],
    'soft-green': [(128, 192, 104, 255), (24, 88, 24, 255), (80, 152, 72, 255)],
    'yellow-green': [(57, 206, 16, 255), (24, 88, 24, 255), (80, 152, 72, 255)],
    'black': [(40, 40, 40, 255), (16, 16, 16, 255), (80, 80, 80, 255)],
    'indigo': [(75, 0, 130, 255), (32, 0, 64, 255), (204, 204, 255, 255)],
    'violet': [(127, 0, 255, 255), (48, 0, 96, 255), (229, 204, 255, 255)],
    'pink': [(255, 102, 178, 255), (120, 24, 64, 255), (255, 204, 229, 255)],
}

# Dialogue & Story (2 Colors): Dark text on light speech bubbles
# Slot 0: Dark Body / Ink
# Slot 1: Shadow / Light Highlight
DEFAULT_DIALOGUE_PALETTES: Dict[str, List[Color4]] = {
    'black': [(40, 40, 40, 255), (184, 184, 184, 255)],
    'blue': [(24, 48, 168, 255), (168, 192, 248, 255)],
    'red': [(168, 32, 32, 255), (248, 168, 168, 255)],
    'green': [(24, 96, 32, 255), (160, 224, 168, 255)],
    'yellow': [(168, 120, 16, 255), (248, 232, 144, 255)],
    'orange': [(184, 72, 16, 255), (248, 200, 152, 255)],
    'brown': [(88, 48, 16, 255), (208, 176, 144, 255)],
    'white': [(184, 184, 184, 255), (248, 248, 248, 255)],
    'indigo': [(48, 16, 112, 255), (184, 168, 240, 255)],
    'violet': [(88, 24, 144, 255), (216, 176, 248, 255)],
    'pink': [(168, 40, 112, 255), (248, 176, 216, 255)],
}

# Global palette profiles
DEFAULT_GLOBAL_PALETTE_PROFILES: Dict[str, Dict[str, List[Color4]]] = {
    'ui_3color': DEFAULT_UI_PALETTES,
    'dialogue_2color': DEFAULT_DIALOGUE_PALETTES,
    'custom': {},
}

# Backward compatibility
DEFAULT_GLOBAL_PALETTES: Dict[str, List[Color4]] = DEFAULT_UI_PALETTES


def adapt_palette_to_font(palette_colors: List[Color4], target_count: int) -> List[Color4]:
    """Adapts a global palette color list to match the number of swatches expected by a font."""
    if not palette_colors or target_count <= 0:
        return []
    if len(palette_colors) == target_count:
        return [tuple(c) if len(c) == 4 else (c[0], c[1], c[2], 255) for c in palette_colors]

    # 2-color font (Body + Shadow) with 3+ color palette: use top 2 primary shades
    if target_count == 2 and len(palette_colors) >= 2:
        return [tuple(palette_colors[0]), tuple(palette_colors[1])]

    # 3-color font with 2-color palette: synthesize smooth midtone
    if target_count == 3 and len(palette_colors) == 2:
        c0, c1 = palette_colors[0], palette_colors[1]
        mid = (
            int(c0[0] * 0.5 + c1[0] * 0.5),
            int(c0[1] * 0.5 + c1[1] * 0.5),
            int(c0[2] * 0.5 + c1[2] * 0.5),
            255
        )
        return [tuple(c0), tuple(c1), mid]

    # Linear interpolation for fonts with arbitrary color count (e.g. gradients)
    res = []
    src_len = len(palette_colors)
    for i in range(target_count):
        idx_f = i * (src_len - 1) / max(target_count - 1, 1)
        low = int(idx_f)
        high = min(low + 1, src_len - 1)
        t = idx_f - low
        c_low = palette_colors[low]
        c_high = palette_colors[high]
        interp = (
            int(c_low[0] * (1 - t) + c_high[0] * t),
            int(c_low[1] * (1 - t) + c_high[1] * t),
            int(c_low[2] * (1 - t) + c_high[2] * t),
            255
        )
        res.append(interp)
    return res

@dataclass
class CharGlyph:
    """Position and kerning width of a single glyph on the sprite sheet.

    ``x`` and ``y`` are pixel coordinates (already multiplied by the cell
    dimensions), so they can be used directly for cropping.
    ``char_width`` is the kerning advance width in pixels.
    """
    x: int
    y: int
    char_width: int


class FontIndex:
    """Parsed representation of a ``.idx`` bitmap-font index file.

    Attributes
    ----------
    char_width : int
        Width of each cell on the sprite sheet.
    char_height : int
        Height of each cell on the sprite sheet.
    all_uppercase : bool
        When True, every lookup key is normalised to uppercase.
    all_lowercase : bool
        When True, every lookup key is normalised to lowercase.
    stacked : bool
        When True the sprite sheet stores two vertical rows per glyph
        (primary on top, secondary/shadow below).
    space_offset : int
        Extra horizontal advance added between every character.
    chartable : Dict[str, CharGlyph]
        Maps each character to its glyph on the sheet.
    """

    def __init__(self) -> None:
        self.char_width: int = 8
        self.char_height: int = 16
        self.all_uppercase: bool = False
        self.all_lowercase: bool = False
        self.stacked: bool = False
        self.space_offset: int = 0
        self.chartable: Dict[str, CharGlyph] = {}

    @classmethod
    def from_path(cls, idx_path: str) -> 'FontIndex':
        """Parse *idx_path* and return a :class:`FontIndex`.

        The ``width`` and ``height`` header lines must appear **before** any
        glyph entries because the pixel coordinates are computed on the fly
        while reading.
        """
        index = cls()
        with open(idx_path, 'r', encoding='utf-8') as fp:
            for raw_line in fp:
                words = raw_line.strip().split()
                if not words:
                    continue
                key = words[0]
                if key == 'width':
                    index.char_width = int(words[1])
                elif key == 'height':
                    index.char_height = int(words[1])
                elif key == 'alluppercase':
                    index.all_uppercase = True
                elif key == 'alllowercase':
                    index.all_lowercase = True
                elif key == 'stacked':
                    index.stacked = True
                elif key == 'space_offset':
                    index.space_offset = int(words[1])
                else:
                    # Glyph entry: <char> <col> <row> <kerning_width>
                    if len(words) < 4:
                        continue
                    if key == 'space':
                        key = ' '
                    if index.all_uppercase:
                        key = key.upper()
                    elif index.all_lowercase:
                        key = key.lower()
                    index.chartable[key] = CharGlyph(
                        x=int(words[1]) * index.char_width,
                        y=int(words[2]) * index.char_height,
                        char_width=int(words[3]),
                    )
        return index

    def get(self, char: str) -> Optional[CharGlyph]:
        """Return the :class:`CharGlyph` for *char*, or ``None``."""
        if self.all_uppercase:
            char = char.upper()
        elif self.all_lowercase:
            char = char.lower()
        return self.chartable.get(char)

    def __contains__(self, char: str) -> bool:
        if self.all_uppercase:
            char = char.upper()
        elif self.all_lowercase:
            char = char.lower()
        return char in self.chartable

    def __repr__(self) -> str:
        return (
            f'FontIndex(char_width={self.char_width}, char_height={self.char_height}, '
            f'glyphs={len(self.chartable)})'
        )


@dataclass(slots=True)
class Font(WithResources, Prefab):
    path_fields = ('file_name',)

    nid: str                                                                            #: NID of the font.
    fallback_ttf: str = None                                                             #: name of the .ttf file (in this directory) to be used as a fallback if the main font cannot render anything
    fallback_size: int = 16                                                              #: what size the fallback font should be rendered at. This may well differ depending on the font, especially at these lower resolutions!
    default_color: Optional[str] = None                                                  #: The palette text is rendered in when no color is asked for.
    outline_font: bool = False                                                           #: whether this font has an outline
    headless: bool = False #:Whether this font renders on a transparent surf
    base_color: Optional[str] = None                                                     #: The palette holding the sprite sheet's own colors. None falls back to `default_color`.
    palettes: Dict[str, List[Color4]] = field(default_factory=dict)                      #: A dictionary of color names to the palette of the font color.

    def __post_init__(self):
        self.file_name: str = None                                                       #: Root path without file ending, e.g. `project.ltproj/resources/convo`.
        self._font_index: Optional['FontIndex'] = None

    @property
    def base_palette_nid(self) -> Optional[str]:
        """Palette whose colors are the ones actually in the PNG.

        Every other palette is an index-for-index remap of it, so this is what a
        recoloring reads *from* -- which is not necessarily the palette text
        happens to default to rendering *in* (:attr:`default_color`).
        """
        return self.base_color or self.default_color

    @property
    def font_index(self) -> Optional['FontIndex']:
        """Lazily parsed :class:`FontIndex` for this font. Not serialized."""
        if self._font_index is None and self.file_name:
            idx_path = self.index_path()
            if os.path.exists(idx_path):
                self._font_index = FontIndex.from_path(idx_path)
        return self._font_index

    def image_path(self):
        return self.file_name + '.png'

    def index_path(self):
        return self.file_name + '.idx'

    def ttf_path(self):
        if self.fallback_ttf:
            return str(Path(self.file_name).parent / self.fallback_ttf)

    def primary_color(self, color):
        palette = self.palettes.get(color)
        if palette:
            return palette[0]
        return None

    def secondary_color(self, color):
        palette = self.palettes.get(color)
        if palette:
            if len(palette) > 1:
                return palette[1]
            return palette[0]
        return None

    @override
    def set_full_path(self, path: str) -> None:
        self.file_name = path

    @override
    def used_resources(self) -> List[Optional[Path]]:
        paths = [Path(self.image_path()), Path(self.index_path())]
        paths.append(Path(self.ttf_path()) if self.ttf_path() else None)
        return paths

    def save(self):
        return asdict(self)

    @classmethod
    def restore(cls, s_dict):
        return dataclass_from_dict(cls, s_dict)

class FontCatalog(ManifestCatalog[Font], CategorizedCatalog[Font]):
    datatype = Font
    manifest = 'fonts.json'
    title = 'fonts'
    filetype = ''

    def __init__(self):
        super().__init__()
        self._loc: Optional[str] = None
        self.ui_assignments: Dict[str, Dict[str, str]] = {
            k: {'font': v, 'color': DEFAULT_COLOR_ASSIGNMENTS.get(k, 'white')}
            for k, v in DEFAULT_FONT_ASSIGNMENTS.items()
        }
        self.palette_profiles: Dict[str, Dict[str, List[Color4]]] = {
            'ui_3color': {k: list(v) for k, v in DEFAULT_UI_PALETTES.items()},
            'dialogue_2color': {k: list(v) for k, v in DEFAULT_DIALOGUE_PALETTES.items()},
            'custom': {},
        }
        self.global_palettes: Dict[str, List[Color4]] = self.palette_profiles['ui_3color']

    def clear(self):
        super().clear()
        if hasattr(self, 'categories'):
            self.categories.clear()
        self._loc = None
        self.ui_assignments = {
            k: {'font': v, 'color': DEFAULT_COLOR_ASSIGNMENTS.get(k, 'white')}
            for k, v in DEFAULT_FONT_ASSIGNMENTS.items()
        }
        self.palette_profiles = {
            'ui_3color': {k: list(v) for k, v in DEFAULT_UI_PALETTES.items()},
            'dialogue_2color': {k: list(v) for k, v in DEFAULT_DIALOGUE_PALETTES.items()},
            'custom': {},
        }
        self.global_palettes = self.palette_profiles['ui_3color']

    def get_assignment(self, role: str) -> str:
        default_target = DEFAULT_FONT_ASSIGNMENTS.get(role, 'text')
        raw = self.ui_assignments.get(role)
        if isinstance(raw, dict):
            assigned = raw.get('font', default_target)
        elif isinstance(raw, (list, tuple)) and len(raw) > 0:
            assigned = raw[0]
        elif isinstance(raw, str):
            assigned = raw
        else:
            assigned = default_target

        if assigned in self:
            return assigned
        if default_target in self:
            return default_target
        if 'text' in self:
            return 'text'
        return self[0].nid if len(self) > 0 else 'text'

    def get_assigned_color(self, role: str) -> str:
        default_color = DEFAULT_COLOR_ASSIGNMENTS.get(role, 'white')
        raw = self.ui_assignments.get(role)
        if isinstance(raw, dict):
            return raw.get('color', default_color) or default_color
        elif isinstance(raw, (list, tuple)) and len(raw) > 1:
            return raw[1] or default_color
        return default_color

    def get_profile_for_font(self, font: Font) -> str:
        """Determines the ideal palette profile for a source based on the number of base colors."""
        base_nid = font.base_palette_nid
        base_palette = font.palettes.get(base_nid) if base_nid else None
        num_colors = len(base_palette) if base_palette else 3
        if num_colors == 2:
            return 'dialogue_2color'
        elif num_colors == 3:
            return 'ui_3color'
        return 'custom' if 'custom' in self.palette_profiles and self.palette_profiles['custom'] else 'ui_3color'

    def sync_font_base_palette_with_sheet(self, font: Font) -> bool:
        """Extracts the actual colors from the source PNG sheet and synchronizes the base palette to ensure perfect recoloring."""
        img_path = font.image_path()
        if not img_path or not os.path.exists(img_path):
            return False
        try:
            from PIL import Image
            from collections import Counter
            im = Image.open(img_path).convert('RGBA')
            counts = Counter()
            for r, g, b, a in im.getdata():
                if a == 255:
                    counts[(r, g, b, 255)] += 1
            if not counts:
                return False
            # Sort by luminance to preserve role correspondence (light -> mid -> dark)
            sorted_colors = sorted(counts.keys(), key=lambda c: (0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]), reverse=True)
            base_key = font.base_palette_nid or 'white'
            font.palettes[base_key] = [tuple(c) for c in sorted_colors]
            return True
        except Exception:
            return False

    def inherit_global_palettes(self, font: Font, overwrite: bool = False, profile_key: Optional[str] = None):
        """Injects the palettes of the corresponding profile into the source, without inverting contrasts."""
        base_nid = font.base_palette_nid
        base_palette = font.palettes.get(base_nid) if base_nid else None
        target_count = len(base_palette) if base_palette else 3

        selected_profile = profile_key or self.get_profile_for_font(font)
        source_palettes = self.palette_profiles.get(selected_profile) or self.global_palettes

        for pal_name, pal_colors in source_palettes.items():
            # NEVER overwrite base palette (base_palette_nid), as it defines the PNG pixels native colors!
            if pal_name == base_nid:
                continue
            if overwrite or pal_name not in font.palettes:
                font.palettes[pal_name] = adapt_palette_to_font(pal_colors, target_count)

    def load(self, loc, *args, **kwargs):
        self._loc = str(loc)
        super().load(loc, *args, **kwargs)
        assign_path = Path(loc, 'font_assignments.json')
        self.ui_assignments = {
            k: {'font': v, 'color': DEFAULT_COLOR_ASSIGNMENTS.get(k, 'white')}
            for k, v in DEFAULT_FONT_ASSIGNMENTS.items()
        }
        if assign_path.exists():
            try:
                with open(assign_path, 'r', encoding='utf-8') as fp:
                    loaded = json.load(fp)
                    if isinstance(loaded, dict):
                        for k, v in loaded.items():
                            if isinstance(k, str):
                                if isinstance(v, str):
                                    self.ui_assignments[k] = {
                                        'font': v,
                                        'color': DEFAULT_COLOR_ASSIGNMENTS.get(k, 'white')
                                    }
                                elif isinstance(v, dict):
                                    self.ui_assignments[k] = {
                                        'font': v.get('font', DEFAULT_FONT_ASSIGNMENTS.get(k, 'text')),
                                        'color': v.get('color', DEFAULT_COLOR_ASSIGNMENTS.get(k, 'white'))
                                    }
            except Exception:
                pass

        palettes_path = Path(loc, 'font_palettes.json')
        self.palette_profiles = {
            'ui_3color': {k: list(v) for k, v in DEFAULT_UI_PALETTES.items()},
            'dialogue_2color': {k: list(v) for k, v in DEFAULT_DIALOGUE_PALETTES.items()},
            'custom': {},
        }
        if palettes_path.exists():
            try:
                with open(palettes_path, 'r', encoding='utf-8') as fp:
                    loaded_p = json.load(fp)
                    if isinstance(loaded_p, dict):
                        if 'profiles' in loaded_p and isinstance(loaded_p['profiles'], dict):
                            # New format with typed profiles
                            for pkey, pdict in loaded_p['profiles'].items():
                                if isinstance(pdict, dict):
                                    if pkey not in self.palette_profiles:
                                        self.palette_profiles[pkey] = {}
                                    for kn, cv in pdict.items():
                                        if isinstance(cv, list):
                                            self.palette_profiles[pkey][kn] = [
                                                tuple(c) if len(c) == 4 else (c[0], c[1], c[2], 255) for c in cv
                                            ]
                        else:
                            # Legacy flat format: distribute palettes by color count
                            for k, v in loaded_p.items():
                                if isinstance(k, str) and isinstance(v, list):
                                    parsed = [tuple(c) if len(c) == 4 else (c[0], c[1], c[2], 255) for c in v]
                                    if len(parsed) == 2:
                                        self.palette_profiles['dialogue_2color'][k] = parsed
                                    elif len(parsed) == 3:
                                        self.palette_profiles['ui_3color'][k] = parsed
                                    else:
                                        self.palette_profiles['custom'][k] = parsed
            except Exception:
                pass
        self.global_palettes = self.palette_profiles['ui_3color']

    def save_assignments(self, loc: Optional[str] = None):
        target_loc = loc or self._loc
        if not target_loc:
            return
        assign_path = Path(target_loc, 'font_assignments.json')
        try:
            os.makedirs(target_loc, exist_ok=True)
            with open(assign_path, 'w', encoding='utf-8') as fp:
                json.dump(self.ui_assignments, fp, indent=4)
        except Exception:
            pass

    def save_palettes(self, loc: Optional[str] = None):
        target_loc = loc or self._loc
        if not target_loc:
            return
        palettes_path = Path(target_loc, 'font_palettes.json')
        try:
            os.makedirs(target_loc, exist_ok=True)
            data_to_save = {
                'profiles': self.palette_profiles,
                # Also save flat ui_3color list at root for backwards compatibility with external tools
                **self.palette_profiles.get('ui_3color', {})
            }
            with open(palettes_path, 'w', encoding='utf-8') as fp:
                json.dump(data_to_save, fp, indent=4)
        except Exception:
            pass

    def save(self, *args, **kwargs):
        self.save_assignments()
        self.save_palettes()
        return super().save(*args, **kwargs)

    def save_resources(self, loc, repoint=True):
        self._loc = str(loc)
        self.save_assignments(loc)
        self.save_palettes(loc)
        super().save_resources(loc, repoint)
