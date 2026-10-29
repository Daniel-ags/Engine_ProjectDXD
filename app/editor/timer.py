import time

from typing import Callable

from PyQt5.QtWidgets import QDockWidget, QWidget
from PyQt5.QtCore import QObject, QTimer, pyqtSignal

from app import constants
from app import counters
from app.counters import GenericAnimCounter
from app.editor.settings.preference_definitions import Preference
from app.utilities.utils import frames2ms

from app.editor.settings import MainSettingsController

class Timer(QWidget):
    tick_elapsed = pyqtSignal()

    def __init__(self, fps=60):
        super().__init__()
        self.main_timer = QTimer()
        self.main_timer.timeout.connect(self.tick)
        timer_speed = int(1000/float(fps))
        self.main_timer.setInterval(timer_speed)
        self.main_timer.start()

        self.autosave_timer = QTimer()
        autosave_time = MainSettingsController().get_preference(Preference.AUTOSAVE_TIME)
        self.autosave_timer.setInterval(int(autosave_time * 60 * 1000))
        self.autosave_timer.start()

        self.passive_counter = GenericAnimCounter.from_frames_back_and_forth([16, 2, 16], frame_duration=constants.FRAMERATE * 2, get_time=lambda: time.time() * 1000)
        self.active_counter = GenericAnimCounter.from_frames_back_and_forth([10, 2, 10], frame_duration=constants.FRAMERATE * 2, get_time=lambda: time.time() * 1000)
        self.move_sprite_counter = GenericAnimCounter.from_frames([6, 3, 6, 3], frame_duration=constants.FRAMERATE * 2, get_time=lambda: time.time() * 1000)

    def tick(self):
        self.tick_elapsed.emit()

    def start(self):
        self.main_timer.start()
        self.autosave_timer.start()

    def stop(self):
        self.main_timer.stop()
        self.autosave_timer.stop()

TIMER = None
def get_timer():
    global TIMER
    if not TIMER:
        TIMER = Timer(constants.FPS//2)
    return TIMER

class _TickGate(QObject):
    """Passes the tick on to a widget's slot. A child of the widget, so the connection
    goes when the widget does"""
    def __init__(self, widget: QWidget, slot: Callable[[], None]):
        super().__init__(widget)
        self.slot = slot

    def on_tick(self):
        widget = self.parent()
        # Called unbound, like QWidget.window below. A widget hidden behind another
        # tab or editor redraws on the first tick after it shows again
        if QWidget.isVisible(widget) and in_active_window(widget):
            self.slot()

def in_active_window(widget: QWidget) -> bool:
    # Called unbound, since editor forms keep their parent in a window attribute
    window = QWidget.window(widget)
    if isinstance(window, QDockWidget):
        # A dock floating beside its main window works with it
        return window.isActiveWindow() or window.parentWidget().isActiveWindow()
    return window.isActiveWindow()

def connect_tick(widget: QWidget, slot: Callable[[], None]) -> None:
    """Calls slot on each tick while widget is on show in the window being worked in.
    Windows in the background, windows closed, and widgets hidden don't redraw."""
    gate = _TickGate(widget, slot)
    get_timer().tick_elapsed.connect(gate.on_tick)
