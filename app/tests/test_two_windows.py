import os
import random
import shutil
from unittest.mock import patch

from app.tests import qt_headless  # noqa: F401 -- before any QApplication

from PyQt5.QtCore import QEvent
from PyQt5.QtWidgets import QApplication, QWidget

from app.data.database.database import DB
from app.data.resources.resources import RESOURCES
from app.tests.test_staging import StagingEditorCase


class TwoWindowTests(StagingEditorCase):
    """Two editor windows open at once: whatever one does, in whatever order, both
    still show the database as it is, and undo takes it all back"""
    def setUp(self):
        super().setUp()
        from app.editor.editor_windows import EditorWindows
        from app.editor.edit_history import HISTORY
        from app.extensions.custom_gui import DeletionDialog
        HISTORY.clear()
        self.history = HISTORY
        self.windows = EditorWindows()
        self.addCleanup(self.close_all)
        # A deletion goes ahead, a swap taking the first other record of the kind
        self.swap_choices = {}
        for name, value in (('inform', True),):
            patcher = patch.object(DeletionDialog, name, return_value=value)
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = patch.object(DeletionDialog, 'get_swap', side_effect=self.choose_swap)
        patcher.start()
        self.addCleanup(patcher.stop)

    def choose_swap(self, tabs, swap_box, parent):
        records = swap_box.records()
        return records[0], True

    def close_all(self):
        self.windows.close_all()
        self.settle()

    def settle(self):
        QApplication.processEvents()
        QApplication.sendPostedEvents(None, QEvent.DeferredDelete)

    def open(self, tab_type):
        window = self.windows.open(tab_type.edit, None)
        self.settle()
        return window

    def units(self):
        from app.editor.unit_editor.new_unit_tab import NewUnitDatabase
        return self.open(NewUnitDatabase)

    def classes(self):
        from app.editor.class_editor.new_class_tab import NewClassDatabase
        return self.open(NewClassDatabase)

    def items(self):
        from app.editor.item_editor.new_item_tab import NewItemDatabase
        return self.open(NewItemDatabase)

    def portraits(self):
        from app.editor.portrait_editor.new_portrait_tab import NewPortraitDatabase
        return self.open(NewPortraitDatabase)

    # === As the user does ===
    def select(self, window, nid):
        window.tab.tree_list.select_item(nid)
        self.settle()

    def rename(self, window, old_nid, new_nid):
        """Types a new ID into the record's ID box and leaves it"""
        self.select(window, old_nid)
        box = window.tab.right_frame.nid_box.edit
        box.setText(new_nid)
        box.editingFinished.emit()
        self.settle()

    def rename_in_list(self, window, old_nid, new_nid):
        """Renames the record in the list, as its context menu's Rename does"""
        tree = window.tab.tree_list
        item = tree.find_item_by_nid(old_nid)
        tree.before_data_changed(old_nid)  # As the item's editor opening does
        item.setText(0, new_nid)
        tree.done_editing(new_nid)
        self.settle()

    def delete(self, window, nid):
        """Deletes the record from the list, as its context menu does"""
        tree = window.tab.tree_list
        tree.delete(tree.find_item_by_nid(nid))
        self.settle()

    def undo(self, window):
        window.undo()
        self.settle()

    def redo(self, window):
        window.redo()
        self.settle()

    # === What every window shows ===
    def assertShowsDatabase(self, window):
        tab = window.tab
        shown, _ = tab.tree_list.get_list_and_category_structure()
        self.assertEqual(sorted(tab.data.keys()), sorted(shown), window.windowTitle())
        current = tab.right_frame.current
        if current is None:
            return
        self.assertTrue(any(record is current for record in tab.data), current.nid)
        self.assertEqual(current.nid, tab.tree_list.get_selected_nid())

    def assertShowsDatabaseWithIds(self, window):
        """A database window, whose form has an ID box"""
        self.assertShowsDatabase(window)
        current = window.tab.right_frame.current
        if current is not None:
            self.assertEqual(current.nid, window.tab.right_frame.nid_box.edit.text())

    def assertUnitFormShowsUnit(self, units):
        form = units.tab.right_frame
        unit = form.current
        if unit is None:  # Nothing chosen yet
            return
        self.assertEqual(unit.klass, form.class_box.edit.currentText())
        self.assertEqual(len(DB.classes), form.class_box.edit.count())
        self.assertEqual(unit.starting_items, form.item_widget.get_items())

    def assertAllShowDatabase(self, units, *others):
        """The unit window and other database windows"""
        for window in (units,) + others:
            self.assertShowsDatabaseWithIds(window)
        self.assertUnitFormShowsUnit(units)

    def snapshot(self):
        from app.editor.edit_history import saved
        state = {name: [saved(record) for record in getattr(DB, name)]
                 for name in ('units', 'classes', 'items', 'levels')}
        # Where a portrait's file is changes with a save, which undo does not take back
        state['portraits'] = [saved(portrait)['record'] for portrait in RESOURCES.portraits]
        return state

    # === One thing at a time ===
    def test_renaming_a_class_shows_in_the_unit_window(self):
        units, classes = self.units(), self.classes()
        self.select(units, 'Eirika')
        klass = DB.units.get('Eirika').klass

        self.rename(classes, klass, klass + '_Two')

        self.assertEqual(klass + '_Two', DB.units.get('Eirika').klass)
        self.assertAllShowDatabase(units, classes)

    def test_deleting_a_class_moves_the_unit_window_to_the_swap(self):
        units, classes = self.units(), self.classes()
        self.select(units, 'Eirika')
        klass = DB.units.get('Eirika').klass

        self.delete(classes, klass)

        self.assertNotIn(klass, DB.classes.keys())
        self.assertIn(DB.units.get('Eirika').klass, DB.classes.keys())
        self.assertAllShowDatabase(units, classes)

    def test_undoing_a_class_deletion_from_the_unit_window_brings_it_back_to_both(self):
        units, classes = self.units(), self.classes()
        self.select(units, 'Eirika')
        klass = DB.units.get('Eirika').klass
        self.select(classes, klass)
        before = self.snapshot()
        self.delete(classes, klass)

        self.undo(units)

        self.assertEqual(before, self.snapshot())
        self.assertAllShowDatabase(units, classes)
        self.redo(classes)
        self.assertNotIn(klass, DB.classes.keys())
        self.assertAllShowDatabase(units, classes)

    def test_renaming_and_deleting_an_item_shows_in_the_unit_window(self):
        units, items = self.units(), self.items()
        unit = next(unit for unit in DB.units if unit.starting_items)
        self.select(units, unit.nid)
        item_nid = unit.starting_items[0][0]

        self.rename(items, item_nid, item_nid + '_Two')
        self.assertEqual(item_nid + '_Two', unit.starting_items[0][0])
        self.assertAllShowDatabase(units, items)

        self.delete(items, item_nid + '_Two')
        self.assertNotIn(item_nid + '_Two', [nid for nid, _ in unit.starting_items])
        self.assertAllShowDatabase(units, items)

        self.undo(units)
        self.undo(units)
        self.assertEqual(item_nid, unit.starting_items[0][0])
        self.assertAllShowDatabase(units, items)

    def test_renaming_a_portrait_renames_it_for_the_unit_the_unit_window_shows(self):
        units, portraits = self.units(), self.portraits()
        unit = next(unit for unit in DB.units if unit.portrait_nid in RESOURCES.portraits.keys())
        self.select(units, unit.nid)
        portrait_nid = unit.portrait_nid

        self.rename_in_list(portraits, portrait_nid, portrait_nid + '_Two')

        self.assertEqual(portrait_nid + '_Two', unit.portrait_nid)
        self.assertAllShowDatabase(units)
        self.assertShowsDatabase(portraits)
        self.undo(portraits)
        self.assertEqual(portrait_nid, unit.portrait_nid)
        self.assertAllShowDatabase(units)
        self.assertShowsDatabase(portraits)

    def test_closing_the_window_that_made_an_edit_leaves_it_for_the_other_to_undo(self):
        units, classes = self.units(), self.classes()
        klass = DB.units.get('Eirika').klass
        self.rename(classes, klass, klass + '_Two')

        classes.close()
        self.settle()
        self.undo(units)

        self.assertEqual(klass, DB.units.get('Eirika').klass)
        self.assertIn(klass, DB.classes.keys())
        self.assertShowsDatabase(units)

    def save(self):
        """Saves the project, as the main window does, to a project of the test's own"""
        from app.editor.file_manager.project_file_backend import ProjectFileBackend
        if not getattr(self, 'backend', None):
            parent = QWidget()
            self.addCleanup(parent.deleteLater)
            self.backend = ProjectFileBackend(parent, None)
            self.backend.current_proj = os.path.join(self.tmp, 'saved.ltproj')
            shutil.copytree(self.proj, self.backend.current_proj)
        self.assertTrue(self.backend.save())
        self.settle()

    def test_saving_between_edits_in_two_windows_leaves_both_able_to_undo(self):
        units, classes = self.units(), self.classes()
        before = self.snapshot()
        klass = DB.units.get('Eirika').klass
        self.rename(classes, klass, klass + '_Two')
        self.save()
        self.rename(units, 'Eirika', 'Eirika_Two')

        self.undo(classes)
        self.undo(units)

        self.assertEqual(before, self.snapshot())
        self.assertAllShowDatabase(units, classes)

    # === Anything, in any order ===
    def test_any_order_of_edits_in_two_windows_keeps_both_showing_the_database_and_undoes(self):
        for seed in range(3):
            with self.subTest(seed=seed):
                self.history.clear()
                self.run_random_edits(random.Random(seed), steps=30)
                self.close_all()
                self.reload()

    def reload(self):
        from app.data.serialization.versions import CURRENT_SERIALIZATION_VERSION
        RESOURCES.load(self.proj, CURRENT_SERIALIZATION_VERSION)
        DB.load(self.proj, CURRENT_SERIALIZATION_VERSION)
        self.history.clear()

    def run_random_edits(self, rng: random.Random, steps: int):
        units, classes, items, portraits = self.units(), self.classes(), self.items(), self.portraits()
        windows = [units, classes, items, portraits]
        before = self.snapshot()
        done = []
        count = [0]

        def fresh_nid(nid):
            count[0] += 1
            return '%s_%d' % (nid, count[0])

        def pick(window):
            return rng.choice(list(window.tab.data.keys()))

        for _ in range(steps):
            window = rng.choice(windows)
            action = rng.choice(['rename', 'rename', 'delete', 'select', 'undo', 'undo', 'redo', 'save'])
            if action == 'save' and rng.random() > 0.3:
                action = 'select'
            if action == 'delete' and len(window.tab.data) <= 3:
                action = 'rename'
            if action == 'rename':
                nid = pick(window)
                # Resources are renamed in their list, the database in the ID box
                rename = self.rename_in_list if window is portraits else self.rename
                rename(window, nid, fresh_nid(nid))
            elif action == 'delete':
                self.delete(window, pick(window))
            elif action == 'select':
                self.select(window, pick(window))
            elif action == 'undo':
                self.undo(window)
            elif action == 'redo':
                self.redo(window)
            elif action == 'save':
                self.save()
            done.append('%s in %s' % (action, window.windowTitle()))
            try:
                self.assertAllShowDatabase(units, classes, items)
                self.assertShowsDatabase(portraits)
            except AssertionError as e:
                raise AssertionError('After %s: %s' % (done, e))

        while self.history.can_undo():
            self.undo(rng.choice(windows))
        self.assertEqual(before, self.snapshot(), done)
        self.assertAllShowDatabase(units, classes, items)
        self.assertShowsDatabase(portraits)


if __name__ == '__main__':
    import unittest
    unittest.main()
