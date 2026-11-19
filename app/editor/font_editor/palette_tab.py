import os
from typing import Dict, List, Optional, Tuple

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QGroupBox,
    QLabel, QPushButton, QListWidget, QListWidgetItem, QLineEdit,
    QColorDialog, QMessageBox, QInputDialog, QScrollArea, QCheckBox
)
from PyQt5.QtCore import Qt, pyqtSignal, QEvent
from PyQt5.QtGui import QColor, QImage, QPixmap, QWheelEvent

from app.data.resources.resources import RESOURCES
from app.data.resources.fonts import (
    Font, Color4, DEFAULT_UI_PALETTES, DEFAULT_DIALOGUE_PALETTES,
    DEFAULT_GLOBAL_PALETTE_PROFILES, DEFAULT_GLOBAL_PALETTES, adapt_palette_to_font
)
from app.engine import engine, image_mods
from app.engine.bmpfont import BmpFont
from app.extensions.custom_gui import ComboBox


PRESET_BACKGROUNDS = [
    ("Menu Dark (#202838)", QColor(0x20, 0x28, 0x38)),
    ("Parchment Light (#E0E0D8)", QColor(0xE0, 0xE0, 0xD8)),
    ("Dialogue Bubble (#F8F8F0)", QColor(0xF8, 0xF8, 0xF0)),
    ("Deep Black (#080808)", QColor(0x08, 0x08, 0x08)),
    ("Navy Combat (#101828)", QColor(0x10, 0x18, 0x28)),
]

SAMPLE_TEXTS = {
    'default': "Iron Sword  Mt 5  Hit 90  Crit 0",
    'dialogue': "Shall we head into battle, commander?",
    'stats': "HP 32/45   STR 14   MAG 8   SKL 16",
    'numbers': "1234567890   +3 SPD   -2 DEF",
}

PALETTE_PROFILES_META = [
    ('ui_3color', "UI & Menus (3 Colors)", "Body, Shadow, Midtone — Light text for dark menus"),
    ('dialogue_2color', "Dialogue & Story (2 Colors)", "Ink Body, Shadow — Dark text for light speech bubbles"),
    ('custom', "Custom Ramps", "Multi-color gradients and special fonts"),
]


class ZoomableScrollArea(QScrollArea):
    """QScrollArea que intercepta wheelEvent para permitir Zoom In e Zoom Out via scroll do mouse."""
    zoom_changed = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)

    def wheelEvent(self, event: QWheelEvent):
        delta = event.angleDelta().y()
        if delta > 0:
            self.zoom_changed.emit(1)
            event.accept()
        elif delta < 0:
            self.zoom_changed.emit(-1)
            event.accept()
        else:
            super().wheelEvent(event)


class PaletteEditorWidget(QWidget):
    """Aba de Gerenciamento e Bancada de Testes de Paletas Globais de Fontes."""
    palettes_updated = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_profile_key: str = 'ui_3color'
        self._current_palette_name: Optional[str] = None
        self._bmp_cache: Dict[str, BmpFont] = {}
        self._preview_bg_color = PRESET_BACKGROUNDS[0][1]
        self._preview_zoom: float = 2.0
        self._showcase_selected_fonts: List[str] = ['text', 'convo', 'profont', 'small']

        main_layout = QVBoxLayout()
        self.setLayout(main_layout)

        # -- Top Action Bar --
        action_bar = QHBoxLayout()
        
        info_label = QLabel(
            "<b>Global Font Palettes</b>: Configure shared color ramps inherited by imported fonts. "
            "Separated by profile (UI vs Dialogue) to prevent contrast inversion."
        )
        action_bar.addWidget(info_label, 1)

        apply_font_btn = QPushButton("Apply to Test Font")
        apply_font_btn.setToolTip("Inject current palette into the currently selected test font")
        apply_font_btn.clicked.connect(self._apply_current_to_selected_font)
        action_bar.addWidget(apply_font_btn)

        apply_all_btn = QPushButton("Apply to All Fonts")
        apply_all_btn.setToolTip("Inject this palette into every project font")
        apply_all_btn.clicked.connect(self._apply_current_to_all_fonts)
        action_bar.addWidget(apply_all_btn)

        sync_all_btn = QPushButton("Sync All Palettes to All Fonts")
        sync_all_btn.setToolTip("Propagate all global palettes across every project font using matching profiles")
        sync_all_btn.clicked.connect(self._sync_all_palettes_to_all_fonts)
        action_bar.addWidget(sync_all_btn)

        reset_all_btn = QPushButton("Reset Palettes to Factory")
        reset_all_btn.setToolTip("Restore all global palette profiles to canonical GBA defaults")
        reset_all_btn.clicked.connect(self._reset_to_factory)
        action_bar.addWidget(reset_all_btn)

        main_layout.addLayout(action_bar)

        # -- Main Content Splitter --
        splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(splitter, 1)

        # Left Column: Palette List & Profile Selector
        left_widget = QWidget()
        left_layout = QVBoxLayout()
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_widget.setLayout(left_layout)

        profile_row = QHBoxLayout()
        profile_row.addWidget(QLabel("<b>Profile:</b>"))
        self.profile_combo = ComboBox()
        for pkey, plabel, pdesc in PALETTE_PROFILES_META:
            self.profile_combo.addItem(plabel, pkey)
        self.profile_combo.currentIndexChanged.connect(self._on_profile_changed)
        profile_row.addWidget(self.profile_combo, 1)
        left_layout.addLayout(profile_row)

        search_box = QLineEdit()
        search_box.setPlaceholderText("Search palette in profile...")
        search_box.textChanged.connect(self._on_search_palette)
        self._search_box = search_box
        left_layout.addWidget(search_box)

        self.palette_list = QListWidget()
        self.palette_list.currentTextChanged.connect(self._on_palette_selected)
        left_layout.addWidget(self.palette_list, 1)

        list_btn_row = QHBoxLayout()
        add_btn = QPushButton("+ Add")
        add_btn.clicked.connect(self._add_palette)
        del_btn = QPushButton("− Delete")
        del_btn.clicked.connect(self._delete_palette)
        dup_btn = QPushButton("Duplicate")
        dup_btn.clicked.connect(self._duplicate_palette)
        list_btn_row.addWidget(add_btn)
        list_btn_row.addWidget(del_btn)
        list_btn_row.addWidget(dup_btn)
        left_layout.addLayout(list_btn_row)

        splitter.addWidget(left_widget)

        # Middle Column: Palette Colors Swatch Editor
        mid_group = QGroupBox("Selected Palette Colors")
        mid_layout = QVBoxLayout()
        mid_group.setLayout(mid_layout)

        self._pal_title_label = QLabel("<b>Palette:</b> (none)")
        mid_layout.addWidget(self._pal_title_label)

        swatch_scroll = QScrollArea()
        swatch_scroll.setWidgetResizable(True)
        self._swatch_container = QWidget()
        self._swatch_layout = QVBoxLayout()
        self._swatch_layout.setAlignment(Qt.AlignTop)
        self._swatch_container.setLayout(self._swatch_layout)
        swatch_scroll.setWidget(self._swatch_container)
        mid_layout.addWidget(swatch_scroll, 1)

        twin_btn = QPushButton("⇄ Generate Twin Profile Counterpart")
        twin_btn.setToolTip("Automatically generate 2-color dialogue version from 3-color UI, or vice versa")
        twin_btn.clicked.connect(self._generate_twin_profile)
        mid_layout.addWidget(twin_btn)

        swatch_ctrl_row = QHBoxLayout()
        add_color_btn = QPushButton("+ Color Slot")
        add_color_btn.clicked.connect(self._add_swatch_color)
        del_color_btn = QPushButton("− Remove Slot")
        del_color_btn.clicked.connect(self._del_swatch_color)
        swatch_ctrl_row.addWidget(add_color_btn)
        swatch_ctrl_row.addWidget(del_color_btn)
        mid_layout.addLayout(swatch_ctrl_row)

        splitter.addWidget(mid_group)

        # Right Column: Interactive Test Bench
        test_group = QGroupBox("Interactive Test Bench (Live Preview)")
        test_layout = QVBoxLayout()
        test_group.setLayout(test_layout)

        test_ctrl_row = QHBoxLayout()
        test_ctrl_row.addWidget(QLabel("Test Font:"))
        self.font_combo = ComboBox()
        self.font_combo.setFixedWidth(160)
        self.font_combo.currentTextChanged.connect(self._update_test_preview)
        test_ctrl_row.addWidget(self.font_combo)

        test_ctrl_row.addWidget(QLabel("Background:"))
        self.bg_combo = ComboBox()
        for label, _ in PRESET_BACKGROUNDS:
            self.bg_combo.addItem(label)
        self.bg_combo.currentIndexChanged.connect(self._on_bg_changed)
        test_ctrl_row.addWidget(self.bg_combo)

        # Zoom Controls
        test_ctrl_row.addWidget(QLabel("<b>Zoom:</b>"))
        zoom_out_btn = QPushButton("−")
        zoom_out_btn.setFixedSize(24, 24)
        zoom_out_btn.setToolTip("Zoom Out (or scroll wheel down on preview)")
        zoom_out_btn.clicked.connect(lambda: self._adjust_zoom(-1))
        test_ctrl_row.addWidget(zoom_out_btn)

        self._zoom_label = QLabel("200%")
        self._zoom_label.setFixedWidth(40)
        self._zoom_label.setAlignment(Qt.AlignCenter)
        test_ctrl_row.addWidget(self._zoom_label)

        zoom_in_btn = QPushButton("+")
        zoom_in_btn.setFixedSize(24, 24)
        zoom_in_btn.setToolTip("Zoom In (or scroll wheel up on preview)")
        zoom_in_btn.clicked.connect(lambda: self._adjust_zoom(1))
        test_ctrl_row.addWidget(zoom_in_btn)

        zoom_reset_btn = QPushButton("Reset 1x")
        zoom_reset_btn.setToolTip("Reset to native 100% scale")
        zoom_reset_btn.clicked.connect(lambda: self._set_zoom(1.0))
        test_ctrl_row.addWidget(zoom_reset_btn)

        test_ctrl_row.addStretch()
        test_layout.addLayout(test_ctrl_row)

        text_input_row = QHBoxLayout()
        text_input_row.addWidget(QLabel("Sample Text:"))
        self.test_text_input = QLineEdit()
        self.test_text_input.setText(SAMPLE_TEXTS['default'])
        self.test_text_input.textChanged.connect(self._update_test_preview)
        text_input_row.addWidget(self.test_text_input, 1)

        preset_text_combo = ComboBox()
        preset_text_combo.addItem("Presets...")
        for k, v in SAMPLE_TEXTS.items():
            preset_text_combo.addItem(f"{k}: {v[:16]}...", v)
        preset_text_combo.currentIndexChanged.connect(self._on_preset_text_chosen)
        text_input_row.addWidget(preset_text_combo)
        test_layout.addLayout(text_input_row)

        # Multi-Font Showcase Header & Controls
        showcase_ctrl_row = QHBoxLayout()
        self.multi_font_check = QCheckBox("Showcase Multi-Font Comparison")
        self.multi_font_check.stateChanged.connect(self._on_showcase_toggle)
        showcase_ctrl_row.addWidget(self.multi_font_check)

        self._showcase_add_combo = ComboBox()
        self._showcase_add_combo.addItem("+ Add Font to Showcase...")
        self._showcase_add_combo.currentIndexChanged.connect(self._on_showcase_add_chosen)
        self._showcase_add_combo.setVisible(False)
        showcase_ctrl_row.addWidget(self._showcase_add_combo)

        self._showcase_clear_btn = QPushButton("Clear Showcase")
        self._showcase_clear_btn.setVisible(False)
        self._showcase_clear_btn.clicked.connect(self._on_showcase_clear)
        showcase_ctrl_row.addWidget(self._showcase_clear_btn)

        showcase_ctrl_row.addStretch()
        test_layout.addLayout(showcase_ctrl_row)

        # Showcase Active Chips Bar
        self._showcase_chips_widget = QWidget()
        self._showcase_chips_layout = QHBoxLayout()
        self._showcase_chips_layout.setContentsMargins(0, 0, 0, 0)
        self._showcase_chips_widget.setLayout(self._showcase_chips_layout)
        self._showcase_chips_widget.setVisible(False)
        test_layout.addWidget(self._showcase_chips_widget)

        # Preview Display Box with Zoomable Scroll Area
        preview_scroll = ZoomableScrollArea()
        preview_scroll.zoom_changed.connect(self._adjust_zoom)
        self._preview_container = QWidget()
        self._preview_layout = QVBoxLayout()
        self._preview_layout.setAlignment(Qt.AlignCenter)
        self._preview_container.setLayout(self._preview_layout)
        preview_scroll.setWidget(self._preview_container)
        test_layout.addWidget(preview_scroll, 1)

        self.main_preview_label = QLabel()
        self.main_preview_label.setAlignment(Qt.AlignCenter)
        self._preview_layout.addWidget(self.main_preview_label)

        self.showcase_rows: List[QWidget] = []

        splitter.addWidget(test_group)
        splitter.setSizes([180, 260, 420])

        self.refresh_all()

    def refresh_all(self):
        self._populate_font_combo()
        self._populate_palette_list()

    def _get_active_profile_palettes(self) -> Dict[str, List[Color4]]:
        profiles = getattr(RESOURCES.fonts, 'palette_profiles', None)
        if not profiles:
            RESOURCES.fonts.palette_profiles = {
                'ui_3color': {k: list(v) for k, v in DEFAULT_UI_PALETTES.items()},
                'dialogue_2color': {k: list(v) for k, v in DEFAULT_DIALOGUE_PALETTES.items()},
                'custom': {},
            }
            profiles = RESOURCES.fonts.palette_profiles
        if self._current_profile_key not in profiles:
            profiles[self._current_profile_key] = {}
        return profiles[self._current_profile_key]

    def _on_profile_changed(self, idx: int):
        self._current_profile_key = self.profile_combo.currentData() or 'ui_3color'
        # Atualiza a fonte de teste sugerida e o background para combinar com o perfil
        if self._current_profile_key == 'dialogue_2color':
            if 'convo' in [f.nid for f in RESOURCES.fonts]:
                self.font_combo.setCurrentText('convo')
            # Seleciona Dialogue Bubble (#F8F8F0)
            self.bg_combo.setCurrentIndex(2)
            self.test_text_input.setText(SAMPLE_TEXTS['dialogue'])
        elif self._current_profile_key == 'ui_3color':
            if 'text' in [f.nid for f in RESOURCES.fonts]:
                self.font_combo.setCurrentText('text')
            # Seleciona Menu Dark (#202838)
            self.bg_combo.setCurrentIndex(0)
            self.test_text_input.setText(SAMPLE_TEXTS['default'])

        self._populate_palette_list()

    def _populate_font_combo(self):
        curr = self.font_combo.currentText()
        self.font_combo.blockSignals(True)
        self.font_combo.clear()
        for f in RESOURCES.fonts:
            self.font_combo.addItem(f.nid)
        if curr in [f.nid for f in RESOURCES.fonts]:
            self.font_combo.setCurrentText(curr)
        elif self.font_combo.count() > 0:
            default_font = 'text' if 'text' in [f.nid for f in RESOURCES.fonts] else self.font_combo.itemText(0)
            self.font_combo.setCurrentText(default_font)
        self.font_combo.blockSignals(False)

    def _populate_palette_list(self, select_name: Optional[str] = None):
        self.palette_list.blockSignals(True)
        self.palette_list.clear()

        palettes = self._get_active_profile_palettes()
        query = self._search_box.text().strip().lower()
        target_name = select_name or self._current_palette_name or ('white' if 'white' in palettes else ('black' if 'black' in palettes else None))

        selected_item = None
        for name in sorted(palettes.keys()):
            if query and query not in name.lower():
                continue
            item = QListWidgetItem(name)
            self.palette_list.addItem(item)
            if name == target_name:
                selected_item = item

        if selected_item:
            self.palette_list.setCurrentItem(selected_item)
            self._current_palette_name = selected_item.text()
        elif self.palette_list.count() > 0:
            self.palette_list.setCurrentRow(0)
            self._current_palette_name = self.palette_list.currentItem().text()
        else:
            self._current_palette_name = None

        self.palette_list.blockSignals(False)
        self._rebuild_swatches()
        self._update_test_preview()

    def _on_search_palette(self, _):
        self._populate_palette_list(self._current_palette_name)

    def _on_palette_selected(self, name: str):
        if not name:
            return
        self._current_palette_name = name
        self._rebuild_swatches()
        self._update_test_preview()

    def _rebuild_swatches(self):
        # Limpa swatches anteriores
        while self._swatch_layout.count():
            item = self._swatch_layout.takeAt(0)
            if item.widget():
                item.widget().setParent(None)

        palettes = self._get_active_profile_palettes()
        if not self._current_palette_name or self._current_palette_name not in palettes:
            self._pal_title_label.setText("<b>Palette:</b> (none)")
            return

        colors = palettes[self._current_palette_name]
        profile_names = {
            'ui_3color': "UI (3 Colors)",
            'dialogue_2color': "Dialogue (2 Colors)",
            'custom': "Custom",
        }
        prof_title = profile_names.get(self._current_profile_key, self._current_profile_key)
        self._pal_title_label.setText(
            f"<b>Profile:</b> <span style='color:#ffaa00;'>{prof_title}</span> | "
            f"<b>Palette:</b> <span style='color:#55aaff;'>{self._current_palette_name}</span> "
            f"({len(colors)} slots)"
        )

        if self._current_profile_key == 'ui_3color':
            role_hints = [
                "0: Body / Fore (Light)",
                "1: Shadow (Dark)",
                "2: Midtone / Anti-alias"
            ]
        elif self._current_profile_key == 'dialogue_2color':
            role_hints = [
                "0: Ink Body (Dark)",
                "1: Highlight / Shadow (Light)"
            ]
        else:
            role_hints = [f"{i}: Slot {i}" for i in range(len(colors))]

        for idx, color in enumerate(colors):
            row_widget = QWidget()
            row_layout = QHBoxLayout()
            row_layout.setContentsMargins(2, 2, 2, 2)
            row_widget.setLayout(row_layout)

            r, g, b = color[0], color[1], color[2]
            a = color[3] if len(color) > 3 else 255

            btn = QPushButton()
            btn.setFixedSize(32, 32)
            btn.setStyleSheet(f"background-color: rgba({r},{g},{b},{a/255.0}); border: 2px solid #555;")
            btn.setToolTip(f"RGBA({r}, {g}, {b}, {a}) — Click to change color")
            btn.clicked.connect(lambda _, i=idx: self._pick_swatch_color(i))
            row_layout.addWidget(btn)

            hint = role_hints[idx] if idx < len(role_hints) else f"{idx}: Tone {idx}"
            lbl = QLabel(f"<b>{hint}</b><br><span style='color:#888;font-size:10px;'>RGB({r}, {g}, {b})</span>")
            row_layout.addWidget(lbl, 1)

            self._swatch_layout.addWidget(row_widget)

    def _pick_swatch_color(self, index: int):
        palettes = self._get_active_profile_palettes()
        if not self._current_palette_name or self._current_palette_name not in palettes:
            return
        colors = palettes[self._current_palette_name]
        if index >= len(colors):
            return

        cur = colors[index]
        r, g, b = cur[0], cur[1], cur[2]
        a = cur[3] if len(cur) > 3 else 255
        dialog = QColorDialog(QColor(r, g, b, a), self)
        dialog.setOption(QColorDialog.ShowAlphaChannel, True)
        if dialog.exec_():
            chosen = dialog.selectedColor()
            colors[index] = (chosen.red(), chosen.green(), chosen.blue(), chosen.alpha())
            self._save_palettes_to_project()
            self._rebuild_swatches()
            self._update_test_preview()

    def _add_swatch_color(self):
        palettes = self._get_active_profile_palettes()
        if not self._current_palette_name or self._current_palette_name not in palettes:
            return
        colors = palettes[self._current_palette_name]
        last_color = colors[-1] if colors else (128, 128, 128, 255)
        colors.append(last_color)
        self._save_palettes_to_project()
        self._rebuild_swatches()
        self._update_test_preview()

    def _del_swatch_color(self):
        palettes = self._get_active_profile_palettes()
        if not self._current_palette_name or self._current_palette_name not in palettes:
            return
        colors = palettes[self._current_palette_name]
        if len(colors) <= 1:
            QMessageBox.information(self, "Notice", "A palette must have at least one color slot.")
            return
        colors.pop()
        self._save_palettes_to_project()
        self._rebuild_swatches()
        self._update_test_preview()

    def _generate_twin_profile(self):
        """Gera versão de diálogo a partir de UI ou versão de UI a partir de diálogo."""
        if not self._current_palette_name:
            return
        profiles = getattr(RESOURCES.fonts, 'palette_profiles', {})
        cur_colors = self._get_active_profile_palettes().get(self._current_palette_name)
        if not cur_colors:
            return

        if self._current_profile_key == 'ui_3color':
            # Converte UI (3 cores: corpo claro, sombra escura, midtone) para Dialogue (2 cores: tinta escura, sombra clara)
            # Slot 0 de diálogo = Tinta escura derivada da sombra da UI ou saturação
            # Slot 1 de diálogo = Realce claro derivado do midtone ou corpo
            dark_ink = cur_colors[1] if len(cur_colors) > 1 else (40, 40, 40, 255)
            light_shadow = cur_colors[2] if len(cur_colors) > 2 else (184, 184, 184, 255)
            twin = [dark_ink, light_shadow]
            target_profile = 'dialogue_2color'
            msg_target = "Dialogue & Story (2 Colors)"
        else:
            # Converte Dialogue (2 cores: tinta escura, sombra clara) para UI (3 cores: corpo claro, sombra escura, midtone)
            light_body = cur_colors[1] if len(cur_colors) > 1 else (248, 248, 248, 255)
            dark_shadow = cur_colors[0] if len(cur_colors) > 0 else (40, 40, 40, 255)
            midtone = (
                int(light_body[0] * 0.6 + dark_shadow[0] * 0.4),
                int(light_body[1] * 0.6 + dark_shadow[1] * 0.4),
                int(light_body[2] * 0.6 + dark_shadow[2] * 0.4),
                255
            )
            twin = [light_body, dark_shadow, midtone]
            target_profile = 'ui_3color'
            msg_target = "UI & Menus (3 Colors)"

        if target_profile not in profiles:
            profiles[target_profile] = {}
        profiles[target_profile][self._current_palette_name] = twin
        self._save_palettes_to_project()

        QMessageBox.information(
            self, "Twin Profile Generated",
            f"Successfully generated '{self._current_palette_name}' in profile '{msg_target}'."
        )

    def _add_palette(self):
        name, ok = QInputDialog.getText(self, "Add Global Palette", "Palette name:")
        if not ok or not name.strip():
            return
        name = name.strip()
        palettes = self._get_active_profile_palettes()
        if name in palettes:
            QMessageBox.warning(self, "Duplicate", f"A palette named '{name}' already exists in this profile.")
            return

        ref_colors = palettes.get(self._current_palette_name)
        if not ref_colors:
            if self._current_profile_key == 'dialogue_2color':
                ref_colors = DEFAULT_DIALOGUE_PALETTES.get('black', [(40, 40, 40, 255), (184, 184, 184, 255)])
            else:
                ref_colors = DEFAULT_UI_PALETTES.get('blue', [(192, 248, 248, 255), (24, 24, 88, 255), (80, 112, 248, 255)])

        palettes[name] = [tuple(c) for c in ref_colors]
        self._save_palettes_to_project()
        self._populate_palette_list(select_name=name)

    def _delete_palette(self):
        if not self._current_palette_name:
            return
        confirm = QMessageBox.question(
            self, "Confirm Delete",
            f"Are you sure you want to delete palette '{self._current_palette_name}' from profile '{self._current_profile_key}'?",
            QMessageBox.Yes | QMessageBox.No
        )
        if confirm != QMessageBox.Yes:
            return
        palettes = self._get_active_profile_palettes()
        palettes.pop(self._current_palette_name, None)
        self._save_palettes_to_project()
        self._populate_palette_list()

    def _duplicate_palette(self):
        if not self._current_palette_name:
            return
        palettes = self._get_active_profile_palettes()
        src_colors = palettes.get(self._current_palette_name, [])
        new_name = f"{self._current_palette_name}_copy"
        counter = 1
        while new_name in palettes:
            new_name = f"{self._current_palette_name}_copy{counter}"
            counter += 1

        palettes[new_name] = [tuple(c) for c in src_colors]
        self._save_palettes_to_project()
        self._populate_palette_list(select_name=new_name)

    def _reset_to_factory(self):
        confirm = QMessageBox.question(
            self, "Reset to Factory",
            "This will reset all global palette profiles (UI, Dialogue) to canonical GBA / Lex Talionis defaults. Proceed?",
            QMessageBox.Yes | QMessageBox.No
        )
        if confirm != QMessageBox.Yes:
            return
        RESOURCES.fonts.palette_profiles = {
            'ui_3color': {k: list(v) for k, v in DEFAULT_UI_PALETTES.items()},
            'dialogue_2color': {k: list(v) for k, v in DEFAULT_DIALOGUE_PALETTES.items()},
            'custom': {},
        }
        RESOURCES.fonts.global_palettes = RESOURCES.fonts.palette_profiles['ui_3color']
        self._save_palettes_to_project()
        self._populate_palette_list()

    def _apply_current_to_selected_font(self):
        target_fnid = self.font_combo.currentText()
        font_obj = RESOURCES.fonts.get(target_fnid)
        if not font_obj or not self._current_palette_name:
            return
        palettes = self._get_active_profile_palettes()
        pal_colors = palettes.get(self._current_palette_name)
        if not pal_colors:
            return

        base_nid = font_obj.base_palette_nid
        base_palette = font_obj.palettes.get(base_nid) if base_nid else None
        target_count = len(base_palette) if base_palette else len(pal_colors)
        font_obj.palettes[self._current_palette_name] = adapt_palette_to_font(pal_colors, target_count)
        self._save_all_project_resources()
        QMessageBox.information(
            self, "Applied",
            f"Palette '{self._current_palette_name}' successfully applied to font '{target_fnid}'."
        )
        self._update_test_preview()

    def _apply_current_to_all_fonts(self):
        if not self._current_palette_name:
            return
        palettes = self._get_active_profile_palettes()
        pal_colors = palettes.get(self._current_palette_name)
        if not pal_colors:
            return

        count = 0
        for f in RESOURCES.fonts:
            base_nid = f.base_palette_nid
            base_palette = f.palettes.get(base_nid) if base_nid else None
            target_count = len(base_palette) if base_palette else len(pal_colors)
            f.palettes[self._current_palette_name] = adapt_palette_to_font(pal_colors, target_count)
            count += 1

        self._save_all_project_resources()
        QMessageBox.information(
            self, "Applied Everywhere",
            f"Palette '{self._current_palette_name}' was applied to all {count} fonts in the project."
        )
        self._update_test_preview()

    def _sync_all_palettes_to_all_fonts(self):
        profiles = getattr(RESOURCES.fonts, 'palette_profiles', {})
        if not profiles:
            return
        for f in RESOURCES.fonts:
            RESOURCES.fonts.inherit_global_palettes(f, overwrite=True)

        self._save_all_project_resources()
        QMessageBox.information(
            self, "Synchronization Complete",
            f"All palette profiles synchronized across all {len(RESOURCES.fonts)} project fonts!"
        )
        self._update_test_preview()

    def _save_palettes_to_project(self):
        if hasattr(RESOURCES.fonts, 'save_palettes'):
            RESOURCES.fonts.save_palettes()
        self.palettes_updated.emit()

    def _save_all_project_resources(self):
        self._save_palettes_to_project()
        if hasattr(RESOURCES.fonts, 'save_assignments'):
            RESOURCES.fonts.save_assignments()

    def _on_bg_changed(self, idx: int):
        if 0 <= idx < len(PRESET_BACKGROUNDS):
            self._preview_bg_color = PRESET_BACKGROUNDS[idx][1]
            self._update_test_preview()

    def _on_preset_text_chosen(self, idx: int):
        if idx > 0:
            combo = self.sender()
            text = combo.itemData(idx)
            if text:
                self.test_text_input.setText(text)

    def _adjust_zoom(self, step: int):
        zoom_levels = [0.5, 0.75, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 6.0]
        # Encontra o nível mais próximo
        closest_idx = 0
        min_diff = 999
        for i, lvl in enumerate(zoom_levels):
            diff = abs(lvl - self._preview_zoom)
            if diff < min_diff:
                min_diff = diff
                closest_idx = i

        new_idx = max(0, min(len(zoom_levels) - 1, closest_idx + step))
        self._set_zoom(zoom_levels[new_idx])

    def _set_zoom(self, zoom: float):
        self._preview_zoom = max(0.5, min(8.0, zoom))
        self._zoom_label.setText(f"{int(self._preview_zoom * 100)}%")
        self._update_test_preview()

    def _on_showcase_toggle(self, state):
        is_checked = (state == Qt.Checked)
        self._showcase_add_combo.setVisible(is_checked)
        self._showcase_clear_btn.setVisible(is_checked)
        self._showcase_chips_widget.setVisible(is_checked)
        if is_checked:
            self._update_showcase_chips()
        self._update_test_preview()

    def _on_showcase_add_chosen(self, idx: int):
        if idx > 0:
            chosen_font = self._showcase_add_combo.itemText(idx)
            if chosen_font and chosen_font not in self._showcase_selected_fonts:
                self._showcase_selected_fonts.append(chosen_font)
                self._update_showcase_chips()
                self._update_test_preview()
            self._showcase_add_combo.setCurrentIndex(0)

    def _on_showcase_clear(self):
        self._showcase_selected_fonts.clear()
        self._update_showcase_chips()
        self._update_test_preview()

    def _update_showcase_chips(self):
        # Limpa layout anterior de chips
        while self._showcase_chips_layout.count():
            item = self._showcase_chips_layout.takeAt(0)
            if item.widget():
                item.widget().setParent(None)

        self._showcase_chips_layout.addWidget(QLabel("<b>Comparing:</b>"))

        for fnid in list(self._showcase_selected_fonts):
            chip = QPushButton(f"{fnid} ✕")
            chip.setStyleSheet("padding: 2px 6px; font-size: 11px; border: 1px solid #777; border-radius: 3px;")
            chip.setToolTip(f"Click to remove '{fnid}' from showcase")
            chip.clicked.connect(lambda _, f=fnid: self._remove_showcase_font(f))
            self._showcase_chips_layout.addWidget(chip)

        self._showcase_chips_layout.addStretch()

        # Atualiza itens disponíveis no combo de adição
        self._showcase_add_combo.blockSignals(True)
        self._showcase_add_combo.clear()
        self._showcase_add_combo.addItem("+ Add Font to Showcase...")
        for f in RESOURCES.fonts:
            if f.nid not in self._showcase_selected_fonts:
                self._showcase_add_combo.addItem(f.nid)
        self._showcase_add_combo.blockSignals(False)

    def _remove_showcase_font(self, fnid: str):
        if fnid in self._showcase_selected_fonts:
            self._showcase_selected_fonts.remove(fnid)
            self._update_showcase_chips()
            self._update_test_preview()

    def _render_font_text(self, font_nid: str, text: str, palette_colors: List[Tuple[int, int, int, int]]) -> Optional[QPixmap]:
        font_obj = RESOURCES.fonts.get(font_nid)
        if not font_obj or not font_obj.image_path() or not os.path.exists(font_obj.image_path()):
            return None

        # Cria ou obtém BmpFont
        if font_nid not in self._bmp_cache:
            try:
                self._bmp_cache[font_nid] = BmpFont(font_obj, headless=True)
            except Exception:
                return None
        bmp = self._bmp_cache[font_nid]
        if not bmp or not bmp.index:
            return None

        base_nid = font_obj.base_palette_nid
        base_palette = font_obj.palettes.get(base_nid, [])
        if not base_palette:
            return None

        adapted = adapt_palette_to_font(palette_colors, len(base_palette))
        palette_map = {tuple(orig): tuple(new) for orig, new in zip(base_palette, adapted)}

        try:
            import pygame
            base_surf = engine.image_load(font_obj.image_path(), convert_alpha=False)
            recolored_sheet = image_mods.color_convert_alpha(base_surf, palette_map)

            # Renderiza o texto
            line_w = max(bmp.width(text), 1) + 12
            line_h = bmp.height + 6
            out_surf = pygame.Surface((line_w, line_h), pygame.SRCALPHA, 32)

            curr_x = 4
            for char in text:
                char_to_use = char.upper() if bmp.all_uppercase else (char.lower() if bmp.all_lowercase else char)
                glyph = bmp.index.get(char_to_use)
                if glyph:
                    rect = (glyph.x, glyph.y, glyph.char_width, bmp.index.char_height)
                    char_surf = engine.subsurface(recolored_sheet, rect)
                    out_surf.blit(char_surf, (curr_x, 3))
                    curr_x += glyph.char_width + bmp.space_offset
                else:
                    curr_x += bmp.index.char_width

            raw = engine.surf_to_raw(out_surf, 'RGBA')
            img = QImage(raw, line_w, line_h, QImage.Format_RGBA8888)
            pix = QPixmap.fromImage(img)
            
            # Escala conforme o nível de zoom ativo (com renderização nítida pixel art)
            scaled_w = max(1, int(line_w * self._preview_zoom))
            scaled_h = max(1, int(line_h * self._preview_zoom))
            return pix.scaled(scaled_w, scaled_h, Qt.KeepAspectRatio, Qt.FastTransformation)
        except Exception:
            return None

    def _update_test_preview(self):
        palettes = self._get_active_profile_palettes()
        if not self._current_palette_name or self._current_palette_name not in palettes:
            self.main_preview_label.setText("(No palette selected)")
            return

        palette_colors = palettes[self._current_palette_name]
        sample_text = self.test_text_input.text().strip() or "Sample Text 123"
        bg_hex = self._preview_bg_color.name()

        # Atualiza cor de fundo dos previews
        self._preview_container.setStyleSheet(f"background-color: {bg_hex}; border-radius: 4px; padding: 12px;")

        show_multi = self.multi_font_check.isChecked()

        if not show_multi:
            # Modo Único
            for r in self.showcase_rows:
                r.setVisible(False)
            self.main_preview_label.setVisible(True)

            font_nid = self.font_combo.currentText()
            pix = self._render_font_text(font_nid, sample_text, palette_colors)
            if pix:
                self.main_preview_label.setPixmap(pix)
            else:
                self.main_preview_label.setText(f"({font_nid} preview unavailable)")
        else:
            # Modo Showcase Multi-Font Customizável
            self.main_preview_label.setVisible(False)

            # Limpa widgets anteriores do showcase layout
            while self._preview_layout.count() > 1:
                item = self._preview_layout.takeAt(1)
                if item.widget():
                    item.widget().setParent(None)
            self.showcase_rows.clear()

            fonts_to_show = self._showcase_selected_fonts or ['text', 'convo', 'profont']
            for fnid in fonts_to_show:
                row_box = QWidget()
                row_layout = QVBoxLayout()
                row_layout.setContentsMargins(4, 4, 4, 8)
                row_layout.setAlignment(Qt.AlignCenter)
                row_box.setLayout(row_layout)

                name_lbl = QLabel(f"<b>{fnid}</b>")
                name_lbl.setStyleSheet("color: #aaa; font-size: 11px;")
                name_lbl.setAlignment(Qt.AlignCenter)
                row_layout.addWidget(name_lbl)

                img_lbl = QLabel()
                img_lbl.setAlignment(Qt.AlignCenter)
                pix = self._render_font_text(fnid, sample_text, palette_colors)
                if pix:
                    img_lbl.setPixmap(pix)
                else:
                    img_lbl.setText(f"({fnid} unavailable)")
                row_layout.addWidget(img_lbl)

                self._preview_layout.addWidget(row_box)
                self.showcase_rows.append(row_box)
