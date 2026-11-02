"""
Shows everything the main window's own editors show, and reports what that changed.

Run by test_main_window_show.py in a process of its own (see main_window_harness.py):

    python -m app.tests.main_window_show PROJECT WORK_DIR

Works on a copy of PROJECT in WORK_DIR. Through the real main window it shows the
global editor's lists, every level in the level editor with each of its docks
raised and every entry of their lists selected, and every overworld with each of
its nodes selected. The report says how many entries were shown, each record whose
saved form changed, the undo steps made, and any exception raised.
"""
from app.tests.main_window_harness import open_main_window, report


def main(source_proj: str, work: str) -> dict:
    run = open_main_window(source_proj, work)
    from PyQt5.QtWidgets import QAbstractItemView
    from app.data.database.database import DB
    from app.editor.edit_history import HISTORY, saved
    window, settle = run.window, run.settle

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
        'errors': run.errors,
    }


if __name__ == '__main__':
    report(main)
