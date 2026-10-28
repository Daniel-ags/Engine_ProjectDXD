"""
Shows everything the main window's own editors show, and reports what that changed.

Run by test_main_window_show.py in a process of its own, since the main window
writes the editor's settings (the current project, recent projects, window
layouts), which are pointed at a temporary folder here before anything reads
them, and holds on to the edit history's listeners and the timer.

    python -m app.tests.main_window_show PROJECT WORK_DIR

Works on a copy of PROJECT in WORK_DIR. Through the real main window it shows the
global editor's lists, every level in the level editor with each of its docks
raised and every entry of their lists selected, and every overworld with each of
its nodes selected. The last line printed is REPORT followed by JSON: how many
entries were shown, each record whose saved form changed, the undo steps made,
and any exception raised.
"""
import json
import os
import shutil
import sys
import traceback

REPORT = 'REPORT '


def main(source_proj: str, work: str) -> dict:
    from app.tests import qt_headless  # noqa: F401 -- before any QApplication
    from PyQt5.QtCore import QEvent, QSettings
    # Before the first settings controller exists
    QSettings.setDefaultFormat(QSettings.IniFormat)
    QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, os.path.join(work, 'settings'))
    from PyQt5.QtWidgets import QAbstractItemView, QApplication, QMessageBox
    from unittest.mock import patch
    app = QApplication(sys.argv)
    from app.editor.editor_locale import init_locale
    init_locale()
    import pygame
    pygame.font.init()
    # A message box would wait forever for someone to close it
    for kind in ('critical', 'warning', 'information', 'question'):
        patch.object(QMessageBox, kind, staticmethod(lambda *args, **kwargs: QMessageBox.Ok)).start()
    errors = []
    sys.excepthook = lambda *exc: errors.append(''.join(traceback.format_exception(*exc)))

    proj = os.path.join(work, os.path.basename(source_proj))
    shutil.copytree(source_proj, proj, ignore=shutil.ignore_patterns('old_portraits'))
    # The testing project's metadata leaves out its version, which a load would
    # take for the oldest and migrate from scratch
    from app.data.serialization.versions import CURRENT_SERIALIZATION_VERSION
    with open(os.path.join(proj, 'metadata.json')) as fp:
        metadata = json.load(fp)
    metadata.setdefault('serialization_version', CURRENT_SERIALIZATION_VERSION)
    with open(os.path.join(proj, 'metadata.json'), 'w') as fp:
        json.dump(metadata, fp)

    from app.data.database.database import DB
    from app.editor.edit_history import HISTORY, saved
    from app.editor.main_editor import MainEditor

    def settle():
        app.processEvents()
        app.sendPostedEvents(None, QEvent.DeferredDelete)

    def snapshot() -> dict:
        records = {id(record): ('%s %s' % (type(record).__name__, record.nid), saved(record))
                   for data in HISTORY.watched_catalogs() for record in data}
        records['mcost'] = ('the movement cost grid', DB.mcost.save())
        return records

    def show_lists(widget) -> int:
        """Selects each entry of each list on show inside widget"""
        shown = 0
        for view in widget.findChildren(QAbstractItemView):
            if view.isVisible() and view.model():
                for row in range(view.model().rowCount()):
                    view.setCurrentIndex(view.model().index(row, 0))
                    settle()
                    shown += 1
        return shown

    window = MainEditor(proj)
    window.show()
    settle()
    HISTORY.commit()
    before = snapshot()
    steps = len(HISTORY._undo)
    state = window.app_state_manager

    shown = show_lists(window.global_editor)
    for level in list(DB.levels):
        window.edit_global()
        settle()
        state.change_and_broadcast('selected_level', level.nid)
        settle()
        window.edit_level()
        settle()
        for dock in window.level_editor.docks.values():
            dock.raise_()
            settle()
            shown += 1 + show_lists(dock)
    window.edit_global()
    settle()
    for overworld in list(DB.overworlds):
        state.change_and_broadcast('selected_overworld', overworld.nid)
        settle()
        window.edit_overworld()
        settle()
        shown += show_lists(window.overworld_editor)
        for node in list(overworld.overworld_nodes):
            state.change_and_broadcast('selected_node', node.nid)
            settle()
            shown += 1
        window.edit_global()
        settle()
    HISTORY.commit()

    after = snapshot()
    return {
        'shown': shown,
        'changed': [label for key, (label, form) in after.items() if key in before and before[key][1] != form],
        'undo_steps': [change_set.label for change_set in HISTORY._undo[steps:]],
        'errors': errors,
    }


if __name__ == '__main__':
    report = main(os.path.abspath(sys.argv[1]), os.path.abspath(sys.argv[2]))
    print(REPORT + json.dumps(report), flush=True)
    # Skips tearing the window down, which only takes time
    os._exit(0)
