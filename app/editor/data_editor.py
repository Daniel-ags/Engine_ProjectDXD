from PyQt5 import QtGui
from PyQt5.QtWidgets import QApplication, QDialog, QGridLayout, QDialogButtonBox, QLineEdit, \
    QPlainTextEdit, QTabWidget, QTextEdit, QSizePolicy
from PyQt5.QtCore import QEvent, Qt
from PyQt5.QtGui import QKeySequence

from app.data.resources.resources import RESOURCES
from app.data.database.database import DB

from app.data.serialization.versions import CURRENT_SERIALIZATION_VERSION
from app.editor.edit_history import HISTORY
from app.editor.settings import MainSettingsController
from app.editor.settings.preference_definitions import Preference

def resync_level_editor(main_editor):
    """Re-broadcasts the selected level after an undo changed the database.

    Undo restores a level's fields in place, which rebuilds the units and regions
    inside it. The level editor (and its sub-widgets) cache those and only refresh
    on a 'selected_level' broadcast, so without it unit edits would go to objects
    the level no longer holds -- the "unit positions revert" bug.
    """
    state_manager = main_editor.app_state_manager if main_editor else None
    if state_manager:
        current_level_nid = state_manager.state.selected_level
        # Sometimes the stored current level nid does not exist as a valid
        # level; check before broadcasting.
        if current_level_nid in DB.levels:
            state_manager.change_and_broadcast(
                'selected_level', current_level_nid)

def handles_own_undo(widget, redo: bool) -> bool:
    """Whether a focused text field has typing of its own to undo or redo"""
    if isinstance(widget, QLineEdit):
        return widget.isRedoAvailable() if redo else widget.isUndoAvailable()
    if isinstance(widget, (QTextEdit, QPlainTextEdit)):
        document = widget.document()
        return document.isRedoAvailable() if redo else document.isUndoAvailable()
    return False

class EditHistoryDialog(QDialog):
    """
    A dialog whose edits go into the edit history. Cancel undoes back to where the
    history stood when the dialog opened, or was last applied. With undo_enabled,
    Ctrl+Z and Ctrl+Shift+Z step back and forth through the history, unless the
    focused text field has typing of its own to undo.
    """
    undo_enabled = True

    def start_history(self):
        self.history_mark = HISTORY.mark()
        self.history_running = True
        app = QApplication.instance()
        app.focusChanged.connect(self.on_focus_changed)
        app.installEventFilter(self)
        self.finished.connect(self.stop_history)

    def stop_history(self):
        if not self.history_running:
            return
        self.history_running = False
        app = QApplication.instance()
        app.focusChanged.disconnect(self.on_focus_changed)
        app.removeEventFilter(self)
        for tab in self.history_tabs():
            HISTORY.unbind(tab)

    def history_tabs(self) -> list:
        raise NotImplementedError

    def current_history_tab(self):
        raise NotImplementedError

    def finish_editing(self):
        """Ends the edit in the focused field. Some fields apply their edit only when
        they lose focus -- a typed ID renames the record then -- so that has to happen
        before the dialog commits or undoes, not after it closes."""
        focused = QApplication.focusWidget()
        if focused is not None and self.isAncestorOf(focused):
            focused.clearFocus()

    def apply_history(self):
        self.history_mark = HISTORY.mark()

    def cancel_history(self):
        self.finish_editing()
        HISTORY.undo_to(self.history_mark)
        resync_level_editor(self.main_editor)

    def on_focus_changed(self, old, new):
        # The field losing focus has finished its edit by now: Qt sends it
        # FocusOut before announcing the change
        if new is not None and self.isAncestorOf(new):
            HISTORY.commit()

    def eventFilter(self, obj, event):
        if event.type() == QEvent.KeyPress and self.undo_enabled and self.isActiveWindow():
            if event.matches(QKeySequence.Undo):
                redo = False
            elif event.matches(QKeySequence.Redo):
                redo = True
            else:
                return super().eventFilter(obj, event)
            if not self.current_history_tab().supports_undo or \
                    handles_own_undo(QApplication.focusWidget(), redo):
                return super().eventFilter(obj, event)
            if redo:
                self.redo()
            else:
                self.undo()
            return True
        return super().eventFilter(obj, event)

    def undo(self):
        self.finish_editing()
        # Edits from before the dialog opened are not this dialog's to take back
        if HISTORY.undo(floor=self.history_mark):
            self.after_history_change()

    def redo(self):
        self.finish_editing()
        if HISTORY.redo():
            self.after_history_change()

    def after_history_change(self):
        for tab in self.history_tabs():
            if tab.supports_undo:
                tab.after_history_change()
        resync_level_editor(self.main_editor)

class SingleDatabaseEditor(EditHistoryDialog):
    def __init__(self, tab, parent=None):
        super().__init__(parent)
        self.window = parent
        self.main_editor = self.window

        self.set_up()

        self.tab = tab.create(self)
        self.grid.addWidget(self.tab, 0, 0, 1, 2)

        self.setWindowTitle(self.tab.windowTitle())

        # Restore Geometry
        self.settings = MainSettingsController()
        geometry = self.settings.component_controller.get_geometry(self._type())
        if geometry:
            self.restoreGeometry(geometry)
        state = self.settings.component_controller.get_state(self._type())
        if state:
            self.tab.splitter.restoreState(state)

    def keyPressEvent(self, keypress: QtGui.QKeyEvent) -> None:
        if keypress.key() == self.settings.get_preference(Preference.EDITOR_CLOSE_BUTTON):
            self.reject()
        else:
            pass

    def set_up(self):
        self.setStyleSheet("font: 10pt;")
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        self.setWindowFlag(Qt.WindowMinMaxButtonsHint, True)

        self.start_history()

        self.grid = QGridLayout(self)
        self.setLayout(self.grid)

        self.buttonbox = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel | QDialogButtonBox.Apply, Qt.Horizontal, self)
        self.grid.addWidget(self.buttonbox, 1, 1)
        self.buttonbox.accepted.connect(self.accept)
        self.buttonbox.rejected.connect(self.reject)
        self.buttonbox.button(QDialogButtonBox.Apply).clicked.connect(self.apply)

    def history_tabs(self) -> list:
        return [self.tab]

    def current_history_tab(self):
        return self.tab

    def on_tab_close(self):
        self.tab.on_tab_close()

    def accept(self):
        self.finish_editing()
        self.save_geometry()
        self.on_tab_close()
        HISTORY.commit()
        super().accept()

    def reject(self):
        self.cancel_history()
        self.save_geometry()
        self.on_tab_close()
        super().reject()

    def apply(self):
        self.apply_history()

    def closeEvent(self, event):
        self.save_geometry()
        self.on_tab_close()
        super().closeEvent(event)

    def _type(self):
        return self.tab.__class__.__name__

    def save_geometry(self):
        self.settings.component_controller.set_geometry(self._type(), self.saveGeometry())
        self.settings.component_controller.set_state(self._type(), self.tab.splitter.saveState())

class MultiDatabaseEditor(SingleDatabaseEditor):
    def __init__(self, tabs, parent=None):
        EditHistoryDialog.__init__(self, parent)
        self.window = parent
        self.main_editor = self.window

        self.set_up()

        self.tab_bar = QTabWidget(self)
        self.grid.addWidget(self.tab_bar, 0, 0, 1, 2)
        self.tabs = []
        for tab in tabs:
            new_tab = tab.create(self)
            self.tabs.append(new_tab)
            self.tab_bar.addTab(new_tab, new_tab.windowTitle())

        self.current_tab = self.tab_bar.currentWidget()
        self.tab_bar.currentChanged.connect(self.on_tab_changed)

        # Restore Geometry
        self.settings = MainSettingsController()
        geometry = self.settings.component_controller.get_geometry(self._type())
        if geometry:
            self.restoreGeometry(geometry)
        for tab in self.tabs:
            _type = tab.__class__.__name__
            state = self.settings.component_controller.get_state(_type)
            if state and tab.splitter:
                tab.splitter.restoreState(state)
            # Also handle the frame itself
            right_frame_type = _type + '_right_frame'
            state = self.settings.component_controller.get_state(right_frame_type)
            if state:
                tab.right_frame.restore_state(state)

    def history_tabs(self) -> list:
        return self.tabs

    def current_history_tab(self):
        return self.current_tab

    def on_tab_changed(self, idx):
        # Make each tab individually resizable
        for i in range(self.tab_bar.count()):
            if i == idx:
                self.tab_bar.widget(i).setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
            else:
                self.tab_bar.widget(i).setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)

        new_tab = self.tab_bar.currentWidget()
        self.current_tab = new_tab
        self.current_tab.update_list()
        self.current_tab.reset()

    def _type(self):
        s = ''
        for tab in self.tabs:
            s += tab.__class__.__name__
        return s

    def on_tab_close(self, event=None):
        if event:
            for tab in self.tabs:
                tab.closeEvent(event)

    def save_geometry(self):
        self.settings.component_controller.set_geometry(self._type(), self.saveGeometry())
        for tab in self.tabs:
            _type = tab.__class__.__name__
            if hasattr(tab, 'splitter') and tab.splitter:
                self.settings.component_controller.set_state(_type, tab.splitter.saveState())
            if hasattr(tab, 'right_frame') and hasattr(tab.right_frame, 'save_state'):
                state = tab.right_frame.save_state()
                right_frame_type = _type + '_right_frame'
                if state:
                    self.settings.component_controller.set_state(right_frame_type, state)

    def closeEvent(self, event):
        self.save_geometry()
        self.on_tab_close(event)
        super().closeEvent(event)

class SingleResourceEditor(EditHistoryDialog):
    # Resources are not recorded yet, so an undo would take back only the
    # database's half of an edit, like the units a portrait rename reached
    undo_enabled = False

    def __init__(self, tab, resource_types=None, parent=None, *args, **kwargs):
        super().__init__(parent)
        self.window = parent
        self.main_editor = parent
        self.resource_types = resource_types
        self.setStyleSheet("font: 10pt;")
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        self.setWindowFlag(Qt.WindowMinMaxButtonsHint, True)

        self.start_history()

        self.grid = QGridLayout(self)
        self.setLayout(self.grid)

        self.buttonbox = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel | QDialogButtonBox.Apply, Qt.Horizontal, self)
        self.grid.addWidget(self.buttonbox, 1, 1)
        self.buttonbox.accepted.connect(self.accept)
        self.buttonbox.rejected.connect(self.reject)
        self.buttonbox.button(QDialogButtonBox.Apply).clicked.connect(self.apply)

        self.tab = tab.create(self, *args, **kwargs)
        self.grid.addWidget(self.tab, 0, 0, 1, 2)

        self.setWindowTitle(self.tab.windowTitle())

        # Restore Geometry
        self.settings = MainSettingsController()
        geometry = self.settings.component_controller.get_geometry(self._type())
        if geometry:
            self.restoreGeometry(geometry)
        state = self.settings.component_controller.get_state(self._type())
        if state:
            self.tab.splitter.restoreState(state)

    def history_tabs(self) -> list:
        return [self.tab]

    def current_history_tab(self):
        return self.tab

    def accept(self):
        self.finish_editing()
        current_proj = self.settings.get_current_project()
        # RESOURCES must be saved here because if we grabbed a file from somewhere else
        # on our computer not under the project tree, we must transfer it under the project
        # tree. The project does not and should not know the absolute path of every one of its
        # resources, just where the resources should be.
        if current_proj and current_proj != 'default.ltproj':
            RESOURCES.save(current_proj, self.resource_types)
        self.save_geometry()
        HISTORY.commit()
        super().accept()
        self.close()

    def reject(self):
        current_proj = self.settings.get_current_project()
        if current_proj:
            RESOURCES.load(current_proj, CURRENT_SERIALIZATION_VERSION)
        self.cancel_history()
        self.save_geometry()
        super().reject()
        self.close()

    def apply(self):
        current_proj = self.settings.get_current_project()
        if current_proj and current_proj != 'default.ltproj':
            RESOURCES.save(current_proj, self.resource_types)
        self.apply_history()
        self.save_geometry()

    def closeEvent(self, event):
        self.save_geometry()
        super().closeEvent(event)

    def _type(self):
        return self.tab.__class__.__name__

    def save_geometry(self):
        self.settings.component_controller.set_geometry(self._type(), self.saveGeometry())
        if hasattr(self.tab, 'splitter'):
            self.settings.component_controller.set_state(self._type(), self.tab.splitter.saveState())

class MultiResourceEditor(SingleResourceEditor):
    def __init__(self, tabs, resource_types, parent=None):
        EditHistoryDialog.__init__(self, parent)
        self.window = parent
        self.main_editor = parent
        self.resource_types = resource_types
        self.setWindowTitle("Resource Editor")
        self.setStyleSheet("font: 10pt;")
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        self.setWindowFlag(Qt.WindowMinMaxButtonsHint, True)

        self.start_history()

        self.grid = QGridLayout(self)
        self.setLayout(self.grid)

        self.buttonbox = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel | QDialogButtonBox.Apply, Qt.Horizontal, self)
        self.grid.addWidget(self.buttonbox, 1, 1)
        self.buttonbox.accepted.connect(self.accept)
        self.buttonbox.rejected.connect(self.reject)
        self.buttonbox.button(QDialogButtonBox.Apply).clicked.connect(self.apply)

        self.tab_bar = QTabWidget(self)
        self.grid.addWidget(self.tab_bar, 0, 0, 1, 2)
        self.tabs = []
        for tab in tabs:
            new_tab = tab.create(self)
            self.tabs.append(new_tab)
            self.tab_bar.addTab(new_tab, new_tab.windowTitle())

        self.current_tab = self.tab_bar.currentWidget()
        self.tab_bar.currentChanged.connect(self.on_tab_changed)

        # Restore Geometry
        self.settings = MainSettingsController()
        geometry = self.settings.component_controller.get_geometry(self._type())
        if geometry:
            self.restoreGeometry(geometry)
        for tab in self.tabs:
            _type = tab.__class__.__name__
            state = self.settings.component_controller.get_state(_type)
            if state and tab.splitter:
                tab.splitter.restoreState(state)
            # Also handle the frame itself
            right_frame_type = _type + '_right_frame'
            state = self.settings.component_controller.get_state(right_frame_type)
            if state:
                tab.right_frame.restore_state(state)

    def history_tabs(self) -> list:
        return self.tabs

    def current_history_tab(self):
        return self.current_tab

    def on_tab_changed(self, idx):
        # Make each tab individually resizable
        for i in range(self.tab_bar.count()):
            if i == idx:
                self.tab_bar.widget(i).setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
            else:
                self.tab_bar.widget(i).setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)

        new_tab = self.tab_bar.currentWidget()
        self.current_tab = new_tab
        self.current_tab.update_list()
        self.current_tab.reset()

    def _type(self):
        s = ''
        for tab in self.tabs:
            s += tab.__class__.__name__
        return s

    def save_geometry(self):
        self.settings.component_controller.set_geometry(self._type(), self.saveGeometry())
        for tab in self.tabs:
            _type = tab.__class__.__name__
            if hasattr(tab, 'splitter') and tab.splitter:
                self.settings.component_controller.set_state(_type, tab.splitter.saveState())
            if hasattr(tab, 'right_frame') and hasattr(tab.right_frame, 'save_state'):
                state = tab.right_frame.save_state()
                right_frame_type = _type + '_right_frame'
                if state:
                    self.settings.component_controller.set_state(right_frame_type, state)

    def closeEvent(self, event):
        self.save_geometry()
        for tab in self.tabs:
            tab.closeEvent(event)
        super().closeEvent(event)

class NewMultiResourceEditor(MultiResourceEditor):
    def on_tab_changed(self, idx):
        # Make each tab individually resizable
        for i in range(self.tab_bar.count()):
            if i == idx:
                self.tab_bar.widget(i).setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
            else:
                self.tab_bar.widget(i).setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)

        new_tab = self.tab_bar.currentWidget()
        self.current_tab = new_tab
        self.current_tab.reset()
