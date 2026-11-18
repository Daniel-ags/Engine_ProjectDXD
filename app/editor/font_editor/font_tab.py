import os
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTabWidget, QGroupBox,
    QLabel, QPushButton, QScrollArea, QGridLayout
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QImage, QPixmap

from app.data.resources.resources import RESOURCES
from app.data.resources.fonts import DEFAULT_FONT_ASSIGNMENTS
from app.editor.base_database_gui import DatabaseTab
from app.editor.data_editor import SingleResourceEditor
from app.editor.font_editor import font_model, font_properties
from app.engine.bmpfont import BmpFont
from app.engine import engine
from app.engine.fonts import load_fonts
from app.extensions.custom_gui import ComboBox


UI_FONT_ROLES = [
    # Grupo Global
    ('text', "General UI & Menus (text)", "Iron Sword  Mt 5  Hit 90", 'global'),
    ('convo', "Dialogues & Lore (convo)", "Shall we head into battle?", 'global'),
    ('number', "Numbers & Counters (number)", "45 / 45   100", 'global'),
    ('small', "Small HUD Labels (small)", "Lv 10  EXP 85", 'global'),
    ('chapter', "Chapter Headers (chapter)", "Chapter 1: Prologue", 'global'),
    # Grupo por Tela (Aliases Semânticos)
    ('ui_promo', "Promotion & Reclass Screen", "Skills & Weapons   +3 SPD", 'screen'),
    ('ui_info', "Unit Info & Status Screen", "STR 14   MAG 8   SKL 16", 'screen'),
    ('ui_choice', "Command & Choice Menus", "Attack   Item   Wait", 'screen'),
    ('ui_banner', "Pop-up Banners & Alerts", "Learned Skill: Adept!", 'screen'),
    ('ui_combat', "Combat Forecast & HUD", "HP 32   Dmg 14   Hit 92%", 'screen'),
]


class FontAssignmentsWidget(QWidget):
    """Aba 2 do Font Editor: permite escolher qual fonte cada parte do jogo utiliza."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._combos: dict[str, ComboBox] = {}
        self._previews: dict[str, QLabel] = {}
        self._bmp_cache: dict[str, BmpFont] = {}

        main_layout = QVBoxLayout()
        self.setLayout(main_layout)

        header_row = QHBoxLayout()
        info_label = QLabel(
            "Select which project font is assigned to each global role or specific game screen. "
            "Previews update live."
        )
        info_label.setWordWrap(True)
        header_row.addWidget(info_label, 1)

        reset_btn = QPushButton("Reset to Defaults")
        reset_btn.setFixedWidth(130)
        reset_btn.clicked.connect(self._reset_defaults)
        header_row.addWidget(reset_btn)
        main_layout.addLayout(header_row)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        container_layout = QVBoxLayout()
        container.setLayout(container_layout)

        global_group = QGroupBox("Global Engine Roles (Overrides Everywhere)")
        global_grid = QGridLayout()
        global_group.setLayout(global_grid)

        screen_group = QGroupBox("Screen-Specific Overrides (Semantic Aliases)")
        screen_grid = QGridLayout()
        screen_group.setLayout(screen_grid)

        g_row, s_row = 0, 0
        for role_key, label_text, sample_text, group_type in UI_FONT_ROLES:
            grid = global_grid if group_type == 'global' else screen_grid
            row = g_row if group_type == 'global' else s_row

            lbl = QLabel(f"<b>{label_text}</b><br><span style='color:#888;font-size:10px;'>FONT['{role_key}']</span>")
            lbl.setFixedWidth(210)

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

            if group_type == 'global':
                g_row += 1
            else:
                s_row += 1

        container_layout.addWidget(global_group)
        container_layout.addWidget(screen_group)
        container_layout.addStretch()
        scroll.setWidget(container)
        main_layout.addWidget(scroll)

        self.refresh_fonts()

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
                assigned_nid = 'text' if 'text' in font_nids else font_nids[0]

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

    def _reset_defaults(self):
        RESOURCES.fonts.ui_assignments = DEFAULT_FONT_ASSIGNMENTS.copy()
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
        self.assignments_tab = FontAssignmentsWidget(self)
        self.tabs.addTab(catalog_page, "Font Catalog")
        self.tabs.addTab(self.assignments_tab, "UI Font Assignments")
        self.tabs.currentChanged.connect(self._on_tab_changed)

        old_layout.addWidget(self.tabs)

    def _on_tab_changed(self, index: int):
        if index == 1:
            self.assignments_tab.refresh_fonts()

    def reset(self):
        super().reset()
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