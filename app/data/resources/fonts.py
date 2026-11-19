from dataclasses import asdict, dataclass, field
import os
import json
from pathlib import Path
from typing import Dict, List, Optional, override, Set

from app.data.resources.base_catalog import ManifestCatalog
from app.data.resources.resource_prefab import WithResources
from app.data.serialization.dataclass_serialization import dataclass_from_dict
from app.utilities.data import Prefab
from app.utilities.typing import Color4, NestedPrimitiveDict

# Mapeamento padrão das categorias de fonte do jogo
DEFAULT_FONT_ASSIGNMENTS: Dict[str, str] = {
    # 1. Globais & Sistema
    'text': 'text',
    'narrow': 'narrow',
    'small': 'small',
    'number': 'number_small2',
    'chapter': 'chapter',
    'system_debug': 'small',

    # 2. Narrativa & Diálogos
    'convo': 'convo',
    'convo_bold': 'bconvo',
    'convo_italic': 'iconvo',
    'convo_narrow': 'nconvo',
    'chapter_title': 'chapter',

    # 3. Menus & Navegação
    'ui_choice': 'text',
    'ui_prep': 'text',
    'ui_save_load': 'text',

    # 4. Ficha de Unidade & Estatísticas
    'ui_info': 'text',
    'ui_stat_bonus': 'small',
    'ui_weapon_rank': 'rank',
    'ui_help': 'info',

    # 5. Combate & HUD de Batalha
    'ui_combat': 'text',
    'combat_numbers': 'number_small2',
    'combat_multipliers': 'small',
    'health_bar': 'number_small2',

    # 6. Progressão, Promoção & Avisos
    'ui_level_up': 'text',
    'ui_level_up_bonus': 'stat',
    'ui_promo': 'text',
    'ui_banner': 'text',

    # 7. Pós-Jogo, Registros & Créditos
    'ui_record_book': 'text',
    'ui_victory': 'text',
    'ui_credits_title': 'credit_title',
    'ui_credits_body': 'credit',
}

# Paletas globais padrão do projeto separadas por perfis de contraste e cor
# UI (3 Cores): Texto claro sobre fundos escuros de janelas e menus
# Slot 0: Corpo Claro / Primário
# Slot 1: Sombra Escura
# Slot 2: Meio-tom / Suavização
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

# Diálogo & História (2 Cores): Texto escuro sobre balões de diálogo claros
# Slot 0: Corpo Escuro / Tinta
# Slot 1: Sombra / Realce Claro
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

# Perfis de paletas globais
DEFAULT_GLOBAL_PALETTE_PROFILES: Dict[str, Dict[str, List[Color4]]] = {
    'ui_3color': DEFAULT_UI_PALETTES,
    'dialogue_2color': DEFAULT_DIALOGUE_PALETTES,
    'custom': {},
}

# Retrocompatibilidade
DEFAULT_GLOBAL_PALETTES: Dict[str, List[Color4]] = DEFAULT_UI_PALETTES


def adapt_palette_to_font(palette_colors: List[Color4], target_count: int) -> List[Color4]:
    """Adapts a global palette color list to match the number of swatches expected by a font."""
    if not palette_colors or target_count <= 0:
        return []
    if len(palette_colors) == target_count:
        return [tuple(c) if len(c) == 4 else (c[0], c[1], c[2], 255) for c in palette_colors]

    # Fonte com 2 cores (Corpo + Sombra) e paleta com 3+ cores: usa os 2 tons principais
    if target_count == 2 and len(palette_colors) >= 2:
        return [tuple(palette_colors[0]), tuple(palette_colors[1])]

    # Fonte com 3 cores e paleta com 2 cores: sintetiza meio-tom suave
    if target_count == 3 and len(palette_colors) == 2:
        c0, c1 = palette_colors[0], palette_colors[1]
        mid = (
            int(c0[0] * 0.5 + c1[0] * 0.5),
            int(c0[1] * 0.5 + c1[1] * 0.5),
            int(c0[2] * 0.5 + c1[2] * 0.5),
            255
        )
        return [tuple(c0), tuple(c1), mid]

    # Interpolação linear para fontes com número arbitrário de cores (ex: gradientes)
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

class FontCatalog(ManifestCatalog[Font]):
    datatype = Font
    manifest = 'fonts.json'
    title = 'fonts'
    filetype = ''

    def __init__(self):
        super().__init__()
        self._loc: Optional[str] = None
        self.ui_assignments: Dict[str, str] = DEFAULT_FONT_ASSIGNMENTS.copy()
        self.palette_profiles: Dict[str, Dict[str, List[Color4]]] = {
            'ui_3color': {k: list(v) for k, v in DEFAULT_UI_PALETTES.items()},
            'dialogue_2color': {k: list(v) for k, v in DEFAULT_DIALOGUE_PALETTES.items()},
            'custom': {},
        }
        self.global_palettes: Dict[str, List[Color4]] = self.palette_profiles['ui_3color']

    def clear(self):
        super().clear()
        self._loc = None
        self.ui_assignments = DEFAULT_FONT_ASSIGNMENTS.copy()
        self.palette_profiles = {
            'ui_3color': {k: list(v) for k, v in DEFAULT_UI_PALETTES.items()},
            'dialogue_2color': {k: list(v) for k, v in DEFAULT_DIALOGUE_PALETTES.items()},
            'custom': {},
        }
        self.global_palettes = self.palette_profiles['ui_3color']

    def get_assignment(self, role: str) -> str:
        default_target = DEFAULT_FONT_ASSIGNMENTS.get(role, 'text')
        assigned = self.ui_assignments.get(role, default_target)
        if assigned in self:
            return assigned
        if default_target in self:
            return default_target
        if 'text' in self:
            return 'text'
        return self[0].nid if len(self) > 0 else 'text'

    def get_profile_for_font(self, font: Font) -> str:
        """Determina o perfil de paleta ideal para uma fonte pelo número de cores da base."""
        base_nid = font.base_palette_nid
        base_palette = font.palettes.get(base_nid) if base_nid else None
        num_colors = len(base_palette) if base_palette else 3
        if num_colors == 2:
            return 'dialogue_2color'
        elif num_colors == 3:
            return 'ui_3color'
        return 'custom' if 'custom' in self.palette_profiles and self.palette_profiles['custom'] else 'ui_3color'

    def sync_font_base_palette_with_sheet(self, font: Font) -> bool:
        """Extrai as cores reais da folha PNG da fonte e sincroniza a paleta base para garantir recolorização perfeita."""
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
            # Ordena por luminosidade para preservar a correspondência de papéis (claro -> médio -> escuro)
            sorted_colors = sorted(counts.keys(), key=lambda c: (0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]), reverse=True)
            base_key = font.base_palette_nid or 'white'
            font.palettes[base_key] = [tuple(c) for c in sorted_colors]
            return True
        except Exception:
            return False

    def inherit_global_palettes(self, font: Font, overwrite: bool = False, profile_key: Optional[str] = None):
        """Injeta as paletas do perfil correspondente na fonte, sem inverter contrastes."""
        base_nid = font.base_palette_nid
        base_palette = font.palettes.get(base_nid) if base_nid else None
        target_count = len(base_palette) if base_palette else 3

        selected_profile = profile_key or self.get_profile_for_font(font)
        source_palettes = self.palette_profiles.get(selected_profile) or self.global_palettes

        for pal_name, pal_colors in source_palettes.items():
            # NUNCA sobrescreve a paleta base (base_palette_nid), pois ela define as cores nativas dos pixels do PNG!
            if pal_name == base_nid:
                continue
            if overwrite or pal_name not in font.palettes:
                font.palettes[pal_name] = adapt_palette_to_font(pal_colors, target_count)

    def load(self, loc, *args, **kwargs):
        self._loc = str(loc)
        super().load(loc, *args, **kwargs)
        assign_path = Path(loc, 'font_assignments.json')
        self.ui_assignments = DEFAULT_FONT_ASSIGNMENTS.copy()
        if assign_path.exists():
            try:
                with open(assign_path, 'r', encoding='utf-8') as fp:
                    loaded = json.load(fp)
                    if isinstance(loaded, dict):
                        for k, v in loaded.items():
                            if isinstance(k, str) and isinstance(v, str):
                                self.ui_assignments[k] = v
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
                            # Formato novo com perfis tipados
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
                            # Formato legado flat: distribui paletas por contagem de cores
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
                # Salva também a flat list ui_3color na raiz para máxima retrocompatibilidade com ferramentas externas
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
