import json
import logging
import os
import shutil
import tempfile
import unittest
from unittest.mock import patch

from app.tests import qt_headless  # noqa: F401 -- before any QApplication

from app.data.database.database import DB
from app.data.resources.resources import RESOURCES
from app.data.serialization.versions import CURRENT_SERIALIZATION_VERSION


class ResourceHistoryTests(unittest.TestCase):
    """Resources are recorded like the database, and reach the project when it is saved"""
    @classmethod
    def setUpClass(cls):
        import sys
        from app.editor.editor_locale import init_locale
        init_locale()
        from PyQt5.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication(sys.argv)

    @classmethod
    def tearDownClass(cls):
        # A test that loads a temporary project leaves the sprites pointing into it
        RESOURCES.load('testing_proj.ltproj', CURRENT_SERIALIZATION_VERSION)
        DB.load('testing_proj.ltproj', CURRENT_SERIALIZATION_VERSION)

    def setUp(self):
        from app.editor.edit_history import HISTORY
        from app.editor.settings import MainSettingsController
        logging.disable(logging.CRITICAL)
        self.addCleanup(logging.disable, logging.NOTSET)
        self.proj = None
        patcher = patch.object(MainSettingsController, 'get_current_project', lambda _: self.proj)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.load('testing_proj.ltproj')
        self.history = HISTORY

    def load(self, proj):
        from app.editor.edit_history import HISTORY
        DB.load(proj, CURRENT_SERIALIZATION_VERSION)
        RESOURCES.load(proj, CURRENT_SERIALIZATION_VERSION)
        HISTORY.clear()

    def copy_project(self):
        """A copy of testing_proj to write to, loaded and current"""
        tmp_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp_dir, ignore_errors=True)
        self.proj = os.path.join(tmp_dir, 'resource_history.ltproj')
        shutil.copytree('testing_proj.ltproj', self.proj)
        self.load(self.proj)
        return tmp_dir

    def open(self, tab_type, resource_type):
        from app.editor.data_editor import SingleResourceEditor
        dialog = SingleResourceEditor(tab_type, [resource_type])
        self.addCleanup(dialog.stop_history)
        self.addCleanup(dialog.hide)
        return dialog

    def portraits(self):
        from app.editor.portrait_editor.new_portrait_tab import NewPortraitDatabase
        return self.open(NewPortraitDatabase, 'portraits')

    def test_a_portrait_rename_and_its_cascade_undo_as_one_step(self):
        dialog = self.portraits()
        portrait = RESOURCES.portraits.get('Eirika')
        full_path = portrait.full_path

        dialog.tab.rename('Eirika', 'Lady')

        self.assertIs(portrait, RESOURCES.portraits.get('Lady'))
        self.assertEqual('Lady', DB.units.get('Eirika').portrait_nid)
        self.assertEqual(full_path, portrait.full_path)  # Saving copies it in under its new name
        self.assertFalse(os.path.exists(os.path.join(os.path.dirname(full_path), 'Lady.png')))

        dialog.undo()

        self.assertIs(portrait, RESOURCES.portraits.get('Eirika'))
        self.assertEqual('Eirika', DB.units.get('Eirika').portrait_nid)
        self.assertEqual(full_path, portrait.full_path)

    def test_a_deleted_portrait_comes_back_with_its_file_on_undo(self):
        from app.extensions.custom_gui import DeletionDialog
        dialog = self.portraits()
        portrait = RESOURCES.portraits.get('Moulder')
        full_path = portrait.full_path
        with patch.object(DeletionDialog, 'inform', return_value=True), \
                patch.object(DeletionDialog, 'get_swap', return_value=(RESOURCES.portraits.get('Seth'), True)):
            self.assertTrue(dialog.tab.delete_from_db('Moulder'))
        self.assertNotIn('Moulder', RESOURCES.portraits.keys())

        dialog.undo()

        self.assertIs(portrait, RESOURCES.portraits.get('Moulder'))
        self.assertEqual(full_path, portrait.full_path)

    def test_undo_takes_back_an_import_without_reloading_the_resources(self):
        from app.data.resources.portraits import PortraitPrefab
        dialog = self.portraits()
        imported = PortraitPrefab('Imported', RESOURCES.portraits.get('Seth').full_path)
        RESOURCES.portraits.append(imported)  # As importing a file does
        self.history.commit()

        with patch.object(RESOURCES, 'load') as load:
            dialog.undo()

        self.assertNotIn('Imported', RESOURCES.portraits.keys())
        load.assert_not_called()

    def test_ok_writes_nothing_to_the_project(self):
        self.copy_project()
        manifest = os.path.join(self.proj, 'resources', 'portraits', 'portraits.json')
        with open(manifest) as fp:
            before = json.load(fp)
        dialog = self.portraits()
        dialog.tab.rename('Eirika', 'Lady')

        dialog.accept()

        with open(manifest) as fp:
            self.assertEqual(before, json.load(fp))
        self.assertFalse(os.path.exists(os.path.join(self.proj, 'resources', 'portraits', 'Lady.png')))

    def test_saving_the_project_is_not_recorded_and_an_earlier_edit_still_undoes(self):
        self.copy_project()
        dialog = self.portraits()
        portrait = RESOURCES.portraits.get('Eirika')
        full_path = portrait.full_path
        dialog.tab.rename('Eirika', 'Lady')
        dialog.accept()
        steps = len(self.history._undo)

        # As the project's save does
        self.history.commit()
        RESOURCES.save(self.proj)
        self.history.rebaseline()
        self.history.commit()

        self.assertEqual(steps, len(self.history._undo))
        self.assertTrue(os.path.exists(portrait.full_path))
        self.assertEqual('Lady.png', os.path.basename(portrait.full_path))
        self.history.undo()
        self.assertEqual('Eirika', portrait.nid)
        self.assertEqual(full_path, portrait.full_path)
        self.assertTrue(os.path.exists(portrait.full_path))

    def test_the_undo_key_steps_back_in_every_recorded_resource_editor(self):
        import sys
        from PyQt5.QtCore import Qt
        from PyQt5.QtTest import QTest
        from app.editor.data_editor import SingleResourceEditor
        from app.editor.font_editor.font_tab import FontDatabase
        from app.editor.icon_editor.icon_tab import Icon16Database, Icon32Database, Icon80Database, MapIconDatabase
        from app.editor.map_animation_editor.map_animation_tab import MapAnimationDatabase
        from app.editor.map_sprite_editor.new_map_sprite_tab import NewMapSpriteDatabase
        from app.editor.panorama_editor.panorama_tab import PanoramaDatabase
        from app.editor.portrait_editor.new_portrait_tab import NewPortraitDatabase
        from app.editor.sound_editor.sound_tab import MusicDatabase, SFXDatabase
        from app.editor.tile_editor.tile_tab import TileMapDatabase, TileSetDatabase
        editors = [
            (NewPortraitDatabase, 'portraits'), (NewMapSpriteDatabase, 'map_sprites'),
            (Icon16Database, 'icons16'), (Icon32Database, 'icons32'), (Icon80Database, 'icons80'),
            (MapIconDatabase, 'map_icons'), (PanoramaDatabase, 'panoramas'), (SFXDatabase, 'sfx'),
            (MusicDatabase, 'music'), (FontDatabase, 'fonts'), (MapAnimationDatabase, 'animations'),
            (TileSetDatabase, 'tilesets'), (TileMapDatabase, 'tilemaps'),
        ]
        # An error in the key's event filter would otherwise end the whole process
        errors = []
        excepthook = patch.object(sys, 'excepthook', lambda *exc_info: errors.append(exc_info[1]))
        excepthook.start()
        self.addCleanup(excepthook.stop)
        for tab_type, resource_type in editors:
            with self.subTest(resource_type), patch.object(SingleResourceEditor, 'undo') as undo:
                errors.clear()
                dialog = self.open(tab_type, resource_type)
                dialog.show()
                dialog.activateWindow()
                self.app.processEvents()

                QTest.keyClick(dialog.tab, Qt.Key_Z, Qt.ControlModifier)

                self.assertEqual([], errors)
                undo.assert_called_once()
                dialog.stop_history()
                dialog.hide()

    def test_the_sound_player_stops_ticking_once_its_window_is_deleted(self):
        import sys
        import time
        from PyQt5.QtCore import QEvent, QCoreApplication
        from app.editor.data_editor import SingleResourceEditor
        from app.editor.sound_editor.sound_tab import SFXDatabase
        self.assertTrue(len(RESOURCES.sfx) > 0)
        errors = []
        excepthook = patch.object(sys, 'excepthook', lambda *exc_info: errors.append(exc_info[1]))
        excepthook.start()
        self.addCleanup(excepthook.stop)
        dialog = SingleResourceEditor(SFXDatabase, ['sfx'])
        dialog.tab.view.selectRow(0)
        self.assertIsNotNone(dialog.tab.sound_player_widget.current_track_name)

        dialog.stop_history()
        dialog.close()
        dialog.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        # Longer than the player's 100 ms tick
        end = time.time() + 0.3
        while time.time() < end:
            self.app.processEvents()

        self.assertEqual([], errors)

    def test_a_font_field_undoes(self):
        # A font is a slots dataclass, which keeps its fields outside __dict__
        from app.editor.font_editor.font_tab import FontDatabase
        dialog = self.open(FontDatabase, 'fonts')
        dialog.tab.left_frame.set_current_row(0)
        font = dialog.tab.right_frame.current
        color, file_name = font.default_color, font.file_name
        font.default_color = 'not a color'
        self.history.commit(origin=dialog.tab)

        dialog.undo()

        self.assertEqual(color, font.default_color)
        self.assertEqual(file_name, font.file_name)

    def test_undo_points_a_map_sprite_back_at_both_its_files(self):
        map_sprite = RESOURCES.map_sprites[0]
        stand, move = map_sprite.stand_full_path, map_sprite.move_full_path
        with self.history.change_set('Move'), self.history.modifying([(map_sprite, RESOURCES.map_sprites)]):
            map_sprite.set_full_path(os.path.join('elsewhere', 'sprite.png'))

        self.history.undo()

        self.assertEqual((stand, move), (map_sprite.stand_full_path, map_sprite.move_full_path))

    def test_a_tileset_rename_takes_its_tilemaps_with_it_and_undoes_with_them(self):
        from PyQt5.QtCore import Qt
        from app.editor.tile_editor.tile_tab import TileSetDatabase
        check = patch('app.editor.edit_history.CHECK_UNRECORDED', True)
        check.start()
        self.addCleanup(check.stop)
        self.history.clear()  # The check starts from the resources as they are now
        dialog = self.open(TileSetDatabase, 'tilesets')
        model = dialog.tab.model
        tilemap = RESOURCES.tilemaps.get('Prologue')

        def tileset_nids():
            return tilemap.tilesets[:], {sprite.tileset_nid for layer in tilemap.layers
                                         for sprite in layer.sprite_grid.values()}

        before = tileset_nids()
        with patch.object(logging, 'warning') as warning:
            model.setData(model.index(RESOURCES.tilesets.index('Prologue')), 'Intro', Qt.EditRole)
            self.assertEqual((['Intro'], {'Intro'}), tileset_nids())
            dialog.undo()

        self.assertEqual(before, tileset_nids())
        self.assertIn('Prologue', RESOURCES.tilesets.keys())
        self.assertEqual([], [c for c in warning.call_args_list if 'LT_EDITOR_CHECK' in c.args[0]])

    def test_autosave_writes_the_resources_as_they_are_in_memory_and_leaves_them_where_they_point(self):
        tmp_dir = self.copy_project()
        portrait = RESOURCES.portraits.get('Eirika')
        full_path = portrait.full_path
        dialog = self.portraits()
        dialog.tab.rename('Eirika', 'Lady')
        dialog.accept()
        autosave_dir = os.path.join(tmp_dir, 'autosave.ltproj')

        RESOURCES.autosave(self.proj, autosave_dir)

        self.assertTrue(os.path.exists(os.path.join(autosave_dir, 'resources', 'portraits', 'Lady.png')))
        with open(os.path.join(autosave_dir, 'resources', 'portraits', 'portraits.json')) as fp:
            self.assertIn('Lady', [entry['nid'] for entry in json.load(fp)])
        self.assertEqual(full_path, portrait.full_path)


if __name__ == '__main__':
    unittest.main()
