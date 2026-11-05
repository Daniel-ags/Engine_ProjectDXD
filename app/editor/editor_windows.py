from typing import Callable, Dict

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QDialog, QWidget

WindowMaker = Callable[[QWidget], QDialog]


class EditorWindows:
    """The editor windows open beside the main window, at most one from each maker.
    A window is deleted once it closes."""
    def __init__(self):
        self.windows: Dict[WindowMaker, QDialog] = {}

    def opener(self, create: WindowMaker) -> Callable[[QWidget], None]:
        """A menu action's slot, which opens the window create(parent) makes"""
        return lambda parent: self.open(create, parent)

    def open(self, create: WindowMaker, parent: QWidget) -> QDialog:
        """Brings the window create made to the front, if it is open, or else opens a
        new one"""
        window = self.windows.get(create)
        if window is None:
            window = create(parent)
            window.setAttribute(Qt.WA_DeleteOnClose)
            window.finished.connect(lambda _: self.forget(create, window))
            self.windows[create] = window
            window.show()
        elif window.isMinimized():
            window.showNormal()
        window.raise_()
        window.activateWindow()
        return window

    def forget(self, create: WindowMaker, window: QDialog):
        if self.windows.get(create) is window:
            del self.windows[create]

    def close_all(self):
        for window in list(self.windows.values()):
            window.close()
