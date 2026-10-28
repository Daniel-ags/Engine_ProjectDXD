"""
Opens the real main window on a copy of a project, for a script run in a process of
its own, since the main window writes the editor's settings (the current project,
recent projects, window layouts), which are pointed at a temporary folder here
before anything reads them, and holds on to the edit history's listeners and the
timer.

A script's last line printed is REPORT followed by JSON, which run_report reads.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import traceback
from dataclasses import dataclass, field
from typing import Callable, List

REPORT = 'REPORT '
# This file is app/tests/main_window_harness.py, two directories below the repo
REPO_ROOT = str(Path(__file__).resolve().parents[2])


@dataclass
class MainWindowRun:
    app: object
    window: object
    errors: List[str] = field(default_factory=list)

    def settle(self):
        """Handles the events waiting, deleting the widgets closed"""
        from PyQt5.QtCore import QEvent
        self.app.processEvents()
        self.app.sendPostedEvents(None, QEvent.DeferredDelete)


def open_main_window(source_proj: str, work: str) -> MainWindowRun:
    """The main window, shown, on a copy of source_proj in work"""
    from app.tests import qt_headless  # noqa: F401 -- before any QApplication
    from PyQt5.QtCore import QSettings
    # Before the first settings controller exists
    QSettings.setDefaultFormat(QSettings.IniFormat)
    QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, os.path.join(work, 'settings'))
    from PyQt5.QtWidgets import QApplication, QMessageBox
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

    from app.editor.main_editor import MainEditor
    run = MainWindowRun(app, MainEditor(proj), errors)
    run.window.show()
    run.settle()
    return run


def report(main: Callable[[str, str], dict]):
    """Runs main(project, work dir) from the command line and prints its report"""
    result = main(os.path.abspath(sys.argv[1]), os.path.abspath(sys.argv[2]))
    print(REPORT + json.dumps(result), flush=True)
    # Skips tearing the window down, which only takes time
    os._exit(0)


def run_report(module: str, project: str, work: str) -> dict:
    """The report of `python -m module project work`"""
    result = subprocess.run([sys.executable, '-m', module, project, work],
                            cwd=REPO_ROOT, capture_output=True, text=True, timeout=600)
    reports = [line[len(REPORT):] for line in result.stdout.splitlines() if line.startswith(REPORT)]
    if not reports:
        raise AssertionError('No report. stdout:\n%s\nstderr:\n%s' % (result.stdout[-3000:], result.stderr[-3000:]))
    return json.loads(reports[-1])
