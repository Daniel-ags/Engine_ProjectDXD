import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from app.tests.main_window_show import REPORT

# This file is app/tests/test_main_window_show.py, two directories below the repo
REPO_ROOT = str(Path(__file__).resolve().parents[2])


class MainWindowShowTests(unittest.TestCase):
    """The main window's global, level and overworld editors show every level, every
    entry of the level editor's docks and every overworld node without changing
    anything, as test_editor_show checks the editor windows. Each run is a process
    of its own: see main_window_show.py."""
    def shown_by_main_window(self, project: str) -> dict:
        with tempfile.TemporaryDirectory() as work:
            result = subprocess.run([sys.executable, '-m', 'app.tests.main_window_show', project, work],
                                    cwd=REPO_ROOT, capture_output=True, text=True, timeout=600)
        reports = [line[len(REPORT):] for line in result.stdout.splitlines() if line.startswith(REPORT)]
        self.assertTrue(reports, 'No report. stdout:\n%s\nstderr:\n%s' % (result.stdout[-3000:], result.stderr[-3000:]))
        return json.loads(reports[-1])

    def assert_shows_without_changing(self, project: str):
        report = self.shown_by_main_window(project)
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
