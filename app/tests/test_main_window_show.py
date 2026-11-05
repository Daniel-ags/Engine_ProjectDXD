import os
import tempfile
import unittest

from app.tests.main_window_harness import run_report


class MainWindowShowTests(unittest.TestCase):
    """The main window's global, level and overworld editors show every level, every
    entry of the level editor's docks and every overworld node without changing
    anything, as test_editor_show checks the editor windows. Each run is a process
    of its own: see main_window_show.py."""
    def assert_shows_without_changing(self, project: str):
        with tempfile.TemporaryDirectory() as work:
            report = run_report('app.tests.main_window_show', project, work)
        self.assertEqual([], report['errors'])
        self.assertGreater(report['shown'], 0)
        self.assertEqual([], report['changed'])
        self.assertEqual([], report['undo_steps'])

    def test_showing_the_testing_project_changes_nothing(self):
        self.assert_shows_without_changing('testing_proj.ltproj')

    @unittest.skipUnless(os.environ.get('LT_SLOW_TESTS'), "a slow test: set LT_SLOW_TESTS=1, or run_tests_parallel.py --slow")
    def test_showing_the_sample_project_changes_nothing(self):
        self.assert_shows_without_changing('default.ltproj')


if __name__ == '__main__':
    unittest.main()
