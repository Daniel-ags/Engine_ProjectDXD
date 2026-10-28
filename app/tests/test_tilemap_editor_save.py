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
        # Backing out of the tilemap editor rewinds to the save -- otherwise
        # Save then Cancel loses the work.
        editor.reject()

        self.assertEqual(MARKER, self.terrain())

    @patch('app.editor.tilemap_editor.QMessageBox')
    def test_save_survives_closing_the_tilemap_dialog(self, _message_box):
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
    def test_an_unsaved_edit_goes_with_an_undo_in_the_tilemap_dialog(self, _message_box):
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
        self.assertEqual(MARKER, self.terrain())
        dialog.undo()

        self.assertEqual(before, self.terrain())

    @patch('app.editor.tilemap_editor.QMessageBox')
    def test_save_writes_nothing_to_the_project_until_it_is_saved(self, _message_box):
        from app.data.resources.resources import RESOURCES
        from app.editor.tilemap_editor import MapEditor
        before = self.terrain()
        editor = MapEditor(None, RESOURCES.tilemaps[0])
        self.edit_and_save(editor)

        self.assertEqual(before, self.terrain_on_disk())


class TileEditorUndoTests(TilemapEditorSaveTests):
    """Undo and redo in the tilemap and tileset terrain editors reach only the steps
    made since the editor opened, one per stroke; Cancel takes them all back, and
    after OK they stay in the edit history"""
    def setUp(self) -> None:
        super().setUp()
        from app.data.resources.resources import RESOURCES
        from app.editor.edit_history import HISTORY
        self.history = HISTORY
        self.tilemap = RESOURCES.tilemaps[0]
        # An edit from before the editor opens, which its undo must leave alone
        HISTORY.bind(self.tilemap, RESOURCES.tilemaps, self)
        self.grid()[(2, 0)] = 'Before'
        HISTORY.unbind(self)
        self.original = dict(self.grid())

    def grid(self) -> dict:
        # Read afresh each time: an undo rebuilds the tilemap's layers
        return self.tilemap.layers[0].terrain_grid

    def open_map_editor(self):
        from app.editor.tilemap_editor import MapEditor
        editor = MapEditor(None, self.tilemap)
        self.addCleanup(editor.deleteLater)
        return editor

    def stroke(self, editor, coord, terrain_nid):
        """Paints terrain, finished by the mouse button's release on the map"""
        from PyQt5.QtCore import QPoint, Qt
        from PyQt5.QtTest import QTest
        editor.current.layers[0].terrain_grid[coord] = terrain_nid
        QTest.mouseRelease(editor.view.viewport(), Qt.LeftButton, pos=QPoint(4, 4))

    def test_each_stroke_is_undone_and_redone_on_its_own_and_undo_stops_where_it_opened(self):
        editor = self.open_map_editor()
        self.stroke(editor, (0, 0), 'A')
        self.stroke(editor, (1, 0), 'B')

        editor.undo()
        self.assertEqual('A', self.grid().get((0, 0)))
        self.assertEqual(self.original.get((1, 0)), self.grid().get((1, 0)))
        editor.undo()
        editor.undo()  # Nothing left of this editor's to undo
        self.assertEqual(self.original, dict(self.grid()))
        self.assertEqual('Before', self.grid()[(2, 0)])

        editor.redo()
        editor.redo()
        self.assertEqual('A', self.grid()[(0, 0)])
        self.assertEqual('B', self.grid()[(1, 0)])

    def test_the_layer_list_shows_the_layers_an_undo_leaves(self):
        editor = self.open_map_editor()
        count = len(self.tilemap.layers)
        editor.layer_menu.new()
        self.assertEqual(count + 1, len(self.tilemap.layers))

        editor.undo()

        self.assertEqual(count, len(self.tilemap.layers))
        self.assertIs(self.tilemap.layers, editor.layer_menu.model._data)
        self.assertEqual(count, editor.layer_menu.model.rowCount())
        self.assertTrue(editor.layer_menu.view.currentIndex().isValid())

    def test_cancel_takes_back_every_stroke(self):
        editor = self.open_map_editor()
        self.stroke(editor, (0, 0), 'A')
        self.stroke(editor, (1, 0), 'B')

        editor.reject()

        self.assertEqual(self.original, dict(self.grid()))

    @patch('app.editor.tilemap_editor.QMessageBox')
    def test_cancel_after_a_kept_stroke_was_undone_and_replaced_goes_back_to_where_it_opened(self, _message_box):
        editor = self.open_map_editor()
        self.stroke(editor, (0, 0), 'A')
        editor.save_current()
        editor.undo()
        self.stroke(editor, (1, 0), 'B')

        editor.reject()

        self.assertEqual(self.original, dict(self.grid()))

    def test_after_ok_each_stroke_is_still_an_undo_step(self):
        editor = self.open_map_editor()
        self.stroke(editor, (0, 0), 'A')
        self.stroke(editor, (1, 0), 'B')
        editor.accept()

        self.history.undo()

        self.assertEqual('A', self.grid()[(0, 0)])
        self.assertEqual(self.original.get((1, 0)), self.grid().get((1, 0)))

    def test_the_tileset_terrain_editor_undoes_each_stroke_and_cancel_takes_them_back(self):
        from app.data.resources.resources import RESOURCES
        from app.editor.tileset_editor import TileSetEditor
        tileset = RESOURCES.tilesets[0]
        original = dict(tileset.terrain_grid)
        editor = TileSetEditor(None, tileset)
        self.addCleanup(editor.deleteLater)
        for coord, terrain_nid in (((0, 0), 'A'), ((1, 0), 'B')):
            tileset.terrain_grid[coord] = terrain_nid
            editor.handle_mouse_release()  # As the stroke's release does

        editor.undo()
        self.assertEqual('A', tileset.terrain_grid[(0, 0)])
        self.assertEqual(original.get((1, 0)), tileset.terrain_grid.get((1, 0)))
        self.assertIsNotNone(tileset.pixmap)  # Loaded again for the view
        editor.redo()
        self.assertEqual('B', tileset.terrain_grid[(1, 0)])

        editor.reject()
        self.assertEqual(original, tileset.terrain_grid)


if __name__ == '__main__':
    unittest.main()
