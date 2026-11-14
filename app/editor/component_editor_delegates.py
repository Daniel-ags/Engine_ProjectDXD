from typing import Optional
from PyQt5.QtCore import Qt, QRect, QSize
from PyQt5.QtWidgets import (QDoubleSpinBox, QItemDelegate, QLineEdit,
                             QSpinBox, QWidget, QStyle)
from PyQt5.QtGui import QFont, QIcon, QPixmap
from app.data.database.database import DB
from app.data.resources.resources import RESOURCES
from app.editor.code_line_edit import CodeLineEdit
from app.editor.settings.main_settings_controller import MainSettingsController
from app.editor.settings.preference_definitions import Preference
from app.extensions.custom_gui import ComboBox
from app.utilities.data import Data


class BaseComponentDelegate(QItemDelegate):
    data: Data
    name: str
    is_float = False
    is_string = False

    settings = MainSettingsController()

    def get_icon(self, obj) -> Optional[QIcon]:
        return None

    def _format_label(self, obj) -> str:
        if hasattr(obj, 'name') and obj.name and obj.name != obj.nid:
            return f"{obj.nid} ({obj.name})"
        return obj.nid

    def createEditor(self, parent, option, index):
        if index.column() == 0:
            editor = ComboBox(parent)
            for obj in self.data:
                name = self._format_label(obj)
                icon = self.get_icon(obj)
                if icon:
                    editor.addItem(icon, name, obj.nid)
                else:
                    editor.addItem(name, obj.nid)
            return editor
        elif index.column() == 1:  # Integer value column
            if self.is_string:
                editor = CodeLineEdit(parent)
            elif self.is_float:
                editor = QDoubleSpinBox(parent)
                editor.setRange(0, 10)
            else:
                editor = QSpinBox(parent)
                editor.setRange(-1000, 1000)
            return editor
        else:
            return super().createEditor(parent, option, index)

    def setModelData(self, editor: QWidget, model, index) -> None:
        if index.column() == 0:  # combobox
            model.setData(index, editor.itemData(editor.currentIndex()), Qt.ItemDataRole)
        else:
            super().setModelData(editor, model, index)

    def sizeHint(self, option, index):
        size = super().sizeHint(option, index)
        if index.column() == 0:
            size.setHeight(max(20, size.height()))
        return size

    def paint(self, painter, option, index):
        if index.column() == 1 and self.is_string:
            painter.save()

            font = painter.font()
            if self.settings.get_preference(Preference.CODE_FONT_IN_BOXES):
                font = QFont(self.settings.get_preference(Preference.CODE_FONT))
            painter.setFont(font)

            if option.state & QStyle.State_Selected:
                painter.fillRect(option.rect, option.palette.highlight())
                painter.setPen(option.palette.highlightedText().color())

            painter.drawText(option.rect, Qt.AlignLeft | Qt.AlignVCenter, str(index.data()))
            painter.restore()
        elif index.column() == 0 and hasattr(self, 'data') and self.data:
            nid = str(index.data() or '')
            obj = self.data.get(nid)
            icon = self.get_icon(obj) if obj else None
            if icon:
                painter.save()
                if option.state & QStyle.State_Selected:
                    painter.fillRect(option.rect, option.palette.highlight())
                    painter.setPen(option.palette.highlightedText().color())

                icon_y = option.rect.top() + (option.rect.height() - 16) // 2
                icon_rect = QRect(option.rect.left() + 2, icon_y, 16, 16)
                icon.paint(painter, icon_rect)

                label = self._format_label(obj)
                text_rect = option.rect.adjusted(22, 0, -2, 0)
                painter.drawText(text_rect, Qt.AlignLeft | Qt.AlignVCenter, label)
                painter.restore()
                return
            super().paint(painter, option, index)
        else:
            super().paint(painter, option, index)


class UnitDelegate(BaseComponentDelegate):
    data = DB.units
    name = "Unit"


class ClassDelegate(BaseComponentDelegate):
    data = DB.classes
    name = "Class"


class AffinityDelegate(BaseComponentDelegate):
    data = DB.affinities
    name = "Affinity"


class TagDelegate(BaseComponentDelegate):
    data = DB.tags
    name = "Tag"


class ItemDelegate(BaseComponentDelegate):
    data = DB.items
    name = "Item"


class StatDelegate(BaseComponentDelegate):
    data = DB.stats
    name = "Stat"


class StatFloatDelegate(BaseComponentDelegate):
    data = DB.stats
    name = "Stat"
    is_float = True


class StatStringDelegate(BaseComponentDelegate):
    data = DB.stats
    name = "Stat"
    is_string = True


class WeaponTypeDelegate(BaseComponentDelegate):
    data = DB.weapons
    name = "Weapon Type"


class SkillDelegate(BaseComponentDelegate):
    data = DB.skills
    name = "Skill"

    def get_icon(self, obj) -> Optional[QIcon]:
        if not obj:
            return None
        try:
            from app.editor.skill_editor import skill_model
            pixmap = skill_model.get_pixmap(obj)
            if pixmap:
                return QIcon(pixmap)
        except Exception:
            pass

        icon_nid = getattr(obj, 'icon_nid', None)
        icon_index = getattr(obj, 'icon_index', None)
        if icon_nid and icon_index and icon_nid in RESOURCES.icons16:
            sheet = RESOURCES.icons16.get(icon_nid)
            if sheet and getattr(sheet, 'pixmap', None):
                sub = sheet.pixmap.copy(icon_index[0] * 16, icon_index[1] * 16, 16, 16)
                return QIcon(sub)
        return None


class TerrainDelegate(BaseComponentDelegate):
    data = DB.terrain
    name = "Terrain"


class LoreDelegate(BaseComponentDelegate):
    data = DB.lore
    name = "Lore"