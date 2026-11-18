from PyQt5.QtWidgets import QWidget, QLineEdit, QMessageBox, QVBoxLayout, \
    QSpinBox, QCheckBox
from PyQt5.QtCore import Qt

from app.data.database.database import DB
from app.data.database.database_types import DatabaseType as DType
from app.data.resources.resources import RESOURCES
from app.editor.edit_history import HISTORY

from app.data.database.stats import StatPrefab
from app.utilities import str_utils
from app.extensions.custom_gui import PropertyBox, ComboBox, PropertyCheckBox
from app.editor.lib.components.validated_line_edit import NidLineEdit

class StatTypeProperties(QWidget):
    def __init__(self, parent, current=None):
        super().__init__(parent)
        self.window = parent
        self._data = self.window._data

        self.current: StatPrefab = current

        name_section = QVBoxLayout()

        self.nid_box = PropertyBox(_("Unique ID"), NidLineEdit, self)
        self.nid_box.edit.editingFinished.connect(self.nid_done_editing)
        name_section.addWidget(self.nid_box)

        self.name_box = PropertyBox(_("Display Name"), QLineEdit, self)
        self.name_box.edit.textChanged.connect(self.name_changed)
        name_section.addWidget(self.name_box)

        self.max_box = PropertyBox(_("Maximum"), QSpinBox, self)
        self.max_box.edit.setRange(0, 255)
        self.max_box.edit.setAlignment(Qt.AlignRight)
        self.max_box.edit.valueChanged.connect(self.maximum_changed)
        name_section.addWidget(self.max_box)

        self.desc_box = PropertyBox(_("Description"), QLineEdit, self)
        self.desc_box.edit.textChanged.connect(self.desc_changed)
        name_section.addWidget(self.desc_box)

        self.position_box = PropertyBox(_("Position"), ComboBox, self)
        self.position_box.edit.addItems(["hidden", "left", "right"])
        self.position_box.setToolTip("Column within Info Menu in engine")
        self.position_box.edit.currentTextChanged.connect(self.position_changed)
        name_section.addWidget(self.position_box)

        # Colored growths / custom stat color
        self.growth_colors_box = PropertyCheckBox(_("Colored Growths"), QCheckBox, self)
        self.growth_colors_box.edit.stateChanged.connect(self.growth_colors_changed)
        self.growth_colors_box.setToolTip(_("Enable custom font palette color for this stat in the Info Menu"))
        name_section.addWidget(self.growth_colors_box)

        self.stat_color_box = PropertyBox(_("Stat Color"), ComboBox, self)
        self.stat_color_box.edit.addItems(self.get_font_colors())
        self.stat_color_box.setToolTip(_("Font palette color from 'text' used when Colored Growths is enabled"))
        self.stat_color_box.edit.currentTextChanged.connect(self.stat_color_changed)
        name_section.addWidget(self.stat_color_box)
        
        self.hidden_stat_box = PropertyCheckBox(_("Hidden Stat"), QCheckBox, self)
        self.hidden_stat_box.edit.stateChanged.connect(self.hidden_stat_changed)
        self.hidden_stat_box.setToolTip(_("Whether this stat appears in the unit and class editors"))
        name_section.addWidget(self.hidden_stat_box)

        self.setLayout(name_section)
        name_section.setAlignment(Qt.AlignTop)

    def get_font_colors(self) -> list[str]:
        font_obj = RESOURCES.fonts.get('text')
        if font_obj and font_obj.palettes:
            return list(font_obj.palettes.keys())
        return ['new-white', 'white', 'yellow', 'blue', 'green', 'red', 'orange', 'purple', 'grey']

    def refresh_font_colors(self):
        current_palettes = self.get_font_colors()
        existing = [self.stat_color_box.edit.itemText(i) for i in range(self.stat_color_box.edit.count())]
        if current_palettes != existing:
            self.stat_color_box.edit.blockSignals(True)
            self.stat_color_box.edit.clear()
            self.stat_color_box.edit.addItems(current_palettes)
            self.stat_color_box.edit.blockSignals(False)

    def on_nid_changed(self, old_nid, new_nid):
        HISTORY.rewrite(DType.STATS, old_nid, new_nid)

    def nid_done_editing(self):
        new_nid = self.nid_box.edit.text()
        other_nids = [d.nid for d in self._data.values() if d is not self.current]
        if new_nid in other_nids:
            QMessageBox.warning(self.window, 'Warning', 'Stat Type ID %s already in use' % new_nid)
            new_nid = str_utils.get_next_name(new_nid, other_nids)
            self.nid_box.edit.setText(new_nid)
        if self.current.name == self.current.nid.replace('_', ' '):
            self.name_box.edit.setText(new_nid.replace('_', ' '))
        HISTORY.rename(self._data, self.current, new_nid, self.on_nid_changed)
        self.window.update_list()

    def name_changed(self, text):
        self.current.name = text
        self.window.update_list()

    def desc_changed(self, text):
        self.current.desc = text

    def position_changed(self, val):
        self.current.position = val

    def maximum_changed(self, val):
        self.current.maximum = val

    def growth_colors_changed(self, state):
        enabled = bool(state)
        self.current.growth_colors = enabled
        self.stat_color_box.setEnabled(enabled)

    def stat_color_changed(self, val):
        if self.current:
            self.current.stat_color = val
        
    def hidden_stat_changed(self, state):
        self.current.hidden_stat = bool(state)

    def set_current(self, current: StatPrefab):
        self.current = current
        self.refresh_font_colors()
        self.nid_box.edit.setText(current.nid)
        self.name_box.edit.setText(current.name)
        self.max_box.edit.setValue(current.maximum)
        self.growth_colors_box.edit.setChecked(bool(current.growth_colors))
        
        stat_color = getattr(current, 'stat_color', 'new-white') or 'new-white'
        if self.stat_color_box.edit.findText(stat_color) == -1:
            self.stat_color_box.edit.addItem(stat_color)
        self.stat_color_box.edit.setValue(stat_color)
        self.stat_color_box.setEnabled(bool(current.growth_colors))

        self.hidden_stat_box.edit.setChecked(bool(current.hidden_stat))
        self.desc_box.edit.setText(current.desc)
        self.position_box.edit.setValue(current.position)