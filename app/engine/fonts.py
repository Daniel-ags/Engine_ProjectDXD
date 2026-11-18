from typing import Dict
from app.data.resources.resources import RESOURCES
from app.engine import bmpfont
from app.utilities.typing import NID

NORMAL_FONT_COLORS = ['white', 'blue', 'green', 'red', 'orange', 'grey', 'yellow', 'brown', 'purple', 'navy']

# Load in default, uncolored fonts
FONT: Dict[NID, bmpfont.BmpFont] = {}
NORMAL_FONT_COLORS = set()


def load_fonts(headless: bool = False):
    """Load all fonts from RESOURCES into the FONT registry and apply UI assignments."""
    global FONT
    global NORMAL_FONT_COLORS
    FONT.clear()

    # 1. Carrega cada fonte física normalmente com seu NID original
    raw_fonts: Dict[NID, bmpfont.BmpFont] = {}
    for font in RESOURCES.fonts.values():
        bmp_font = bmpfont.BmpFont(font, headless=headless)
        raw_fonts[font.nid] = bmp_font
        FONT[font.nid] = bmp_font
        for color_name in font.palettes:
            font_name_with_color = '%s-%s' % (font.nid, color_name)
            FONT[font_name_with_color] = bmp_font.with_default_color(color_name)

    # 2. Aplica os Aliases Semânticos configurados na Aba "UI Assignments" do Editor
    assignments = getattr(RESOURCES.fonts, 'ui_assignments', {}) or {}
    for role_key, target_nid in assignments.items():
        if target_nid not in raw_fonts:
            # Fallback seguro para 'text' caso a fonte escolhida não exista
            target_nid = 'text' if 'text' in raw_fonts else next(iter(raw_fonts), None)
        if not target_nid:
            continue

        target_bmp = raw_fonts[target_nid]
        target_prefab = RESOURCES.fonts.get(target_nid)
        FONT[role_key] = target_bmp
        if target_prefab:
            for color_name in target_prefab.palettes:
                FONT[f'{role_key}-{color_name}'] = target_bmp.with_default_color(color_name)

    text_prefab = RESOURCES.fonts.get(assignments.get('text', 'text')) or RESOURCES.fonts.get("text")
    NORMAL_FONT_COLORS = text_prefab.palettes.keys() if text_prefab else {'white'}


def get_text_color_options() -> list[str]:
    assignments = getattr(RESOURCES.fonts, 'ui_assignments', {}) or {}
    text_nid = assignments.get('text', 'text')
    text_font = RESOURCES.fonts.get(text_nid) or RESOURCES.fonts.get('text')
    if not text_font or not text_font.palettes:
        return ['white']
    return list(text_font.palettes.keys())