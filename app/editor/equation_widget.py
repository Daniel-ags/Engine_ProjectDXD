from PyQt5.QtWidgets import QStyle, QStyledItemDelegate, QPlainTextEdit
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont

from app.editor.settings.preference_definitions import Preference
from app.utilities import str_utils
from app.data.database.database import DB

from app.extensions.list_dialogs import MultiAttrListDialog
from app.extensions.list_models import MultiAttrListModel

from app.data.database import equations
from app.data.database.database_types import DatabaseType as DType
from app.editor import reference_dialogs
from app.editor.edit_history import HISTORY
from app.editor.custom_widgets import ObjBox
from app.utilities.data import Data

import logging

from app.editor.settings import MainSettingsController
from app.editor.code_line_edit import CodeLineEdit

class EquationMultiModel(MultiAttrListModel):
    descs = {
        "AVOID": "Chance to avoid an enemy's attack",
        "CONSTITUTION": "Offsets weight speed reduction from items",
        "CRIT_ADD": "Flat damage bonus on crits",
        "CRIT_AVOID": "Reduces enemy's crit chance",
        "CRIT_HIT": "Crit chance",
        "CRIT_MULT": "Multiplicative damage bonus on crits, after def/res",
        "DAMAGE": "Base damage with physical weapons",
        "DEFENSE": "Base defense",
        "HEAL": "Base heal formula",
        "HIT": "Base hit rate",
        "HITPOINTS": "Total HP",
        "MAGIC_DAMAGE": "Base damage with magical weapons",
        "MAGIC_DEFENSE": "Base magical defense",
        "MOVEMENT": "Total movement",
        "RATING": "Overall unit rating",
        "RESCUE_AID": "Maximum weight that can be rescued",
        "RESCUE_WEIGHT": "Rescue weight",
        "SPEED_TO_DOUBLE": "Doubling threshold",
        "STEAL_ATK": "Steal ability",
        "STEAL_DEF": "Steal resistance",
        "THRACIA_CRIT": "Multiplicative damage bonus on crits, before def/res",
    }

    settings = MainSettingsController()

    def data(self, index, role):
        if not index.isValid():
            return None
        if role == Qt.EditRole:
            data = self._data[index.row()]
            attr = self._headers[index.column()]
            return getattr(data, attr)
        # no easy way of showing syntax highlighting via a role...
        if index.column() == 1 and role == Qt.FontRole:
            if self.settings.get_preference(Preference.CODE_FONT_IN_BOXES):
                return QFont(self.settings.get_preference(Preference.CODE_FONT))
            else:
                return QFont()
        if index.column() == 1 and role == Qt.DecorationRole:
            equation = self._data[index.row()]
            good = self.test_equation(equation)
            if good:
                icon = self.window.style().standardIcon(QStyle.SP_DialogApplyButton)
            else:
                icon = self.window.style().standardIcon(QStyle.SP_DialogCancelButton)
            return icon
        elif role == Qt.DisplayRole or role == Qt.EditRole:
            data = self._data[index.row()]
            attr = self._headers[index.column()]
            return getattr(data, attr)
        elif role == Qt.ToolTipRole:
            data = self._data[index.row()]
            if data.nid in self.descs:
                return self.descs[data.nid]
        return None

    def test_equation(self, equation) -> bool:
        try:
            from app.engine import equations as parse
            from app.engine.objects import unit
            test_unit = unit.UnitObject.from_prefab(DB.units[0])
            test_unit.stats = {k: v for (k, v) in test_unit.bases.items()}
            test_unit.stat_bonus = lambda x: 0
            parser = parse.Parser()
            result = parser.get(equation.nid, test_unit)
            result = parser.get_expression(equation.expression, test_unit)
            return True
        except Exception as e:
            logging.exception(e)
            logging.error("TestEquation Error: %s" % e)
            return False

    def delete(self, idx):
        element = self._data[idx]
        others = Data([eq for eq in DB.equations if eq is not element])
        with HISTORY.change_set('Delete %s' % element.nid):
            if reference_dialogs.check_delete(DType.EQUATIONS, element.nid, 'Equation', self.window,
                                              lambda: ObjBox("Equation", reference_dialogs.NidListModel, lambda: others, self.window)):
                super().delete(idx)

    def create_new(self):
        nids = [d.nid for d in self._data]
        nid = str_utils.get_next_name("EQUATION", nids)
        new_equation = equations.Equation(nid)
        DB.equations.append(new_equation)
        return new_equation

    def on_attr_changed(self, data, attr, old_value, new_value):
        if attr == 'nid':
            self._data.update_nid(data, new_value)
            HISTORY.rewrite(DType.EQUATIONS, old_value, new_value)

class EquationDelegate(QStyledItemDelegate):
    def createEditor(self, parent, option, index):
        return CodeLineEdit(parent)

class EquationDialog(MultiAttrListDialog):
    locked_vars = {"HIT", "AVOID", "CRIT_HIT", "CRIT_AVOID",
                   "DAMAGE", "DEFENSE", "MAGIC_DAMAGE", "MAGIC_DEFENSE",
                   "HITPOINTS", "MOVEMENT", "THRACIA_CRIT", "CRIT_ADD", "CRIT_MULT",
                   "SPEED_TO_DOUBLE", "STEAL_ATK", "STEAL_DEF",
                   "HEAL", "RESCUE_AID", "RESCUE_WEIGHT", "RATING", "CONSTITUTION"}

    @classmethod
    def create(cls):
        def deletion_func(model, index):
            return model._data[index.row()].nid not in cls.locked_vars

        dlg = cls(DB.equations, "Equation", ("nid", "expression"),
                  EquationMultiModel, (deletion_func, None, deletion_func), cls.locked_vars)

        equation_delegate = EquationDelegate(dlg.view)
        dlg.view.setItemDelegateForColumn(1, equation_delegate)

        return dlg

    def accept(self):
        super().accept()
        from app.engine import equations
        equations.clear()

# Testing
# Run "python -m app.editor.equation_widget"
if __name__ == '__main__':
    import sys
    from PyQt5.QtWidgets import QApplication
    app = QApplication(sys.argv)
    from app.data.serialization.versions import CURRENT_SERIALIZATION_VERSION
    DB.load('default.ltproj', CURRENT_SERIALIZATION_VERSION)
    window = EquationDialog.create()
    window.show()
    app.exec_()
