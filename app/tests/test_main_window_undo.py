import tempfile
import unittest

from app.tests.main_window_harness import run_report


class MainWindowUndoTests(unittest.TestCase):
    """The level editor's edits in the main window are undo steps of their own, apart
    from each other and from an editor window's edits. A process of its own: see
    main_window_edits.py."""
    def test_each_edit_in_either_window_is_undone_on_its_own(self):
        with tempfile.TemporaryDirectory() as work:
            report = run_report('app.tests.main_window_edits', 'testing_proj.ltproj', work)
        self.assertEqual([], report['errors'])
        edited, after_item, after_unit, after_title = report['states']
        self.assertTrue(edited['title'].endswith(' Edited'))
        self.assertTrue(edited['moved'])
        self.assertTrue(edited['item'].endswith(' Typed'))
        # Last made, first undone: the item, by Ctrl+Z in a main window field with
        # nothing of its own to undo, then the unit, then the title
        self.assertEqual({'title': edited['title'], 'moved': True, 'item': edited['item'][:-len(' Typed')]},
                         after_item)
        self.assertEqual(dict(after_item, moved=False), after_unit)
        self.assertEqual(dict(after_unit, title=edited['title'][:-len(' Edited')]), after_title)

        # The Undo menu item names what it would undo, and the status bar what it did
        self.assertEqual('Undo edit to %s (Items)' % report['item'], report['undo_text'])
        self.assertEqual('Undid edit to %s (Items)' % report['item'], report['feedback'])


if __name__ == '__main__':
    unittest.main()
