from app.editor.custom_widgets import CustomQtRoles
import os

from PyQt5.QtWidgets import QFileDialog, QMessageBox
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap, QIcon

from app.utilities import str_utils
from app.data.resources.icons import Icon, IconSheet
from app.data.resources.map_icons import MapIcon, MapIconCatalog
from app.data.resources.resources import RESOURCES
from app.utilities.data import Data
from app.data.database import references
from app.data.database.database import DB
from app.data.resources.resource_types import ResourceType as RType
from app.editor import reference_dialogs
from app.editor.base_database_gui import ResourceCollectionModel

from app.editor.settings import MainSettingsController
from app.editor.icon_editor import icon_view

class IconModel(ResourceCollectionModel):
    def __init__(self, data, window):
        super().__init__(data, window)
        self.sub_data = Data()
        for icon in self._data:
            new_icons = icon_view.icon_slice(icon, self.width, self.height)
            for i in new_icons:
                self.sub_data.append(i)

    def rowCount(self, parent=None):
        return len(self.sub_data)

    def data(self, index, role):
        if not index.isValid():
            return None
        if role == Qt.DisplayRole or role == Qt.EditRole:
            item = self.sub_data[index.row()]
            text = item.nid
            return text
        elif role == Qt.DecorationRole:
            item = self.sub_data[index.row()]
            if item.pixmap:
                pixmap = item.pixmap.scaled(max(self.width, 32), max(self.height, 32))
                return QIcon(pixmap)
        elif role == CustomQtRoles.FilterRole:
            item = self.sub_data[index.row()]
            text = item.parent_nid
            return text
        return None

    def setData(self, index, value, role):
        if not index.isValid():
            return False
        if role == Qt.EditRole:
            item: Icon = self.sub_data[index.row()]
            self.sub_data.update_nid(item, value)
            self._data.get(item.parent_nid).set_alias(item.nid, item.icon_index)
        return True

    def flags(self, index):
        if index.isValid():
            return Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable
        else:
            return Qt.NoItemFlags

    def create_new(self):
        raise NotImplementedError

    def append(self):
        self.layoutAboutToBeChanged.emit()
        self.create_new()
        view = self.window.view
        # self.dataChanged.emit(self.index(0), self.index(self.rowCount()))
        self.layoutChanged.emit()
        last_index = self.index(self.rowCount() - 1)
        view.setCurrentIndex(last_index)
        return last_index

    def new(self, index):
        item = self.sub_data[index]
        # idx = self._data.index(item.nid)
        # self.create_new()
        # self._data.move_index(len(self._data) - 1, idx + 1)
        # self.layoutChanged.emit()

    def on_nid_changed(self, old_nid, new_nid):
        pass

    def do_add(self, icon: IconSheet):
        self._data.append(icon)
        new_icons = icon_view.icon_slice(icon, self.width, self.height)
        for i in new_icons:
            self.sub_data.append(i)

    def do_delete(self, nid):
        self.layoutAboutToBeChanged.emit()
        for i in self._data:
            if i.nid == nid:
                self._data.delete(i)
        for i in self.sub_data._list[:]:
            if i.nid == nid or i.parent_nid == nid:
                self.sub_data.delete(i)
        self.layoutChanged.emit()

    def reorder_sub_data(self):
        """Re-sort the sliced icons to follow the current icon sheet order.

        Keeps the existing Icon objects (and their aliases) rather than re-slicing.
        """
        self.layoutAboutToBeChanged.emit()
        by_sheet = {}
        for icon in self.sub_data:
            by_sheet.setdefault(icon.parent_nid, []).append(icon)
        self.sub_data.clear()
        for sheet in self._data:
            for icon in by_sheet.get(sheet.nid, []):
                self.sub_data.append(icon)
        self.layoutChanged.emit()

class Icon16Model(IconModel):
    database = RESOURCES.icons16
    width, height = 16, 16
    resource_type = RType.ICONS16

    def create_new(self):
        settings = MainSettingsController()
        starting_path = settings.get_last_open_path()
        fns, ok = QFileDialog.getOpenFileNames(self.window, "Choose %s", starting_path, "PNG Files (*.png);;All Files(*)")
        icon = None
        if ok:
            for fn in fns:
                if fn.endswith('.png'):
                    nid = os.path.split(fn)[-1][:-4]  # Get rid of .png ending
                    pix = QPixmap(fn)
                    if pix.width() % self.width == 0 and pix.height() % self.height == 0:
                        nid = str_utils.get_next_name(nid, [d.nid for d in self.database])
                        icon = IconSheet(nid, fn)
                        icon.pixmap = pix
                        self.do_add(icon)
                    else:
                        QMessageBox.critical(self.window, "File Size Error!", "Icon width and height must be exactly divisible by %dx%d pixels!" % (self.width, self.height))
                else:
                    QMessageBox.critical(self.window, "File Type Error!", "Icon must be PNG format!")
            parent_dir = os.path.split(fns[-1])[0]
            settings.set_last_open_path(parent_dir)
            """
            # This `self.window.update_list` has been removed to fix a bug where
            # 1. Create a new icon
            # 2. rename the icon
            # 3. Create another new icon
            # 4. Segmentation fault with error `QSortFilterProxyModel: index from wrong model passed to mapFromSource`
            It doesn't seem to be necessary????
            """
            # self.window.update_list()  

        return icon

    def delete(self, idx):
        icon = self.sub_data[idx]
        # Deleting one icon of a sheet deletes the whole sheet
        nid = icon.parent_nid or icon.nid
        if reference_dialogs.check_delete(DB, self.resource_type, nid, 'Icon', self.window):
            self.do_delete(nid)

    def on_nid_changed(self, old_nid, new_nid):
        references.rewrite(DB, self.resource_type, old_nid, new_nid)


class Icon32Model(Icon16Model):
    database = RESOURCES.icons32
    width, height = 32, 32
    resource_type = RType.ICONS32


class Icon80Model(Icon16Model):
    database = RESOURCES.icons80
    width, height = 80, 72
    resource_type = RType.ICONS80


class MapIconModel(Icon16Model):
    database = RESOURCES.map_icons
    width, height = 48, 48
    resource_type = RType.MAP_ICONS

    def __init__(self, data, window):
        super().__init__(data, window)
        self.sub_data = self._data

    def reorder_sub_data(self):
        # Map icons are never sliced -- sub_data *is* _data, so it is already in order
        pass

    def flags(self, index):
        if index.isValid():
            return Qt.ItemIsEnabled | Qt.ItemIsSelectable
        else:
            return Qt.NoItemFlags

    def create_new(self):
        settings = MainSettingsController()
        starting_path = settings.get_last_open_path()
        fns, ok = QFileDialog.getOpenFileNames(self.window, "Choose %s", starting_path, "PNG Files (*.png);;All Files(*)")
        icon = None
        if ok:
            for fn in fns:
                if fn.endswith('.png'):
                    nid = os.path.split(fn)[-1][:-4]  # Get rid of .png ending
                    pix = QPixmap(fn)
                    if pix.width() % 16 == 0 and pix.height() % 16 == 0 and pix.width() == pix.height():
                        ratio = pix.width() / 16
                        if ratio > 3:
                            QMessageBox.critical(self.window, "File Size Error!", "Map icon width and height for file " + fn + " must be either 16x16, 32x32, or 48x48")
                            continue
                        nid = str_utils.get_next_name(nid, [d.nid for d in self.database])
                        icon = MapIcon(nid, os.path.basename(fn))
                        icon.full_path = fn
                        icon.pixmap = pix
                        self._data.append(icon)
                    else:
                        QMessageBox.critical(self.window, "File Size Error!", "Icon width and height must be exactly divisible by %dx%d pixels!" % (self.width, self.height))
                else:
                    QMessageBox.critical(self.window, "File Type Error!", "Icon must be PNG format!")
            parent_dir = os.path.split(fns[-1])[0]
            settings.set_last_open_path(parent_dir)
            self.window.update_list()
        return icon

    def delete(self, idx):
        nid = self.sub_data[idx].nid
        # An overworld node always shows some icon, so its nodes fall back to the default
        if reference_dialogs.check_delete(DB, self.resource_type, nid, 'Map Icon', self.window,
                                          fallback=MapIconCatalog.DEFAULT()):
            self.do_delete(nid)

    def on_nid_changed(self, old_nid, new_nid):
        references.rewrite(DB, self.resource_type, old_nid, new_nid)

    def do_delete(self, nid):
        self.layoutAboutToBeChanged.emit()
        for i in self._data:
            if i.nid == nid:
                self._data.delete(i)
        for i in self.sub_data._list[:]:
            if i.nid == nid:
                self.sub_data.delete(i)
        self.layoutChanged.emit()
