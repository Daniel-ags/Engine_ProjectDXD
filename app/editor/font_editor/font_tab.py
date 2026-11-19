import os
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTabWidget, QGroupBox,
    QLabel, QPushButton, QScrollArea, QGridLayout, QLineEdit
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QImage, QPixmap

from app.data.resources.resources import RESOURCES
from app.data.resources.fonts import DEFAULT_FONT_ASSIGNMENTS
from app.editor.base_database_gui import DatabaseTab
from app.editor.data_editor import SingleResourceEditor
from app.editor.font_editor import font_model, font_properties
from app.editor.font_editor.palette_tab import PaletteEditorWidget
from app.engine.bmpfont import BmpFont
from app.engine import engine
from app.engine.fonts import load_fonts
from app.extensions.custom_gui import ComboBox


FONT_ROLE_CATEGORIES = [
    ('global', "1. Core & Fallbacks (Global Engine Roles)"),
    ('story', "2. Narrative & Dialogue (Events & Lore)"),
    ('menu', "3. Menus & Navigation (Options & Prep)"),
    ('status', "4. Unit Status & Stats (Growth & Ranks)"),
    ('combat', "5. Combat Experience (Forecast & Battle HUD)"),
    ('progression', "6. Progression & Alerts (Level Up & Promo)"),
    ('postgame', "7. Records & Post-Game (Hall of Fame & Credits)"),
]

UI_FONT_ROLES = [
    # 1. Globais & Sistema
    ('text', "General UI & Base Text", "Iron Sword  Mt 5  Hit 90", 'global'),
    ('narrow', "Condensed / Narrow Text", "Vulnerary (3/3)  Longsword", 'global'),
    ('small', "Small Labels & Indicators", "Def +2  Avo +10  Cost 1", 'global'),
    ('system_debug', "FPS Counter & Diagnostics", "FPS: 60 (Min: 58)  Speed: 1x", 'global'),

    # 2. Narrativa & Diálogos
    ('convo', "Main Dialogue", "Shall we head into battle, commander?", 'story'),
    ('convo_bold', "Emphasized Dialogue (<b>)", "Stand back! This is dangerous!", 'story'),
    ('convo_italic', "Thoughts & Narration (<i>)", "(Could this be the legendary blade...?)", 'story'),
    ('convo_narrow', "Compact Dialogue", "We must reach the fortress before nightfall!", 'story'),
    ('chapter_title', "Chapter Title Ribbon", "Chapter 1: Maiden of the Plains", 'story'),

    # 3. Menus & Navegação
    ('ui_choice', "Action & Command Menus", "Attack   Item   Trade   Wait", 'menu'),
    ('ui_prep', "Battle Preparation Screens", "Manage Items   Check Map   Fight!", 'menu'),
    ('ui_save_load', "Save / Load Slots", "File 1: Ch 4  Turn 12  Gold 5400G", 'menu'),

    # 4. Ficha de Unidade & Estatísticas
    ('ui_info', "Status & Profile Screen", "STR 14   MAG 8   SKL 16   SPD 15", 'status'),
    ('ui_stat_bonus', "Stat Modifiers & Buffs", "+3 SPD   -2 DEF   +5 HIT", 'status'),
    ('ui_weapon_rank', "Weapon Mastery Ranks", "S   A   B   C   D   E", 'status'),
    ('ui_help', "Tooltips & Help Boxes", "Effective against cavalry and armored units.", 'status'),

    # 5. Combate & HUD de Batalha
    ('ui_combat', "Combat Forecast HUD", "Atk 24   Hit 85%   Crit 12%   AS 14", 'combat'),
    ('combat_numbers', "Battle Hit, Damage & Crit", "32 / 45   Dmg 14   Hit 95", 'combat'),
    ('combat_multipliers', "Attack Multipliers", "x2   x3   x4", 'combat'),
    ('health_bar', "Overhead Health Bars", "HP 28 / 28   Guard 100%", 'combat'),

    # 6. Progressão, Promoção & Avisos
    ('ui_level_up', "Level Up Screen", "Level 12 Paladin   EXP 100", 'progression'),
    ('ui_level_up_bonus', "Level Up Stat Ticks (+1)", "+1 HP   +1 STR   +1 SPD", 'progression'),
    ('ui_promo', "Promotion & Class Change", "Promote to Hero?  Gain Sol & Axes", 'progression'),
    ('ui_banner', "Alerts & Notifications", "Learned Skill: Adept!   Item: Silver Bow", 'progression'),

    # 7. Pós-Jogo, Registros & Créditos
    ('ui_record_book', "Hall of Fame & Record Book", "Overall MVP: Ephraim   Total Turns: 84", 'postgame'),
    ('ui_victory', "Chapter Victory Summary", "Chapter Complete!   Cleared in 8 Turns", 'postgame'),
    ('ui_credits_title', "Credits Department Titles", "Lead Designer & Programmer", 'postgame'),
    ('ui_credits_body', "Credits Staff Roll & Thanks", "Special Thanks to the Lex Talionis Community", 'postgame'),
]


class FontAssignmentsWidget(QWidget):
    """Aba 2 do Font Editor: permite escolher qual fonte cada parte do jogo utiliza."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._combos: dict[str, ComboBox] = {}
        self._previews: dict[str, QLabel] = {}
        self._role_widgets: dict[str, tuple] = {}
        self._category_boxes: dict[str, QGroupBox] = {}
        self._bmp_cache: dict[str, BmpFont] = {}

        main_layout = QVBoxLayout()
        self.setLayout(main_layout)

        # Header com Instruções e Botão de Reset Geral
        header_row = QHBoxLayout()
        info_label = QLabel(
            "Configure which project font is assigned to each functional system across 7 categorized groups. "
            "Previews update live and changes are saved automatically to your project."
        )
        info_label.setWordWrap(True)
        header_row.addWidget(info_label, 1)

        reset_btn = QPushButton("Reset All to Defaults")
        reset_btn.setFixedWidth(150)
        reset_btn.clicked.connect(self._reset_defaults)
        header_row.addWidget(reset_btn)
        main_layout.addLayout(header_row)

        # Barra de Pesquisa Rápida
        search_row = QHBoxLayout()
        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("Search font roles (e.g. combat, dialogue, status, banner, numbers)...")
        self._search_input.textChanged.connect(self._on_search_changed)
        search_row.addWidget(self._search_input)
        main_layout.addLayout(search_row)

        # Scroll container com as 7 categorias
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        container_layout = QVBoxLayout()
        container.setLayout(container_layout)

        # Criação dos GroupBoxes por Categoria
        cat_grids: dict[str, QGridLayout] = {}
        cat_row_counts: dict[str, int] = {}
        for cat_key, cat_title in FONT_ROLE_CATEGORIES:
            grp = QGroupBox(cat_title)
            grp.setStyleSheet("QGroupBox { font-weight: bold; margin-top: 6px; } QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 4px; }")
            grp_layout = QVBoxLayout()
            grp.setLayout(grp_layout)

            cat_header = QHBoxLayout()
            cat_header.addStretch()
            cat_reset_btn = QPushButton("Reset Category")
            cat_reset_btn.setToolTip(f"Reset {cat_title} roles to defaults")
            cat_reset_btn.setFixedWidth(120)
            cat_reset_btn.clicked.connect(lambda _, ck=cat_key: self._reset_category(ck))
            cat_header.addWidget(cat_reset_btn)
            grp_layout.addLayout(cat_header)

            grid = QGridLayout()
            grid.setColumnStretch(0, 0)
            grid.setColumnStretch(1, 0)
            grid.setColumnStretch(2, 1)
            grp_layout.addLayout(grid)

            self._category_boxes[cat_key] = grp
            cat_grids[cat_key] = grid
            cat_row_counts[cat_key] = 0
            container_layout.addWidget(grp)

        # Preenchimento de cada papel
        for role_key, label_text, sample_text, cat_key in UI_FONT_ROLES:
            grid = cat_grids[cat_key]
            row = cat_row_counts[cat_key]

            lbl = QLabel(f"<b>{label_text}</b><br><span style='color:#888;font-size:10px;'>FONT['{role_key}']</span>")
            lbl.setFixedWidth(220)

            combo = ComboBox()
            combo.setFixedWidth(140)
            combo.currentTextChanged.connect(lambda val, rk=role_key: self._on_role_changed(rk, val))
            self._combos[role_key] = combo

            preview_lbl = QLabel()
            preview_lbl.setMinimumHeight(36)
            preview_lbl.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            preview_lbl.setStyleSheet("background-color: #283040; border: 1px solid #555; padding-left: 6px;")
            preview_lbl.setProperty("sample_text", sample_text)
            self._previews[role_key] = preview_lbl

            grid.addWidget(lbl, row, 0)
            grid.addWidget(combo, row, 1)
            grid.addWidget(preview_lbl, row, 2)

            self._role_widgets[role_key] = (lbl, combo, preview_lbl, cat_key, label_text)
            cat_row_counts[cat_key] += 1

        container_layout.addStretch()
        scroll.setWidget(container)
        main_layout.addWidget(scroll)

        self.refresh_fonts()

    def _on_search_changed(self, text: str):
        query = text.strip().lower()
        cat_visibility = {cat_key: False for cat_key, _ in FONT_ROLE_CATEGORIES}

        for role_key, (lbl, combo, preview_lbl, cat_key, label_text) in self._role_widgets.items():
            matches = (not query) or (query in role_key.lower()) or (query in label_text.lower())
            lbl.setVisible(matches)
            combo.setVisible(matches)
            preview_lbl.setVisible(matches)
            if matches:
                cat_visibility[cat_key] = True

        for cat_key, grp in self._category_boxes.items():
            grp.setVisible(cat_visibility[cat_key])

    def refresh_fonts(self):
        self._bmp_cache.clear()
        font_nids = [f.nid for f in RESOURCES.fonts]
        if not hasattr(RESOURCES.fonts, 'ui_assignments'):
            RESOURCES.fonts.ui_assignments = DEFAULT_FONT_ASSIGNMENTS.copy()

        assignments = RESOURCES.fonts.ui_assignments

        for role_key, combo in self._combos.items():
            combo.blockSignals(True)
            combo.clear()
            for fnid in font_nids:
                combo.addItem(fnid)

            assigned_nid = assignments.get(role_key, DEFAULT_FONT_ASSIGNMENTS.get(role_key, 'text'))
            if assigned_nid not in font_nids and font_nids:
                default_target = DEFAULT_FONT_ASSIGNMENTS.get(role_key, 'text')
                assigned_nid = default_target if default_target in font_nids else ('text' if 'text' in font_nids else font_nids[0])
                assignments[role_key] = assigned_nid

            idx = combo.findText(assigned_nid)
            if idx >= 0:
                combo.setCurrentIndex(idx)
            combo.blockSignals(False)
            self._update_role_preview(role_key, assigned_nid)

    def _on_role_changed(self, role_key: str, font_nid: str):
        if not font_nid:
            return
        RESOURCES.fonts.ui_assignments[role_key] = font_nid
        if hasattr(RESOURCES.fonts, 'save_assignments'):
            RESOURCES.fonts.save_assignments()
        self._update_role_preview(role_key, font_nid)
        try:
            load_fonts(headless=True)
        except Exception:
            pass

    def _reset_category(self, cat_key: str):
        roles_in_cat = [rk for rk, _, _, ck in UI_FONT_ROLES if ck == cat_key]
        font_nids = [f.nid for f in RESOURCES.fonts]
        for role_key in roles_in_cat:
            default_nid = DEFAULT_FONT_ASSIGNMENTS.get(role_key, 'text')
            if default_nid not in font_nids and font_nids:
                default_nid = 'text' if 'text' in font_nids else font_nids[0]
            RESOURCES.fonts.ui_assignments[role_key] = default_nid
            combo = self._combos.get(role_key)
            if combo:
                combo.blockSignals(True)
                idx = combo.findText(default_nid)
                if idx >= 0:
                    combo.setCurrentIndex(idx)
                combo.blockSignals(False)
            self._update_role_preview(role_key, default_nid)

        if hasattr(RESOURCES.fonts, 'save_assignments'):
            RESOURCES.fonts.save_assignments()
        try:
            load_fonts(headless=True)
        except Exception:
            pass

    def _reset_defaults(self):
        RESOURCES.fonts.ui_assignments = DEFAULT_FONT_ASSIGNMENTS.copy()
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

    def _update_role_preview(self, role_key: str, font_nid: str):
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
            bmp.blit(sample_text, surf, (2, 2))
            raw = engine.surf_to_raw(surf, 'RGBA')
            img = QImage(raw, w, h, QImage.Format_RGBA8888)
            pix = QPixmap.fromImage(img)
            scaled = pix.scaled(w * 2, h * 2, Qt.KeepAspectRatio, Qt.FastTransformation)
            lbl.setPixmap(scaled)
        except Exception as e:
            lbl.setText(f"Preview error: {e}")


class FontDatabase(DatabaseTab):
    def __init__(self, data, title, right_frame, deletion_criteria, collection_model, parent=None):
        super().__init__(data, title, right_frame, deletion_criteria, collection_model, parent)
        self._wrap_in_tabs()

    def _wrap_in_tabs(self):
        """Envelopa o splitter original do DatabaseTab na Aba 1 e adiciona a Aba 2."""
        # DatabaseTab define self.layout como um atributo QHBoxLayout (não um método)
        old_layout = self.layout if not callable(self.layout) else self.layout()
        catalog_page = QWidget(self)
        catalog_layout = QHBoxLayout()
        catalog_layout.setContentsMargins(0, 0, 0, 0)
        catalog_page.setLayout(catalog_layout)

        # Move todos os widgets/layouts originais para dentro de catalog_page
        while old_layout.count():
            item = old_layout.takeAt(0)
            if item.widget():
                catalog_layout.addWidget(item.widget())
            elif item.layout():
                catalog_layout.addLayout(item.layout())

        self.tabs = QTabWidget(self)
        self.palette_tab = PaletteEditorWidget(self)
        self.assignments_tab = FontAssignmentsWidget(self)
        self.tabs.addTab(catalog_page, "Font Catalog")
        self.tabs.addTab(self.palette_tab, "Palette Editor")
        self.tabs.addTab(self.assignments_tab, "UI Font Assignments")
        self.tabs.currentChanged.connect(self._on_tab_changed)
        self.palette_tab.palettes_updated.connect(self.assignments_tab.refresh_fonts)

        old_layout.addWidget(self.tabs)

    def _on_tab_changed(self, index: int):
        if index == 1:
            self.palette_tab.refresh_all()
        elif index == 2:
            self.assignments_tab.refresh_fonts()

    def reset(self):
        super().reset()
        if hasattr(self, 'palette_tab'):
            self.palette_tab.refresh_all()
        if hasattr(self, 'assignments_tab'):
            self.assignments_tab.refresh_fonts()

    @classmethod
    def create(cls, parent=None):
        data = RESOURCES.fonts
        title = 'Font'
        right_frame = font_properties.FontProperties
        collection_model = font_model.FontModel
        dialog = cls(data, title, right_frame, (None, lambda *_: False, None), collection_model, parent)
        return dialog

    @classmethod
    def edit(cls, parent=None):
        return SingleResourceEditor(FontDatabase, ['fonts'], parent)


# Testing
# Run "python -m app.editor.font_editor.font_tab" from main directory
if __name__ == '__main__':
    import sys
    from PyQt5.QtWidgets import QApplication
    app = QApplication(sys.argv)
    from app.data.serialization.versions import CURRENT_SERIALIZATION_VERSION
    RESOURCES.load('default.ltproj', CURRENT_SERIALIZATION_VERSION)
    window = SingleResourceEditor(FontDatabase, ['fonts'])
    window.show()
    app.exec_()