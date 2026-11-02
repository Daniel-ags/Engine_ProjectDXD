import os
import unittest

from app.tests import qt_headless

from app.editor.settings import MainSettingsController


class TemporarySettingsTests(unittest.TestCase):
    def test_every_settings_controller_writes_to_the_temporary_folder(self):
        main = MainSettingsController()

        for controller in (main, main.component_controller, main.project_history_controller):
            self.assertEqual(os.path.normcase(qt_headless.SETTINGS_DIR),
                             os.path.normcase(os.path.dirname(controller.state.fileName())))

    def test_recent_projects_stay_out_of_the_developers_settings(self):
        settings = MainSettingsController()
        settings.append_or_bump_project('Temporary', qt_headless.SETTINGS_DIR)

        self.assertEqual(qt_headless.SETTINGS_DIR, settings.get_last_ten_projects()[0].path)
        settings.project_history_controller.state.sync()
        self.assertTrue(os.path.isfile(settings.project_history_controller.state.fileName()))


if __name__ == '__main__':
    unittest.main()
