"""
Edits a level in the main window and an item in an editor window beside it, then
undoes them one at a time, and reports what each undo put back.

Run by test_main_window_undo.py in a process of its own (see main_window_harness.py):

    python -m app.tests.main_window_edits PROJECT WORK_DIR

The level editor's edits are a field typed in, finished by focus moving on, then a
unit moved on the map, finished by the mouse button's release. The first undo is
Ctrl+Z pressed in a main window field with no typing of its own to undo. The report
lists, after each undo, the level's title, whether the unit is where it was moved
to, and the item's name, with any exception raised, and what the Undo menu item and
the status bar say of the first undo.
"""
from app.tests.main_window_harness import open_main_window, report


def main(source_proj: str, work: str) -> dict:
    run = open_main_window(source_proj, work)
    from PyQt5.QtCore import QPoint, Qt
    from PyQt5.QtTest import QTest
    from app.data.database.database import DB
    from app.editor.edit_history import HISTORY
    from app.editor.item_editor.new_item_tab import NewItemDatabase
    window, settle = run.window, run.settle

    window.edit_level()
    settle()
    level = DB.levels.get(window.app_state_manager.state.selected_level)
    unit = level.units[0]
    item, other_item = DB.items[0], DB.items[1]
    moved_to = (1, 1) if unit.starting_position != (1, 1) else (2, 2)
    HISTORY.commit()

    # A field typed in, which focus moving on to another field finishes
    menu = window.level_editor.properties_menu
    window.level_editor.docks['Properties'].raise_()
    window.activateWindow()
    settle()
    menu.title_box.edit.setFocus()
    settle()
    QTest.keyClicks(menu.title_box.edit, ' Edited')
    menu.win_condition.edit.setFocus()
    settle()

    # A unit moved on the map, as a click there does, then the button released
    unit.starting_position = moved_to
    QTest.mouseRelease(window.level_editor.map_view.viewport(), Qt.LeftButton, pos=QPoint(8, 8))
    settle()

    # An item renamed in the item editor window, finished by choosing another item
    items = window.editor_windows.open(NewItemDatabase.edit, window)
    settle()
    items.tab.on_select(item.nid)
    QTest.keyClicks(items.tab.right_frame.name_box.edit, ' Typed')
    items.tab.on_select(other_item.nid)
    settle()

    def state() -> dict:
        return {'title': level.name, 'moved': level.units.get(unit.nid).starting_position == moved_to,
                'item': item.name}

    states = [state()]
    window.update_undo_actions()  # As the Edit menu opening does
    undo_text = window.undo_act.text()
    # The first undo is Ctrl+Z in a field of the main window that has no typing of its own to undo
    window.activateWindow()
    settle()
    menu.win_condition.edit.setFocus()
    settle()
    QTest.keyClick(menu.win_condition.edit, Qt.Key_Z, Qt.ControlModifier)
    settle()
    states.append(state())
    feedback = window.undo_feedback.text()
    for _ in range(2):
        HISTORY.undo()
        settle()
        states.append(state())
    return {'states': states, 'errors': run.errors, 'item': item.nid,
            'undo_text': undo_text, 'feedback': feedback}


if __name__ == '__main__':
    report(main)
