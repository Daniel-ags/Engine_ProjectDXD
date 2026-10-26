import os
import shutil
import tempfile
import unittest
from unittest.mock import patch

from app.tests import qt_headless  # noqa: F401 -- before any QApplication

MARKER = 'TEST_MARKER_TERRAIN'


class TilemapEditorSaveTests(unittest.TestCase):
    '''
    The Save button in the tilemap editor keeps the edits made so far: the tilemap
    editor's own Cancel rewinds only to the save, and the tilemap dialog that opened
    it keeps the save through its Cancel. Like every resource edit, the save reaches
    the project on disk when the project is saved.
    '''

    @classmethod
    def setUpClass(cls) -> None:
        import sys
        from app.editor.editor_locale import init_locale
        init_locale()
        from PyQt5.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication(sys.argv)

    def setUp(self) -> None:
        from app.data.database.database import DB
        from app.data.resources.resources import RESOURCES
        from app.data.serialization.versions import CURRENT_SERIALIZATION_VERSION
        from app.editor.edit_history import HISTORY

        self.tmp_dir = tempfile.mkdtemp()
        self.proj = os.path.join(self.tmp_dir, 'save_test.ltproj')
        # testing_proj, not default.ltproj: a sixth the size, so copying and
        # loading it takes a fraction of the time
        shutil.copytree('testing_proj.ltproj', self.proj)

        DB.load(self.proj, CURRENT_SERIALIZATION_VERSION)
        RESOURCES.load(self.proj, CURRENT_SERIALIZATION_VERSION)
        HISTORY.clear()
        self.version = CURRENT_SERIALIZATION_VERSION

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    @classmethod
    def tearDownClass(cls) -> None:
        # RESOURCES.load points the global SPRITES dict at the loaded project's
        # custom_sprites, so every temp project this class loads leaves those
        # entries holding paths under a directory tearDown has deleted. The next
        # sprites.load_images() anywhere in the suite then dies on a missing file.
        # Leave the singletons on the project the rest of the suite expects.
        from app.data.database.database import DB
        from app.data.resources.resources import RESOURCES
        from app.data.serialization.versions import CURRENT_SERIALIZATION_VERSION
        RESOURCES.load('testing_proj.ltproj', CURRENT_SERIALIZATION_VERSION)
        DB.load('testing_proj.ltproj', CURRENT_SERIALIZATION_VERSION)

    def terrain(self):
        from app.data.resources.resources import RESOURCES
        return RESOURCES.tilemaps[0].layers[0].terrain_grid.get((0, 0))

    def terrain_on_disk(self):
        """What the project on disk says the first tilemap's origin terrain is"""
        from app.data.resources.resources import RESOURCES
        RESOURCES.load(self.proj, self.version)
        return self.terrain()

    def edit_and_save(self, editor):
        editor.current.layers[0].terrain_grid[(0, 0)] = MARKER
        editor.save_current()

    @patch('app.editor.tilemap_editor.QMessageBox')
    def test_save_then_cancel_in_the_tilemap_editor_keeps_the_save(self, _message_box):
        from app.data.resources.resources import RESOURCES
        from app.editor.tilemap_editor import MapEditor
        editor = MapEditor(None, RESOURCES.tilemaps[0])
        self.edit_and_save(editor)
        # Backing out of the tilemap editor rewinds to its snapshot, which the
        # save should have advanced -- otherwise Save then Cancel loses the work.
        editor.restore()

        self.assertEqual(MARKER, self.terrain())

    @patch('app.editor.tilemap_editor.QMessageBox')
    def test_save_survives_cancelling_the_tilemap_dialog(self, _message_box):
        from app.editor.data_editor import SingleResourceEditor
        from app.editor.tile_editor.tile_tab import TileMapDatabase
        from app.editor.tilemap_editor import MapEditor
        dialog = SingleResourceEditor(TileMapDatabase, ['tilemaps'])
        self.addCleanup(dialog.stop_history)
        tab = dialog.tab
        tab.view.setCurrentIndex(tab.model.index(0))

        def edit_save_and_cancel(editor):
            self.edit_and_save(editor)
            editor.reject()
        with patch.object(MapEditor, 'exec_', edit_save_and_cancel):
            tab.edit_current()
        dialog.reject()

        self.assertEqual(MARKER, self.terrain())

    @patch('app.editor.tilemap_editor.QMessageBox')
    def test_an_unsaved_edit_goes_with_the_tilemap_dialogs_cancel(self, _message_box):
        from app.editor.data_editor import SingleResourceEditor
        from app.editor.tile_editor.tile_tab import TileMapDatabase
        from app.editor.tilemap_editor import MapEditor
        before = self.terrain()
        dialog = SingleResourceEditor(TileMapDatabase, ['tilemaps'])
        self.addCleanup(dialog.stop_history)
        tab = dialog.tab
        tab.view.setCurrentIndex(tab.model.index(0))

        def edit_and_ok(editor):
            editor.current.layers[0].terrain_grid[(0, 0)] = MARKER
            editor.accept()
        with patch.object(MapEditor, 'exec_', edit_and_ok):
            tab.edit_current()
        dialog.reject()

        self.assertEqual(before, self.terrain())

    @patch('app.editor.tilemap_editor.QMessageBox')
    def test_save_writes_nothing_to_the_project_until_it_is_saved(self, _message_box):
        from app.data.resources.resources import RESOURCES
        from app.editor.tilemap_editor import MapEditor
        before = self.terrain()
        editor = MapEditor(None, RESOURCES.tilemaps[0])
        self.edit_and_save(editor)

        self.assertEqual(before, self.terrain_on_disk())


if __name__ == '__main__':
    unittest.main()
