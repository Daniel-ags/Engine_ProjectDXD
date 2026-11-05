'''
Import before the first QApplication to run Qt without a screen

The offscreen platform doesn't ask the OS for its fonts. It reads them from Qt's
own lib/fonts folder, which the PyQt5 wheels leave out, and warns
"QFontDatabase: Cannot find font directory" every time it looks. On Windows,
point it at the system fonts instead.

It also warns that it "does not support propagateSizeHints()" whenever a test
shows a widget, and "does not support raise()" whenever one is raised, which say
nothing about the widget, so those messages are dropped. Every other Qt message
still reaches stderr

The editor's settings (recent projects, the current project, window layouts,
preferences) go to files in a temporary folder of this process's own. Otherwise
they are the developer's own: on Windows, QSettings(company, product) is the
registry whatever the default format or settings path says
'''
import atexit
import os
import shutil
import sys
import tempfile

from PyQt5.QtCore import QSettings, qInstallMessageHandler

from app.editor.settings import component_settings_controller, main_settings_controller, project_history_controller

SETTINGS_DIR = tempfile.mkdtemp(prefix='lt_test_settings_')
atexit.register(shutil.rmtree, SETTINGS_DIR, ignore_errors=True)


class _TemporarySettings(QSettings):
    def __init__(self, company, product):
        super().__init__(os.path.join(SETTINGS_DIR, '%s_%s.ini' % (company, product)), QSettings.IniFormat)


for _controller in (component_settings_controller, main_settings_controller, project_history_controller):
    _controller.QSettings = _TemporarySettings

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
if sys.platform == 'win32':
    os.environ.setdefault('QT_QPA_FONTDIR', os.path.join(os.environ.get('WINDIR', r'C:\Windows'), 'Fonts'))

IGNORED_MESSAGES = {'This plugin does not support propagateSizeHints()',
                    'This plugin does not support raise()'}

def _message_handler(mode, context, message):
    if message not in IGNORED_MESSAGES:
        print(message, file=sys.stderr)

qInstallMessageHandler(_message_handler)
