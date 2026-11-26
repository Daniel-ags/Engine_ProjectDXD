import os
from typing import Optional

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
    QLabel, QPushButton, QScrollArea, QGridLayout, QLineEdit, QMessageBox,
    QSplitter, QListWidget, QListWidgetItem
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QIcon, QImage, QPixmap

from app.data.database.database import DB
from app.data.resources.resources import RESOURCES
from app.data.resources.fonts import (
    Font, FontCatalog, DEFAULT_FONT_ASSIGNMENTS, DEFAULT_COLOR_ASSIGNMENTS,
    get_default_font_for_role, get_default_color_for_role
)
from app.data.resources.resource_types import ResourceType as RType
from app.editor import reference_dialogs
from app.editor.data_editor import SingleResourceEditor, NewMultiResourceEditor
from app.editor.new_editor_tab import NewEditorTab
from app.editor.edit_history import HISTORY
from app.editor.font_editor import font_model, font_properties
from app.editor.font_editor.palette_tab import FontPaletteDatabase, PaletteEditorWidget
from app.engine.bmpfont import BmpFont
from app.engine import engine
from app.engine.fonts import load_fonts
from app.extensions.custom_gui import ComboBox
from app.utilities.typing import NID


FONT_ROLE_CATEGORIES = [
    ('global', "Core & Fallbacks"),
    ('story', "Dialogue & Story"),
    ('menu', "Menus & Navigation"),
    ('status', "Unit Status & Stats"),
    ('combat', "Combat HUD"),
    ('progression', "Progression"),
    ('postgame', "Records & Credits"),
]

def get_ui_font_roles(db=None) -> list[tuple[str, str, str, str]]:
    """
    Returns the game interface roles (role_key, label_text, sample_text, cat_key).
    Reads weapon ranks dynamically from the database (DB.weapon_ranks),
    allowing for individual customization of any rank defined within the project.
    """
    roles = [
        # 1. Global & System
        ('text', "General UI & Base Text", "Iron Sword  Mt 5  Hit 90", 'global'),
        ('narrow', "Condensed / Narrow Text", "Vulnerary (3/3)  Longsword", 'global'),
        ('small', "Small Labels & Indicators", "Def +2  Avo +10  Cost 1", 'global'),
        ('system_debug', "FPS Counter & Diagnostics", "FPS: 60 (Min: 58)  Speed: 1x", 'global'),

        # 2. Narrative & Dialogues
        ('convo', "Main Dialogue", "Shall we head into battle, commander?", 'story'),
        ('convo_bold', "Emphasized Dialogue (<b>)", "Stand back! This is dangerous!", 'story'),
        ('convo_italic', "Thoughts & Narration (<i>)", "(Could this be the legendary blade...?)", 'story'),
        ('convo_narrow', "Compact Dialogue", "We must reach the fortress before nightfall!", 'story'),
        ('chapter_title', "Chapter Title Ribbon", "Chapter 1: Maiden of the Plains", 'story'),

        # 3. Menus & Navigation
        ('ui_choice', "Action & Command Menus", "Attack   Item   Trade   Wait", 'menu'),
        ('ui_prep', "Battle Preparation Screens", "Manage Items   Check Map   Fight!", 'menu'),
        ('ui_save_load', "Save / Load Slots", "File 1: Ch 4  Turn 12  Gold 5400G", 'menu'),

        # 4. Unit Info & Stats
        ('ui_info', "Status & Profile Screen", "STR 14   MAG 8   SKL 16   SPD 15", 'status'),
        ('ui_stat_bonus', "Stat Modifiers (Fallback)", "+3 SPD   -2 DEF   +5 HIT", 'status'),
        ('ui_stat_buff', "Stat Buffs & Bonuses (+)", "+3 SPD   +5 HIT   +2 ATK", 'status'),
        ('ui_stat_debuff', "Stat Debuffs & Penalties (-)", "-2 DEF   -4 ATK   -3 AVO", 'status'),
    ]

    # Dynamic discovery of Weapon Ranks
    target_db = db or DB
    weapon_ranks = getattr(target_db, 'weapon_ranks', []) if target_db else []
    if weapon_ranks:
        for wr in weapon_ranks:
            rank_name = wr.nid or wr.rank
            roles.append((
                f'weapon_rank_{rank_name}',
                f"Weapon Rank ({rank_name})",
                f"Rank {rank_name}",
                'status'
            ))
    else:
        roles.append(('ui_weapon_rank', "Weapon Mastery Ranks", "S   A   B   C   D   E", 'status'))

    roles.extend([
        ('ui_help', "Tooltips & Help Boxes", "Effective against cavalry and armored units.", 'status'),

        # 5. Combat & Battle HUD
        ('ui_combat', "Combat Forecast HUD", "Atk 24   Hit 85%   Crit 12%   AS 14", 'combat'),
        ('combat_numbers', "Battle Hit, Damage & Crit", "32 / 45   Dmg 14   Hit 95", 'combat'),
        ('combat_multiplier_2', "Attack Multiplier (x2)", "x2", 'combat'),
        ('combat_multiplier_3', "Attack Multiplier (x3)", "x3", 'combat'),
        ('combat_multiplier_4', "Attack Multiplier (x4)", "x4", 'combat'),
        ('combat_multiplier_5', "Attack Multiplier (x5+)", "x5", 'combat'),
        ('health_bar', "Overhead Health Bars", "HP 28 / 28   Guard 100%", 'combat'),

        # 6. Progression, Promotion & Banners
        ('ui_level_up', "Level Up Screen", "Level 12 Paladin   EXP 100", 'progression'),
        ('ui_level_up_bonus', "Level Up Stat Ticks (+1)", "+1 HP   +1 STR   +1 SPD", 'progression'),
        ('ui_promo', "Promotion & Class Change", "Promote to Hero?  Gain Sol & Axes", 'progression'),
        ('ui_banner', "Alerts & Notifications", "Learned Skill: Adept!   Item: Silver Bow", 'progression'),

        # 7. Post-Game, Records & Credits
        ('ui_record_book', "Hall of Fame & Record Book", "Overall MVP: Ephraim   Total Turns: 84", 'postgame'),
        ('ui_victory', "Chapter Victory Summary", "Chapter Complete!   Cleared in 8 Turns", 'postgame'),
        ('ui_credits_title', "Credits Department Titles", "Lead Designer & Programmer", 'postgame'),
        ('ui_credits_body', "Credits Staff Roll & Thanks", "Special Thanks to the Lex Talionis Community", 'postgame'),
    ])
    return roles

UI_FONT_ROLES = get_ui_font_roles()


class FontAssignmentsWidget(QWidget):
    """Font Editor tab: allows you to choose which font and palette each part of the game uses."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._combos: dict[str, ComboBox] = {}
        self._color_combos: dict[str, ComboBox] = {}
        self._previews: dict[str, QLabel] = {}
        self._role_widgets: dict[str, tuple] = {}
        self._bmp_cache: dict[str, BmpFont] = {}
        self._current_category: str = 'all'

        main_layout = QHBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(main_layout)

        self.splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(self.splitter)

        # Left Panel: Search filter, categories and reset actions
        self.left_frame = QWidget()
        left_layout = QVBoxLayout()
        left_layout.setContentsMargins(0, 0, 0, 0)
        self.left_frame.setLayout(left_layout)

        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("Filter roles...")
        self._search_input.textChanged.connect(self._on_search_changed)
        left_layout.addWidget(self._search_input)

        self.category_list = QListWidget()
        all_item = QListWidgetItem("All Roles")
        all_item.setData(Qt.UserRole, 'all')
        self.category_list.addItem(all_item)
        for cat_key, cat_title in FONT_ROLE_CATEGORIES:
            item = QListWidgetItem(cat_title)
            item.setData(Qt.UserRole, cat_key)
            self.category_list.addItem(item)
        self.category_list.setCurrentRow(0)
        self.category_list.currentRowChanged.connect(self._on_category_changed)
        left_layout.addWidget(self.category_list, 1)

        self.reset_cat_btn = QPushButton("Reset Category")
        self.reset_cat_btn.setEnabled(False)
        self.reset_cat_btn.clicked.connect(self._on_reset_active_category)
        left_layout.addWidget(self.reset_cat_btn)

        self.reset_all_btn = QPushButton("Reset All to Defaults")
        self.reset_all_btn.clicked.connect(self._reset_defaults)
        left_layout.addWidget(self.reset_all_btn)

        self.splitter.addWidget(self.left_frame)

        # Right Panel: Font and Palette assignment grid
        self.right_frame = QWidget()
        right_layout = QVBoxLayout()
        self.right_frame.setLayout(right_layout)

        self.category_title_label = QLabel("All Roles")
        self.category_title_label.setStyleSheet("font-weight: bold;")
        right_layout.addWidget(self.category_title_label)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self._scroll_container = QWidget()
        self._grid = QGridLayout()
        self._grid.setAlignment(Qt.AlignTop)
        self._grid.setColumnStretch(0, 0)
        self._grid.setColumnStretch(1, 0)
        self._grid.setColumnStretch(2, 0)
        self._grid.setColumnStretch(3, 1)
        self._scroll_container.setLayout(self._grid)

        self._populate_grid()

        scroll.setWidget(self._scroll_container)
        right_layout.addWidget(scroll, 1)

        self.splitter.addWidget(self.right_frame)
        self.splitter.setSizes([180, 560])

        self.refresh_fonts()

    def _populate_grid(self):
        # Clear previous widgets if rebuilding
        for i in reversed(range(self._grid.count())):
            item = self._grid.itemAt(i)
            w = item.widget() if item else None
            if w:
                w.deleteLater()
        self._combos.clear()
        self._color_combos.clear()
        self._previews.clear()
        self._role_widgets.clear()

        # Grid column headers
        h_role = QLabel("Role")
        h_role.setFixedWidth(180)
        h_font = QLabel("Font")
        h_font.setFixedWidth(130)
        h_color = QLabel("Palette / Color")
        h_color.setFixedWidth(130)
        h_prev = QLabel("Sample Preview")

        self._grid.addWidget(h_role, 0, 0)
        self._grid.addWidget(h_font, 0, 1)
        self._grid.addWidget(h_color, 0, 2)
        self._grid.addWidget(h_prev, 0, 3)

        roles = get_ui_font_roles()
        for row_idx, (role_key, label_text, sample_text, cat_key) in enumerate(roles, start=1):
            lbl = QLabel(label_text)
            lbl.setToolTip(f"Engine role: FONT['{role_key}']")
            lbl.setFixedWidth(180)

            font_combo = ComboBox()
            font_combo.setFixedWidth(130)
            font_combo.currentTextChanged.connect(lambda val, rk=role_key: self._on_font_changed(rk, val))
            self._combos[role_key] = font_combo

            color_combo = ComboBox()
            color_combo.setFixedWidth(130)
            color_combo.currentTextChanged.connect(lambda val, rk=role_key: self._on_color_changed(rk, val))
            self._color_combos[role_key] = color_combo

            preview_lbl = QLabel()
            preview_lbl.setMinimumHeight(32)
            preview_lbl.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            preview_lbl.setStyleSheet("border: 1px solid #333; padding-left: 4px;")
            preview_lbl.setProperty("sample_text", sample_text)
            self._previews[role_key] = preview_lbl

            self._grid.addWidget(lbl, row_idx, 0)
            self._grid.addWidget(font_combo, row_idx, 1)
            self._grid.addWidget(color_combo, row_idx, 2)
            self._grid.addWidget(preview_lbl, row_idx, 3)

            self._role_widgets[role_key] = (lbl, font_combo, color_combo, preview_lbl, cat_key, label_text)

    def _on_category_changed(self, row: int):
        item = self.category_list.item(row)
        if not item:
            return
        self._current_category = item.data(Qt.UserRole) or 'all'
        self.category_title_label.setText(item.text())
        if self._current_category == 'all':
            self.reset_cat_btn.setText("Reset Category")
            self.reset_cat_btn.setEnabled(False)
        else:
            self.reset_cat_btn.setText(f"Reset {item.text()}")
            self.reset_cat_btn.setEnabled(True)
        self._update_visibility()

    def _on_search_changed(self, _):
        self._update_visibility()

    def _update_visibility(self):
        query = self._search_input.text().strip().lower()
        active_cat = self._current_category

        for role_key, (lbl, font_combo, color_combo, preview_lbl, cat_key, label_text) in self._role_widgets.items():
            cat_match = (active_cat == 'all' or cat_key == active_cat)
            text_match = (not query) or (query in role_key.lower()) or (query in label_text.lower())
            visible = cat_match and text_match
            lbl.setVisible(visible)
            font_combo.setVisible(visible)
            color_combo.setVisible(visible)
            preview_lbl.setVisible(visible)

    def _on_reset_active_category(self):
        if self._current_category and self._current_category != 'all':
            self._reset_category(self._current_category)

    def refresh_fonts(self):
        self._bmp_cache.clear()
        current_role_keys = set(self._combos.keys())
        expected_roles = get_ui_font_roles()
        expected_role_keys = {rk for rk, _, _, _ in expected_roles}
        if current_role_keys != expected_role_keys:
            self._populate_grid()

        font_nids = [f.nid for f in RESOURCES.fonts]
        if not hasattr(RESOURCES.fonts, 'ui_assignments'):
            RESOURCES.fonts.ui_assignments = {
                k: {'font': v, 'color': DEFAULT_COLOR_ASSIGNMENTS.get(k, 'white')}
                for k, v in DEFAULT_FONT_ASSIGNMENTS.items()
            }

        assignments = RESOURCES.fonts.ui_assignments

        for role_key in self._combos:
            font_combo = self._combos[role_key]
            color_combo = self._color_combos[role_key]

            font_combo.blockSignals(True)
            font_combo.clear()
            for fnid in font_nids:
                font_combo.addItem(fnid)

            raw = assignments.get(role_key)
            if isinstance(raw, dict):
                assigned_font = raw.get('font', get_default_font_for_role(role_key))
                assigned_color = raw.get('color', get_default_color_for_role(role_key))
            elif isinstance(raw, (list, tuple)) and len(raw) >= 2:
                assigned_font, assigned_color = raw[0], raw[1]
            elif isinstance(raw, str):
                assigned_font = raw
                assigned_color = get_default_color_for_role(role_key)
            else:
                assigned_font = get_default_font_for_role(role_key)
                assigned_color = get_default_color_for_role(role_key)

            if assigned_font not in font_nids and font_nids:
                default_target = get_default_font_for_role(role_key)
                assigned_font = default_target if default_target in font_nids else ('text' if 'text' in font_nids else font_nids[0])

            idx = font_combo.findText(assigned_font)
            if idx >= 0:
                font_combo.setCurrentIndex(idx)
            font_combo.blockSignals(False)

            # Populate color ComboBox with palettes from selected font
            font_prefab = RESOURCES.fonts.get(assigned_font)
            palettes = list(font_prefab.palettes.keys()) if font_prefab and font_prefab.palettes else ['white']
            color_combo.blockSignals(True)
            color_combo.clear()
            for p in palettes:
                color_combo.addItem(p)

            if assigned_color not in palettes:
                assigned_color = font_prefab.default_color if font_prefab and font_prefab.default_color in palettes else palettes[0]

            c_idx = color_combo.findText(assigned_color)
            if c_idx >= 0:
                color_combo.setCurrentIndex(c_idx)
            color_combo.blockSignals(False)

            assignments[role_key] = {'font': assigned_font, 'color': assigned_color}
            self._update_role_preview(role_key, assigned_font, assigned_color)

    def _on_font_changed(self, role_key: str, font_nid: str):
        if not font_nid:
            return
        font_prefab = RESOURCES.fonts.get(font_nid)
        palettes = list(font_prefab.palettes.keys()) if font_prefab and font_prefab.palettes else ['white']

        color_combo = self._color_combos.get(role_key)
        if color_combo:
            color_combo.blockSignals(True)
            cur_color = color_combo.currentText()
            color_combo.clear()
            for p in palettes:
                color_combo.addItem(p)

            if cur_color in palettes:
                chosen_color = cur_color
            elif font_prefab and font_prefab.default_color in palettes:
                chosen_color = font_prefab.default_color
            else:
                chosen_color = palettes[0]

            idx = color_combo.findText(chosen_color)
            if idx >= 0:
                color_combo.setCurrentIndex(idx)
            color_combo.blockSignals(False)
        else:
            chosen_color = 'white'

        RESOURCES.fonts.ui_assignments[role_key] = {'font': font_nid, 'color': chosen_color}
        if hasattr(RESOURCES.fonts, 'save_assignments'):
            RESOURCES.fonts.save_assignments()
        self._update_role_preview(role_key, font_nid, chosen_color)
        try:
            load_fonts(headless=True)
        except Exception:
            pass

    def _on_color_changed(self, role_key: str, color_name: str):
        if not color_name:
            return
        font_combo = self._combos.get(role_key)
        current_font = font_combo.currentText() if font_combo else 'text'

        RESOURCES.fonts.ui_assignments[role_key] = {'font': current_font, 'color': color_name}
        if hasattr(RESOURCES.fonts, 'save_assignments'):
            RESOURCES.fonts.save_assignments()
        self._update_role_preview(role_key, current_font, color_name)
        try:
            load_fonts(headless=True)
        except Exception:
            pass

    def _reset_category(self, cat_key: str):
        roles_in_cat = [rk for rk, _, _, ck in get_ui_font_roles() if ck == cat_key]
        font_nids = [f.nid for f in RESOURCES.fonts]
        for role_key in roles_in_cat:
            default_font = get_default_font_for_role(role_key)
            default_color = get_default_color_for_role(role_key)
            if default_font not in font_nids and font_nids:
                default_font = 'text' if 'text' in font_nids else font_nids[0]

            font_combo = self._combos.get(role_key)
            if font_combo:
                font_combo.blockSignals(True)
                idx = font_combo.findText(default_font)
                if idx >= 0:
                    font_combo.setCurrentIndex(idx)
                font_combo.blockSignals(False)

            font_prefab = RESOURCES.fonts.get(default_font)
            palettes = list(font_prefab.palettes.keys()) if font_prefab and font_prefab.palettes else ['white']

            color_combo = self._color_combos.get(role_key)
            if color_combo:
                color_combo.blockSignals(True)
                color_combo.clear()
                for p in palettes:
                    color_combo.addItem(p)
                if default_color not in palettes:
                    default_color = font_prefab.default_color if font_prefab and font_prefab.default_color in palettes else palettes[0]
                idx = color_combo.findText(default_color)
                if idx >= 0:
                    color_combo.setCurrentIndex(idx)
                color_combo.blockSignals(False)

            RESOURCES.fonts.ui_assignments[role_key] = {'font': default_font, 'color': default_color}
            self._update_role_preview(role_key, default_font, default_color)

        if hasattr(RESOURCES.fonts, 'save_assignments'):
            RESOURCES.fonts.save_assignments()
        try:
            load_fonts(headless=True)
        except Exception:
            pass

    def _reset_defaults(self):
        new_assignments = {}
        for rk, _, _, _ in get_ui_font_roles():
            new_assignments[rk] = {
                'font': get_default_font_for_role(rk),
                'color': get_default_color_for_role(rk)
            }
        RESOURCES.fonts.ui_assignments = new_assignments
        if hasattr(RESOURCES.fonts, 'save_assignments'):
            RESOURCES.fonts.save_assignments()
        self.refresh_fonts()
        try:
            load_fonts(headless=True)
        except Exception:
            pass

    def _get_bmp(self, font_nid: str):
        if font_nid not in self._bmp_cache:
            font_prefab = RESOURCES.fonts.get(font_nid)
            if font_prefab and font_prefab.image_path() and os.path.exists(font_prefab.image_path()):
                try:
                    self._bmp_cache[font_nid] = BmpFont(font_prefab, headless=True)
                except Exception:
                    self._bmp_cache[font_nid] = None
            else:
                self._bmp_cache[font_nid] = None
        return self._bmp_cache[font_nid]

    def _update_role_preview(self, role_key: str, font_nid: str, color_name: Optional[str] = None):
        lbl = self._previews.get(role_key)
        if not lbl:
            return
        sample_text = lbl.property("sample_text") or "Sample Text 123"
        bmp = self._get_bmp(font_nid)
        if not bmp:
            lbl.setText(f"({font_nid} preview unavailable)")
            return
        try:
            import pygame
            w = max(bmp.width(sample_text), 1) + 8
            h = bmp.height + 4
            surf = pygame.Surface((w, h), pygame.SRCALPHA, 32)
            bmp.blit(sample_text, surf, (2, 2), color=color_name)
            raw = engine.surf_to_raw(surf, 'RGBA')
            img = QImage(raw, w, h, QImage.Format_RGBA8888)
            pix = QPixmap.fromImage(img)
            scaled = pix.scaled(w * 2, h * 2, Qt.KeepAspectRatio, Qt.FastTransformation)
            lbl.setPixmap(scaled)
        except Exception as e:
            lbl.setText(f"Preview error: {e}")

    @classmethod
    def create(cls, parent=None, db=None, res=None):
        return cls(parent)

    def windowTitle(self) -> str:
        return "UI Assignments"

    def reset(self):
        self.refresh_fonts()


FontAssignmentDatabase = FontAssignmentsWidget


class NewFontDatabase(NewEditorTab):
    catalog_type = FontCatalog
    properties_type = font_properties.FontProperties
    allow_rename = True
    allow_duplicate = True
    icon_size = 32

    def __init__(self, parent=None, database=None, resources=None, *args, **kwargs):
        super().__init__(parent, database or DB, resources or RESOURCES)
        self.setWindowTitle("Fonts")
        self._setup_legacy_compat()

    def _setup_legacy_compat(self):
        def _set_current_row(row: int):
            keys = list(self.data.keys())
            if 0 <= row < len(keys):
                nid = keys[row]
                self.tree_list.select_item(nid)
                self.on_select(nid)

        self.left_frame.set_current_row = _set_current_row

        parent_tab = self

        class _ModelProxy:
            @staticmethod
            def create_new():
                new_font = font_model.create_new_font(parent_tab)
                if new_font:
                    parent_tab.reset()
                    parent_tab.tree_list.select_item(new_font.nid)
                    parent_tab.on_select(new_font.nid)
                return new_font

        self.left_frame.model = _ModelProxy()

    @property
    def data(self):
        return self._res.fonts if self._res else RESOURCES.fonts

    def get_icon(self, font_nid: NID) -> Optional[QIcon]:
        if not self.data.get(font_nid):
            return None
        font = self.data.get(font_nid)
        pix = font_model.get_font_preview_pixmap(font)
        if pix:
            return QIcon(pix)
        return None

    def create_new(self, nid=None):
        new_font = font_model.create_new_font(self)
        if new_font:
            return [new_font.nid]
        return False

    def duplicate(self, old_nid: NID, nid: NID):
        if self.data.get(nid):
            QMessageBox.warning(self, 'Warning', 'ID %s already in use' % nid)
            return False
        old_font = self.data.get(old_nid)
        if not old_font:
            return False
        new_font = Font.restore(old_font.save())
        new_font.nid = nid
        self.data.append(new_font)
        return True

    def _on_nid_changed(self, old_nid: NID, new_nid: NID):
        HISTORY.rewrite(RType.FONTS, old_nid, new_nid)

    def _on_delete(self, nid: NID) -> bool:
        return reference_dialogs.check_delete(RType.FONTS, nid, 'Font', self)

    @classmethod
    def edit(cls, parent=None):
        return get_full_editor(parent)


FontDatabase = NewFontDatabase


def get_full_editor(parent=None) -> NewMultiResourceEditor:
    editor = NewMultiResourceEditor(
        (NewFontDatabase, FontPaletteDatabase, FontAssignmentDatabase),
        ('fonts',),
        parent
    )
    editor.setWindowTitle("Font Editor")
    editor.resize(760, 520)
    return editor


# Testing
# Run "python -m app.editor.font_editor.font_tab" from main directory
if __name__ == '__main__':
    import sys
    from PyQt5.QtWidgets import QApplication
    app = QApplication(sys.argv)
    from app.data.serialization.versions import CURRENT_SERIALIZATION_VERSION
    RESOURCES.load('default.ltproj', CURRENT_SERIALIZATION_VERSION)
    window = get_full_editor()
    window.show()
    app.exec_()