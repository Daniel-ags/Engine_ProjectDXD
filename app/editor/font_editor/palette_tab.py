import os
from typing import Dict, List, Optional, Tuple

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QGroupBox,
    QLabel, QPushButton, QListWidget, QListWidgetItem, QLineEdit,
    QColorDialog, QMessageBox, QInputDialog, QScrollArea, QMenu, QSpinBox,
    QFrame
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QColor, QImage, QPixmap

from app.data.resources.resources import RESOURCES
from app.data.resources.fonts import (
    Color4, DEFAULT_UI_PALETTES, DEFAULT_DIALOGUE_PALETTES,
    adapt_palette_to_font
)
from app.engine.bmpfont import BmpFont
from app.engine import engine, image_mods
from app.extensions.custom_gui import ComboBox
from app.extensions.color_icon import AlphaColorIcon


PALETTE_PROFILES_META = [
    ('ui_3color', "UI & Menus (3 Colors)", "Body, Shadow, Midtone — Light text for dark menus"),
    ('dialogue_2color', "Dialogue & Story (2 Colors)", "Ink Body, Shadow — Dark text for light speech bubbles"),
    ('custom', "Custom Ramps", "Multi-color gradients and special fonts"),
]


def color_to_hex(r: int, g: int, b: int, a: int = 255) -> str:
    if a < 255:
        return f"#{r:02X}{g:02X}{b:02X}{a:02X}"
    return f"#{r:02X}{g:02X}{b:02X}"


def hex_to_color(hex_str: str) -> Optional[Tuple[int, int, int, int]]:
    cleaned = hex_str.strip().lstrip('#')
    if len(cleaned) == 6:
        try:
            r = int(cleaned[0:2], 16)
            g = int(cleaned[2:4], 16)
            b = int(cleaned[4:6], 16)
            return (r, g, b, 255)
        except ValueError:
            return None
    elif len(cleaned) == 8:
        try:
            r = int(cleaned[0:2], 16)
            g = int(cleaned[2:4], 16)
            b = int(cleaned[4:6], 16)
            a = int(cleaned[6:8], 16)
            return (r, g, b, a)
        except ValueError:
            return None
    return None


class PaletteListWidget(QListWidget):
    """QListWidget with keyboard shortcuts for rename (F2) and delete (Delete)."""

    def __init__(self, parent_widget):
        super().__init__(parent_widget)
        self.parent_widget = parent_widget

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Delete:
            self.parent_widget._delete_palette()
            event.accept()
        elif event.key() == Qt.Key_F2:
            self.parent_widget._rename_palette()
            event.accept()
        else:
            super().keyPressEvent(event)


class PaletteEditorWidget(QWidget):
    """Global Font Palette Management and Editor Tab."""
    palettes_updated = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_profile_key: str = 'ui_3color'
        self._current_palette_name: Optional[str] = None
        self._updating_inputs: bool = False
        self._bmp_cache: Dict[str, Optional[BmpFont]] = {}

        main_layout = QHBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(main_layout)

        # -- Main Splitter --
        self.splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(self.splitter)

        # Column 1: Palette List & Profile Selector (left_frame)
        self.left_frame = QWidget()
        left_layout = QVBoxLayout()
        left_layout.setContentsMargins(0, 0, 0, 0)
        self.left_frame.setLayout(left_layout)

        profile_row = QHBoxLayout()
        profile_row.addWidget(QLabel("Profile:"))
        self.profile_combo = ComboBox()
        for pkey, plabel, pdesc in PALETTE_PROFILES_META:
            self.profile_combo.addItem(plabel, pkey)
        self.profile_combo.currentIndexChanged.connect(self._on_profile_changed)
        profile_row.addWidget(self.profile_combo, 1)
        left_layout.addLayout(profile_row)

        self._search_box = QLineEdit()
        self._search_box.setPlaceholderText("Filter by keyword...")
        self._search_box.textChanged.connect(self._on_search_palette)
        left_layout.addWidget(self._search_box)

        self.palette_list = PaletteListWidget(self)
        self.palette_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.palette_list.customContextMenuRequested.connect(self._on_palette_context_menu)
        self.palette_list.currentTextChanged.connect(self._on_palette_selected)
        left_layout.addWidget(self.palette_list, 1)

        # Bottom actions on left panel (Vanilla pattern)
        self.create_btn = QPushButton("Create Palette...")
        self.create_btn.clicked.connect(self._add_palette)
        left_layout.addWidget(self.create_btn)

        btn_row = QHBoxLayout()
        self.sync_btn = QPushButton("Sync to Fonts")
        self.sync_btn.setToolTip("Synchronize all palette profiles across all project fonts")
        self.sync_btn.clicked.connect(self._sync_all_palettes_to_all_fonts)
        btn_row.addWidget(self.sync_btn)

        self.reset_btn = QPushButton("Reset Defaults")
        self.reset_btn.setToolTip("Reset all global palette profiles to default")
        self.reset_btn.clicked.connect(self._reset_to_factory)
        btn_row.addWidget(self.reset_btn)
        left_layout.addLayout(btn_row)

        self.splitter.addWidget(self.left_frame)

        # Column 2: Selected Palette Color Editor (right_frame)
        self.right_frame = QWidget()
        right_layout = QVBoxLayout()
        self.right_frame.setLayout(right_layout)

        # Palette Header
        header_row = QHBoxLayout()
        header_row.addWidget(QLabel("Palette:"))
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Palette Name")
        self.name_edit.editingFinished.connect(self._on_palette_name_edited)
        header_row.addWidget(self.name_edit, 1)

        self._profile_badge = QLabel("")
        header_row.addWidget(self._profile_badge)

        apply_all_btn = QPushButton("Apply to All Fonts")
        apply_all_btn.setToolTip("Apply this palette to all project fonts")
        apply_all_btn.clicked.connect(self._apply_current_to_all_fonts)
        header_row.addWidget(apply_all_btn)

        right_layout.addLayout(header_row)

        # Palette Preview Section
        preview_group = QGroupBox("Preview")
        preview_layout = QVBoxLayout()
        preview_group.setLayout(preview_layout)

        preview_ctrl_row = QHBoxLayout()
        preview_ctrl_row.addWidget(QLabel("Font:"))
        self.preview_font_combo = ComboBox()
        self.preview_font_combo.currentIndexChanged.connect(self._on_preview_font_changed)
        preview_ctrl_row.addWidget(self.preview_font_combo, 1)

        self.preview_text_edit = QLineEdit("What? How?")
        self.preview_text_edit.setPlaceholderText("Sample preview text...")
        self.preview_text_edit.textChanged.connect(self._update_palette_preview)
        preview_ctrl_row.addWidget(self.preview_text_edit, 2)
        preview_layout.addLayout(preview_ctrl_row)

        self.preview_display_lbl = QLabel()
        self.preview_display_lbl.setMinimumHeight(44)
        self.preview_display_lbl.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.preview_display_lbl.setStyleSheet("background-color: #141c2b; border: 1px solid #283854; border-radius: 6px; padding: 4px 10px;")
        preview_layout.addWidget(self.preview_display_lbl)

        right_layout.addWidget(preview_group)

        # Swatch Slot Grid
        swatch_scroll = QScrollArea()
        swatch_scroll.setWidgetResizable(True)
        self._swatch_container = QWidget()
        self._swatch_layout = QVBoxLayout()
        self._swatch_layout.setAlignment(Qt.AlignTop)
        self._swatch_container.setLayout(self._swatch_layout)
        swatch_scroll.setWidget(self._swatch_container)
        right_layout.addWidget(swatch_scroll, 1)

        # Swatch Actions Bar
        bottom_row = QHBoxLayout()
        add_color_btn = QPushButton("Add Slot")
        add_color_btn.clicked.connect(self._add_swatch_color)
        del_color_btn = QPushButton("Remove Slot")
        del_color_btn.clicked.connect(self._del_swatch_color)
        self.twin_btn = QPushButton("Convert to Dialogue")
        self.twin_btn.clicked.connect(self._generate_twin_profile)

        bottom_row.addWidget(add_color_btn)
        bottom_row.addWidget(del_color_btn)
        bottom_row.addWidget(self.twin_btn)
        bottom_row.addStretch()
        right_layout.addLayout(bottom_row)

        self.splitter.addWidget(self.right_frame)
        self.splitter.setSizes([220, 520])

        self.refresh_all()

    @classmethod
    def create(cls, parent=None, db=None, res=None):
        return cls(parent)

    def windowTitle(self) -> str:
        return "Palettes"

    def reset(self):
        self.refresh_all()

    def refresh_all(self):
        self._update_compatible_fonts()
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
        if hasattr(self, 'twin_btn'):
            if self._current_profile_key == 'ui_3color':
                self.twin_btn.setText("Convert to Dialogue")
            elif self._current_profile_key == 'dialogue_2color':
                self.twin_btn.setText("Convert to UI")
            else:
                self.twin_btn.setText("Generate Twin")
        self._update_compatible_fonts()
        self._populate_palette_list()

    def _on_preview_font_changed(self, idx: int):
        self._update_palette_preview()

    def _update_compatible_fonts(self):
        if not hasattr(self, 'preview_font_combo'):
            return
        self.preview_font_combo.blockSignals(True)
        cur_text = self.preview_font_combo.currentText()
        self.preview_font_combo.clear()

        # Discover fonts compatible with current profile
        compatible_fonts = []
        all_fonts = [f.nid for f in RESOURCES.fonts]
        for f in RESOURCES.fonts:
            prof = RESOURCES.fonts.get_profile_for_font(f)
            if prof == self._current_profile_key:
                compatible_fonts.append(f.nid)

        font_choices = compatible_fonts if compatible_fonts else all_fonts
        for fn in font_choices:
            self.preview_font_combo.addItem(fn)

        # Select a preferred default font if available
        if cur_text in font_choices:
            self.preview_font_combo.setCurrentText(cur_text)
        else:
            if self._current_profile_key == 'ui_3color':
                for pref in ('text', 'text_white', 'small', 'narrow-blue'):
                    if pref in font_choices:
                        self.preview_font_combo.setCurrentText(pref)
                        break
            elif self._current_profile_key == 'dialogue_2color':
                for pref in ('convo', 'bconvo', 'hint'):
                    if pref in font_choices:
                        self.preview_font_combo.setCurrentText(pref)
                        break

        self.preview_font_combo.blockSignals(False)
        self._update_palette_preview()

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

    def _update_palette_preview(self):
        if not hasattr(self, 'preview_display_lbl') or not hasattr(self, 'preview_font_combo'):
            return

        font_nid = self.preview_font_combo.currentText()
        palettes = self._get_active_profile_palettes()
        if not self._current_palette_name or self._current_palette_name not in palettes:
            self.preview_display_lbl.clear()
            self.preview_display_lbl.setText("  (No palette selected)")
            return

        current_colors = palettes[self._current_palette_name]
        sample_text = self.preview_text_edit.text() if hasattr(self, 'preview_text_edit') else "Preview 123"
        if not sample_text:
            sample_text = "Preview 123"

        font_prefab = RESOURCES.fonts.get(font_nid)
        bmp = self._get_bmp(font_nid) if font_nid else None

        if not bmp or not font_prefab:
            self.preview_display_lbl.clear()
            self.preview_display_lbl.setText(f"  ({font_nid or 'No font'} preview unavailable)")
            return

        try:
            import pygame
            temp_key = "__temp_preview_palette__"

            # Base colors and surface from the font sheet
            base_nid = font_prefab.base_palette_nid or bmp.default_color
            base_palette = font_prefab.palettes.get(base_nid) if base_nid else None
            base_surf = bmp.surfaces.get(base_nid, bmp.surfaces.get(bmp.default_color))

            target_count = len(base_palette) if base_palette else len(current_colors)
            adapted_colors = adapt_palette_to_font(current_colors, target_count)

            if base_surf and base_palette:
                palette_map = {orig: new for orig, new in zip(map(tuple, base_palette), map(tuple, adapted_colors))}
                custom_surf = image_mods.color_convert_alpha(base_surf.copy(), palette_map)
                bmp.surfaces[temp_key] = custom_surf
                # Invalidate cached glyphs for the temp palette
                bmp._chars = {k: v for k, v in bmp._chars.items() if k[1] != temp_key}
                bmp._stacked_chars = {k: v for k, v in bmp._stacked_chars.items() if k[1] != temp_key}
            else:
                font_prefab.palettes[temp_key] = [tuple(c) for c in adapted_colors]

            w = max(bmp.width(sample_text), 1) + 12
            h = bmp.height + 6
            surf = pygame.Surface((w, h), pygame.SRCALPHA, 32)
            bmp.blit(sample_text, surf, (2, 2), color=temp_key)

            # Cleanup temp allocations
            bmp.surfaces.pop(temp_key, None)
            font_prefab.palettes.pop(temp_key, None)

            raw = engine.surf_to_raw(surf, 'RGBA')
            img = QImage(raw, w, h, QImage.Format_RGBA8888)
            pix = QPixmap.fromImage(img)
            scaled = pix.scaled(w * 2, h * 2, Qt.KeepAspectRatio, Qt.FastTransformation)
            self.preview_display_lbl.setPixmap(scaled)
        except Exception:
            self.preview_display_lbl.clear()
            self.preview_display_lbl.setText("  (Error rendering preview)")

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

    def _on_search_palette(self, _):
        self._populate_palette_list(self._current_palette_name)

    def _on_palette_selected(self, name: str):
        if not name:
            return
        self._current_palette_name = name
        self._rebuild_swatches()

    def _on_palette_context_menu(self, pos):
        menu = QMenu(self)
        add_act = menu.addAction("New Palette...")
        add_act.triggered.connect(self._add_palette)

        selected_item = self.palette_list.itemAt(pos)
        if selected_item:
            dup_act = menu.addAction("Duplicate")
            dup_act.triggered.connect(self._duplicate_palette)

            rename_act = menu.addAction("Rename...")
            rename_act.triggered.connect(self._rename_palette)

            menu.addSeparator()
            del_act = menu.addAction("Delete")
            del_act.triggered.connect(self._delete_palette)

        menu.exec_(self.palette_list.mapToGlobal(pos))

    def _on_palette_name_edited(self):
        new_name = self.name_edit.text().strip()
        if not self._current_palette_name or not new_name or new_name == self._current_palette_name:
            if self._current_palette_name:
                self.name_edit.setText(self._current_palette_name)
            return
        palettes = self._get_active_profile_palettes()
        if new_name in palettes:
            QMessageBox.warning(self, "Duplicate Name", f"A palette named '{new_name}' already exists in this profile.")
            self.name_edit.setText(self._current_palette_name)
            return

        palettes[new_name] = palettes.pop(self._current_palette_name)
        self._current_palette_name = new_name
        self._save_palettes_to_project()
        self._populate_palette_list(select_name=new_name)

    def _rebuild_swatches(self):
        # Clear previous widgets
        while self._swatch_layout.count():
            item = self._swatch_layout.takeAt(0)
            if item.widget():
                item.widget().setParent(None)
            elif item.layout():
                while item.layout().count():
                    sub_item = item.layout().takeAt(0)
                    if sub_item.widget():
                        sub_item.widget().setParent(None)

        palettes = self._get_active_profile_palettes()
        if not self._current_palette_name or self._current_palette_name not in palettes:
            self.name_edit.blockSignals(True)
            self.name_edit.setText("")
            self.name_edit.setEnabled(False)
            self.name_edit.blockSignals(False)
            self._profile_badge.setText("(No palette selected)")
            return

        self.name_edit.setEnabled(True)
        self.name_edit.blockSignals(True)
        self.name_edit.setText(self._current_palette_name)
        self.name_edit.blockSignals(False)

        profile_names = {
            'ui_3color': "UI (3 Colors)",
            'dialogue_2color': "Dialogue (2 Colors)",
            'custom': "Custom",
        }
        prof_title = profile_names.get(self._current_profile_key, self._current_profile_key)
        colors = palettes[self._current_palette_name]
        self._profile_badge.setText(f"({prof_title})")

        if self._current_profile_key == 'ui_3color':
            role_hints = [
                "Body (Light)",
                "Shadow (Dark)",
                "Midtone"
            ]
        elif self._current_profile_key == 'dialogue_2color':
            role_hints = [
                "Ink (Dark)",
                "Highlight (Light)"
            ]
        else:
            role_hints = [f"Slot {i}" for i in range(len(colors))]

        self._swatch_layout.setSpacing(6)

        for idx, color in enumerate(colors):
            card = QFrame()
            card.setFrameShape(QFrame.StyledPanel)
            card.setStyleSheet(
                "QFrame { background-color: #2b2b30; border: 1px solid #3c3c44; border-radius: 6px; padding: 4px; }"
                "QLabel { border: none; background: transparent; }"
            )
            row_layout = QHBoxLayout(card)
            row_layout.setContentsMargins(8, 4, 8, 4)
            row_layout.setSpacing(10)

            r, g, b = color[0], color[1], color[2]
            a = color[3] if len(color) > 3 else 255

            # Slot badge
            slot_lbl = QLabel(f"#{idx}")
            slot_lbl.setFixedWidth(24)
            slot_lbl.setStyleSheet("font-weight: bold; color: #a0a0b0; font-size: 11px;")

            # Role badge
            hint = role_hints[idx] if idx < len(role_hints) else f"Slot {idx}"
            role_lbl = QLabel(hint)
            role_lbl.setFixedWidth(115)
            role_lbl.setStyleSheet("font-weight: 500; color: #e0e0e0;")

            # Color Picker Swatch (32x32)
            btn = AlphaColorIcon(QColor(r, g, b, a), self)
            btn.set_size(30)
            btn.setToolTip("Click to choose color from palette picker")

            # Hex field
            hex_layout = QHBoxLayout()
            hex_layout.setSpacing(2)
            hex_prefix = QLabel("#")
            hex_prefix.setStyleSheet("color: #888; font-weight: bold;")
            hex_edit = QLineEdit()
            hex_edit.setFixedWidth(75)
            clean_hex = color_to_hex(r, g, b, a).lstrip('#')
            hex_edit.setText(clean_hex)
            hex_edit.setPlaceholderText("RRGGBB")
            hex_edit.setToolTip("Hex code (RRGGBB or RRGGBBAA)")
            hex_edit.setStyleSheet("font-family: monospace; font-size: 11px;")
            hex_layout.addWidget(hex_prefix)
            hex_layout.addWidget(hex_edit)

            # RGBA channels with compact identifier badges
            channels_layout = QHBoxLayout()
            channels_layout.setSpacing(4)

            def create_channel_box(name: str, val: int, bg_color: str, tooltip: str):
                box = QHBoxLayout()
                box.setSpacing(2)
                badge = QLabel(name)
                badge.setFixedSize(16, 20)
                badge.setAlignment(Qt.AlignCenter)
                badge.setStyleSheet(f"background-color: {bg_color}; color: #ffffff; border-radius: 3px; font-weight: bold; font-size: 10px;")
                spin = QSpinBox()
                spin.setRange(0, 255)
                spin.setValue(val)
                spin.setFixedWidth(48)
                spin.setToolTip(tooltip)
                box.addWidget(badge)
                box.addWidget(spin)
                return box, spin

            r_box, r_spin = create_channel_box("R", r, "#b71c1c", "Red channel (0-255)")
            g_box, g_spin = create_channel_box("G", g, "#1b5e20", "Green channel (0-255)")
            b_box, b_spin = create_channel_box("B", b, "#0d47a1", "Blue channel (0-255)")
            a_box, a_spin = create_channel_box("A", a, "#4a148c", "Alpha / Opacity channel (0-255)")

            channels_layout.addLayout(r_box)
            channels_layout.addLayout(g_box)
            channels_layout.addLayout(b_box)
            channels_layout.addLayout(a_box)

            def make_color_handlers(i=idx, b_widget=btn, h_widget=hex_edit, rs=r_spin, gs=g_spin, bs=b_spin, as_s=a_spin):
                def on_color_icon_changed(nc: QColor):
                    pal = self._get_active_profile_palettes()
                    if not self._current_palette_name or i >= len(pal.get(self._current_palette_name, [])):
                        return
                    new_tuple = (nc.red(), nc.green(), nc.blue(), nc.alpha())
                    pal[self._current_palette_name][i] = new_tuple
                    rs.blockSignals(True)
                    gs.blockSignals(True)
                    bs.blockSignals(True)
                    as_s.blockSignals(True)
                    h_widget.blockSignals(True)
                    rs.setValue(nc.red())
                    gs.setValue(nc.green())
                    bs.setValue(nc.blue())
                    as_s.setValue(nc.alpha())
                    h_widget.setText(color_to_hex(*new_tuple).lstrip('#'))
                    rs.blockSignals(False)
                    gs.blockSignals(False)
                    bs.blockSignals(False)
                    as_s.blockSignals(False)
                    h_widget.blockSignals(False)
                    self._save_palettes_to_project()
                    self._update_palette_preview()

                def on_hex_changed(text):
                    clean_text = text.strip().lstrip('#')
                    parsed = hex_to_color(clean_text)
                    if not parsed:
                        return
                    pal = self._get_active_profile_palettes()
                    if not self._current_palette_name or i >= len(pal.get(self._current_palette_name, [])):
                        return
                    pal[self._current_palette_name][i] = parsed
                    b_widget.blockSignals(True)
                    b_widget.change_color(QColor(*parsed))
                    b_widget.blockSignals(False)
                    rs.blockSignals(True)
                    gs.blockSignals(True)
                    bs.blockSignals(True)
                    as_s.blockSignals(True)
                    rs.setValue(parsed[0])
                    gs.setValue(parsed[1])
                    bs.setValue(parsed[2])
                    as_s.setValue(parsed[3])
                    rs.blockSignals(False)
                    gs.blockSignals(False)
                    bs.blockSignals(False)
                    as_s.blockSignals(False)
                    self._save_palettes_to_project()
                    self._update_palette_preview()

                def on_spin_changed():
                    pal = self._get_active_profile_palettes()
                    if not self._current_palette_name or i >= len(pal.get(self._current_palette_name, [])):
                        return
                    new_tuple = (rs.value(), gs.value(), bs.value(), as_s.value())
                    pal[self._current_palette_name][i] = new_tuple
                    b_widget.blockSignals(True)
                    b_widget.change_color(QColor(*new_tuple))
                    b_widget.blockSignals(False)
                    h_widget.blockSignals(True)
                    h_widget.setText(color_to_hex(*new_tuple).lstrip('#'))
                    h_widget.blockSignals(False)
                    self._save_palettes_to_project()
                    self._update_palette_preview()

                b_widget.colorChanged.connect(on_color_icon_changed)
                h_widget.textEdited.connect(on_hex_changed)
                rs.valueChanged.connect(on_spin_changed)
                gs.valueChanged.connect(on_spin_changed)
                bs.valueChanged.connect(on_spin_changed)
                as_s.valueChanged.connect(on_spin_changed)

            make_color_handlers()

            row_layout.addWidget(slot_lbl)
            row_layout.addWidget(role_lbl)
            row_layout.addWidget(btn)
            row_layout.addLayout(hex_layout)
            row_layout.addLayout(channels_layout)
            row_layout.addStretch()

            self._swatch_layout.addWidget(card)

        self._update_palette_preview()

    def _add_palette(self):
        name, ok = QInputDialog.getText(self, "Add Palette", "Palette name:")
        if not ok or not name.strip():
            return
        name = name.strip()
        palettes = self._get_active_profile_palettes()
        if name in palettes:
            QMessageBox.warning(self, "Duplicate Name", f"A palette named '{name}' already exists in this profile.")
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

    def _rename_palette(self):
        if not self._current_palette_name:
            return
        old_name = self._current_palette_name
        new_name, ok = QInputDialog.getText(
            self, "Rename Palette", "New palette name:", QLineEdit.Normal, old_name)
        if not ok or not new_name.strip() or new_name.strip() == old_name:
            return
        new_name = new_name.strip()
        palettes = self._get_active_profile_palettes()
        if new_name in palettes:
            QMessageBox.warning(self, "Duplicate Name", f"A palette named '{new_name}' already exists in this profile.")
            return
        palettes[new_name] = palettes.pop(old_name)
        self._current_palette_name = new_name
        self._save_palettes_to_project()
        self._populate_palette_list(select_name=new_name)

    def _add_swatch_color(self):
        palettes = self._get_active_profile_palettes()
        if not self._current_palette_name or self._current_palette_name not in palettes:
            return
        colors = palettes[self._current_palette_name]
        last_color = colors[-1] if colors else (128, 128, 128, 255)
        colors.append(last_color)
        self._save_palettes_to_project()
        self._rebuild_swatches()

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

    def _generate_twin_profile(self):
        """Generates a dialogue counterpart from UI palette or a UI counterpart from dialogue palette."""
        if not self._current_palette_name:
            return
        cur_colors = self._get_active_profile_palettes().get(self._current_palette_name)
        if not cur_colors:
            return

        if self._current_profile_key == 'ui_3color':
            dark_ink = cur_colors[1] if len(cur_colors) > 1 else (40, 40, 40, 255)
            light_shadow = cur_colors[2] if len(cur_colors) > 2 else (184, 184, 184, 255)
            twin = [dark_ink, light_shadow]
            target_profile = 'dialogue_2color'
            msg_target = "Dialogue & Story (2 Colors)"
        else:
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

        target_dict = getattr(RESOURCES.fonts, 'palette_profiles', {}).get(target_profile)
        if target_dict is None:
            return
        target_dict[self._current_palette_name] = twin
        self._save_palettes_to_project()

        QMessageBox.information(
            self, "Twin Profile Created",
            f"Successfully generated twin palette for '{self._current_palette_name}' in profile '{msg_target}'."
        )

    def _reset_to_factory(self):
        confirm = QMessageBox.question(
            self, "Reset Defaults",
            "This will reset all global palette profiles (UI, Dialogue) to defaults. Proceed?",
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

    def _save_palettes_to_project(self):
        if hasattr(RESOURCES.fonts, 'save_palettes'):
            RESOURCES.fonts.save_palettes()
        self.palettes_updated.emit()

    def _save_all_project_resources(self):
        self._save_palettes_to_project()
        if hasattr(RESOURCES.fonts, 'save_assignments'):
            RESOURCES.fonts.save_assignments()


# Alias for standard vanilla naming convention
FontPaletteDatabase = PaletteEditorWidget
