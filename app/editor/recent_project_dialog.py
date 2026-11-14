from __future__ import annotations

import os
from typing import List, Optional

from PyQt5.QtCore import QAbstractTableModel, QDir, QModelIndex, Qt
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import (QFileDialog, QHBoxLayout, QHeaderView,
                             QMessageBox, QPushButton, QTableView, QToolButton,
                             QVBoxLayout)

from app import dark_theme
from app.editor.file_manager.project_initializer import ProjectInitializer
from app.editor.settings.main_settings_controller import MainSettingsController
from app.editor.settings.preference_definitions import Preference
from app.editor.settings.project_history_controller import ProjectHistoryEntry
from app.extensions.custom_gui import SimpleDialog

class RecentProjectsModel(QAbstractTableModel):
    def __init__(self, data: List[ProjectHistoryEntry]):
        super(RecentProjectsModel, self).__init__()
        self._data = data
        # The last column holds the selected row's remove button
        self.header_labels = ["Project Title",
                              "Project Full Path", "Last Opened on...", ""]

    def data(self, index, role):
        if role == Qt.DisplayRole:
            return self.getColumnProperty(index, self._data[index.row()])
        return None

    def rowCount(self, index: QModelIndex):
        return len(self._data)

    def columnCount(self, index: QModelIndex):
        return 4

    def remove_row(self, row: int):
        self.beginRemoveRows(QModelIndex(), row, row)
        self._data.pop(row)
        self.endRemoveRows()

    def getColumnProperty(self, index: QModelIndex, entry: ProjectHistoryEntry) -> str:
        if index.column() == 0:
            return entry.name
        elif index.column() == 1:
            return entry.path
        elif index.column() == 2:
            return entry.get_last_open_time().strftime('%Y-%m-%d %a %H:%M:%S') if entry.get_last_open_time() else "Unknown"
        return None

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return self.header_labels[section]
        return QAbstractTableModel.headerData(self, section, orientation, role)


DEFAULT_PROJECT = "default.ltproj"
REMOVE_COLUMN = 3


class RecentProjectDialog(SimpleDialog):
    def __init__(self, recent_projects: List[ProjectHistoryEntry], load_only: bool):
        super().__init__()
        self.setWindowTitle("Recent Projects")
        self.settings = MainSettingsController()
        # With no history, default.ltproj stands in, and has nothing to remove
        self.in_history = bool(recent_projects)
        self.projects = recent_projects if self.in_history else [ProjectHistoryEntry(DEFAULT_PROJECT, DEFAULT_PROJECT)]
        self._selected_path: Optional[str] = None

        layout = QVBoxLayout()
        self.setLayout(layout)

        self.project_table = QTableView()
        self.project_table.verticalHeader().hide()
        self.project_table.setShowGrid(False)
        self.model = RecentProjectsModel(self.projects)
        self.project_table.setModel(self.model)
        header = self.project_table.horizontalHeader()
        for column in range(REMOVE_COLUMN):
            header.setSectionResizeMode(column, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(REMOVE_COLUMN, QHeaderView.Fixed)
        header.resizeSection(REMOVE_COLUMN, 24)
        self.project_table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.project_table.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.project_table.setSelectionBehavior(QTableView.SelectRows)
        self.project_table.setSelectionMode(QTableView.SingleSelection)
        self.project_table.selectionModel().currentRowChanged.connect(self.on_current_row_changed)
        self.project_table.doubleClicked.connect(self.on_double_click_project)

        button_layout = QHBoxLayout()
        self.confirm_button = QPushButton("Open selected project", self)
        self.confirm_button.clicked.connect(self.on_click_confirm)
        button_layout.addWidget(self.confirm_button)
        self.open_other_button = QPushButton("Open other...", self)
        self.open_other_button.clicked.connect(self.on_click_open)
        button_layout.addWidget(self.open_other_button)
        if not load_only:
            self.new_button = QPushButton("Create New...", self)
            self.new_button.clicked.connect(self.on_click_new)
            button_layout.addWidget(self.new_button)

        layout.addWidget(self.project_table)
        layout.addLayout(button_layout)

        self.select_row(0)
        self.fit_size()

    def fit_size(self):
        self.project_table.resizeColumnsToContents()
        self.project_table.horizontalHeader().resizeSection(REMOVE_COLUMN, 24)
        dialogWidth = self.project_table.horizontalHeader().length() + 24
        dialogHeight = self.project_table.verticalHeader().length() + 104
        self.setFixedSize(dialogWidth, dialogHeight)

    def select_row(self, row: int):
        self.project_table.setCurrentIndex(self.model.index(row, 0))
        self.project_table.selectRow(row)
        # setCurrentIndex does not announce a row that was already current
        self.on_current_row_changed(self.model.index(row, 0), QModelIndex())

    def on_current_row_changed(self, current: QModelIndex, previous: QModelIndex):
        if previous.isValid():
            self.project_table.setIndexWidget(self.model.index(previous.row(), REMOVE_COLUMN), None)
        if not current.isValid():
            return
        project = self.projects[current.row()]
        self._selected_path = project.path
        if self.in_history:
            remove_button = QToolButton(self)
            remove_button.setIcon(QIcon(f"{dark_theme.get_theme().icon_dir()}/x.png"))
            remove_button.setToolTip("Remove from recent projects")
            remove_button.setStyleSheet(
                "QToolButton { border: 0px solid #575757; background-color: transparent; }")
            remove_button.clicked.connect(lambda: self.remove_project(project))
            self.project_table.setIndexWidget(self.model.index(current.row(), REMOVE_COLUMN), remove_button)

    def remove_project(self, project: ProjectHistoryEntry):
        self.settings.remove_project(project.path)
        row = self.projects.index(project)
        self.model.remove_row(row)
        if not self.projects:
            self.in_history = False
            self.model.beginInsertRows(QModelIndex(), 0, 0)
            self.projects.append(ProjectHistoryEntry(DEFAULT_PROJECT, DEFAULT_PROJECT))
            self.model.endInsertRows()
        self.select_row(min(row, len(self.projects) - 1))
        self.fit_size()

    def on_double_click_project(self, index: QModelIndex):
        self._selected_path = self.projects[index.row()].path
        self.accept()

    def on_click_confirm(self):
        self.accept()

    def on_click_open(self):
        if self.projects:
            starting_path = os.path.join(self.projects[0].path, '..')
        else:
            starting_path = QDir.currentPath()
        fn = QFileDialog.getExistingDirectory(
            self, "Open Project Directory", starting_path)
        if fn:
            if not fn.endswith('.ltproj'):
                QMessageBox.warning(self, "Incorrect directory type",
                                    "%s is not an .ltproj." % fn)
            else:
                self._selected_path = fn
                self.accept()

    def on_click_new(self):
        project_initializer = ProjectInitializer()
        result = project_initializer.full_create_new_project()
        if result:
            _, _, path = result
            self._selected_path = path
            self.accept()

    def closeEvent(self, event):
        self._selected_path = None
        super().closeEvent(event)

    def get_selected(self) -> Optional[str]:
        return self._selected_path


def choose_recent_project(load_only: bool = False, allow_auto_open: bool = False) -> Optional[str]:
    """
    str means go open that project at that path
    None means don't do anything (When you press X or close on the dialog)
    """
    settings = MainSettingsController()
    if allow_auto_open and settings.get_preference(Preference.AUTO_OPEN_LAST):
        return settings.get_current_project(fallback=DEFAULT_PROJECT)
    dialog = RecentProjectDialog(settings.get_last_ten_projects(), load_only)
    dialog.exec_()
    selected_path: Optional[str] = \
        dialog.get_selected()
    return selected_path
