import logging
import unittest
from unittest.mock import patch

from app.tests import qt_headless  # noqa: F401 -- before any QApplication

from PyQt5.QtWidgets import QApplication

from app.data.database.database import DB
from app.data.resources.resources import RESOURCES
from app.data.serialization.versions import CURRENT_SERIALIZATION_VERSION


class HiddenMapViewTests(unittest.TestCase):
    """A map view asked to draw while hidden, as the global and overworld editors'
    are behind the level editor's, draws once it shows, and only then"""
    @classmethod
    def setUpClass(cls):
        import sys
        cls.app = QApplication.instance() or QApplication(sys.argv)

    def setUp(self):
        from app.editor.map_view import SimpleMapView
        logging.disable(logging.CRITICAL)
        self.addCleanup(logging.disable, logging.NOTSET)
        DB.load('testing_proj.ltproj', CURRENT_SERIALIZATION_VERSION)
        RESOURCES.load('testing_proj.ltproj', CURRENT_SERIALIZATION_VERSION)
        self.view = SimpleMapView()
        self.addCleanup(self.view.deleteLater)
        self.level = next(level for level in DB.levels if RESOURCES.tilemaps.get(level.tilemap))

    def draws(self, action) -> int:
        from app.editor import tilemap_editor
        with patch.object(tilemap_editor, 'get_tilemap_pixmap', side_effect=tilemap_editor.get_tilemap_pixmap) as draw:
            action()
            QApplication.processEvents()
        return draw.call_count

    def test_hidden_it_draws_nothing_until_it_shows(self):
        def asked_twice():
            self.view.set_current_level(self.level)
            self.view.update_view()
        self.assertEqual(0, self.draws(asked_twice))
        self.assertIsNone(self.view.working_image)

        self.assertEqual(1, self.draws(self.view.show))
        self.assertIsNotNone(self.view.working_image)

    def test_on_show_it_draws_when_asked(self):
        self.view.show()
        self.assertEqual(1, self.draws(lambda: self.view.set_current_level(self.level)))
        # Shown again with nothing asked meanwhile, it has nothing new to draw
        self.view.hide()
        self.assertEqual(0, self.draws(self.view.show))


if __name__ == '__main__':
    unittest.main()
