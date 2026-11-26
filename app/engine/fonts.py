from typing import Dict
from app.data.resources.resources import RESOURCES
from app.data.resources.fonts import DEFAULT_FONT_ASSIGNMENTS, DEFAULT_COLOR_ASSIGNMENTS
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

    STANDARD_ENGINE_COLORS = (
        'white', 'blue', 'green', 'red', 'orange',
        'grey', 'gray', 'yellow', 'brown', 'purple', 'navy', 'new-white'
    )

    # 1. Load each physical font under its original NID
    raw_fonts: Dict[NID, bmpfont.BmpFont] = {}
    for font in RESOURCES.fonts.values():
        bmp_font = bmpfont.BmpFont(font, headless=headless)
        raw_fonts[font.nid] = bmp_font
        FONT[font.nid] = bmp_font
        for color_name in font.palettes:
            font_name_with_color = '%s-%s' % (font.nid, color_name)
            FONT[font_name_with_color] = bmp_font.with_default_color(color_name)
        # Sync grey and gray spellings for physical fonts
        if f'{font.nid}-grey' in FONT and f'{font.nid}-gray' not in FONT:
            FONT[f'{font.nid}-gray'] = FONT[f'{font.nid}-grey']
        elif f'{font.nid}-gray' in FONT and f'{font.nid}-grey' not in FONT:
            FONT[f'{font.nid}-grey'] = FONT[f'{font.nid}-gray']

    # 2. Apply semantic UI role aliases configured in Font Editor
    user_assignments = getattr(RESOURCES.fonts, 'ui_assignments', {}) or {}
    all_roles = set(DEFAULT_FONT_ASSIGNMENTS.keys()).union(user_assignments.keys())

    for role_key in all_roles:
        val = user_assignments.get(role_key)
        if isinstance(val, dict):
            target_nid = val.get('font', DEFAULT_FONT_ASSIGNMENTS.get(role_key, 'text'))
            chosen_color = val.get('color', DEFAULT_COLOR_ASSIGNMENTS.get(role_key, 'white'))
        elif isinstance(val, (list, tuple)) and len(val) >= 2:
            target_nid = val[0]
            chosen_color = val[1]
        elif isinstance(val, str):
            target_nid = val
            chosen_color = DEFAULT_COLOR_ASSIGNMENTS.get(role_key, 'white')
        else:
            target_nid = DEFAULT_FONT_ASSIGNMENTS.get(role_key, 'text')
            chosen_color = DEFAULT_COLOR_ASSIGNMENTS.get(role_key, 'white')

        if target_nid not in raw_fonts:
            default_fallback = DEFAULT_FONT_ASSIGNMENTS.get(role_key, 'text')
            if default_fallback in raw_fonts:
                target_nid = default_fallback
            elif 'text' in raw_fonts:
                target_nid = 'text'
            else:
                target_nid = next(iter(raw_fonts), None)
        if not target_nid:
            continue

        target_bmp = raw_fonts[target_nid]
        target_prefab = RESOURCES.fonts.get(target_nid)

        # If chosen_color is defined and present in target font, configure default_color on role instance
        if chosen_color and target_prefab and chosen_color in target_prefab.palettes:
            FONT[role_key] = target_bmp.with_default_color(chosen_color)
        else:
            FONT[role_key] = target_bmp

        if target_prefab:
            for color_name in target_prefab.palettes:
                FONT[f'{role_key}-{color_name}'] = target_bmp.with_default_color(color_name)

        # Grey / gray equivalence
        if f'{role_key}-grey' in FONT and f'{role_key}-gray' not in FONT:
            FONT[f'{role_key}-gray'] = FONT[f'{role_key}-grey']
        elif f'{role_key}-gray' in FONT and f'{role_key}-grey' not in FONT:
            FONT[f'{role_key}-grey'] = FONT[f'{role_key}-gray']

        # Safe fallback for standard engine colors missing from target font
        for std_color in STANDARD_ENGINE_COLORS:
            full_key = f'{role_key}-{std_color}'
            if full_key not in FONT:
                FONT[full_key] = target_bmp

    text_val = user_assignments.get('text', DEFAULT_FONT_ASSIGNMENTS.get('text', 'text'))
    text_nid = text_val.get('font', 'text') if isinstance(text_val, dict) else (text_val if isinstance(text_val, str) else 'text')
    text_prefab = RESOURCES.fonts.get(text_nid) or RESOURCES.fonts.get("text")
    NORMAL_FONT_COLORS = text_prefab.palettes.keys() if text_prefab else {'white'}


def get_text_color_options() -> list[str]:
    assignments = getattr(RESOURCES.fonts, 'ui_assignments', {}) or {}
    text_val = assignments.get('text', DEFAULT_FONT_ASSIGNMENTS.get('text', 'text'))
    text_nid = text_val.get('font', 'text') if isinstance(text_val, dict) else (text_val if isinstance(text_val, str) else 'text')
    text_font = RESOURCES.fonts.get(text_nid) or RESOURCES.fonts.get('text')
    if not text_font or not text_font.palettes:
        return ['white']
    return list(text_font.palettes.keys())