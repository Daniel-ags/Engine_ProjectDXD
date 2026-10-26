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
from app.editor.file_manager.staging import LOCK_FILE, Staging


def write(path, content: bytes):
    with open(path, 'wb') as fp:
        fp.write(content)

def read(path) -> bytes:
    with open(path, 'rb') as fp:
        return fp.read()

def listing(folder) -> dict:
    """Each file under a folder, with its contents"""
    files = {}
    for dirpath, _, filenames in os.walk(folder):
        for name in filenames:
            path = os.path.join(dirpath, name)
            files[os.path.relpath(path, folder)] = read(path)
    return files

def fingerprint(folder) -> dict:
    """Each file under a folder, with its size and when it was last written"""
    files = {}
    for dirpath, _, filenames in os.walk(folder):
        for name in filenames:
            stat = os.stat(os.path.join(dirpath, name))
            files[os.path.relpath(os.path.join(dirpath, name), folder)] = (stat.st_size, stat.st_mtime_ns)
    return files


class StagingTests(unittest.TestCase):
    """The folder where resource files wait for a project save"""
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.sources = os.path.join(self.tmp, 'sources')
        os.mkdir(self.sources)
        self.staging = self.make_staging()

    def make_staging(self) -> Staging:
        staging = Staging(os.path.join(self.tmp, 'staging'))
        patcher = patch.object(staging, 'fallback_root', lambda: os.path.join(self.tmp, 'fallback'))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(staging.end)
        staging.start(os.path.join(self.tmp, 'my_game.ltproj'))
        return staging

    def source(self, name, content: bytes) -> str:
        path = os.path.join(self.sources, name)
        write(path, content)
        return path

    def test_a_staged_file_keeps_its_name_in_the_projects_session_folder(self):
        staged = self.staging.stage_file(self.source('Eirika.png', b'eirika'))

        self.assertEqual('Eirika.png', os.path.basename(staged))
        self.assertEqual(b'eirika', read(staged))
        session_dir = os.path.join(self.tmp, 'staging', 'my_game', self.staging.session_id)
        self.assertEqual(os.path.normcase(session_dir), os.path.normcase(os.path.dirname(os.path.dirname(staged))))

    def test_a_change_to_the_source_leaves_the_staged_copy_alone(self):
        source = self.source('Eirika.png', b'eirika')
        staged = self.staging.stage_file(source)

        write(source, b'changed')
        restaged = self.staging.stage_file(source)

        self.assertEqual(b'eirika', read(staged))
        self.assertNotEqual(staged, restaged)
        self.assertEqual(b'changed', read(restaged))

    def test_the_same_file_staged_twice_is_one_copy(self):
        source = self.source('Eirika.png', b'eirika')
        self.assertEqual(self.staging.stage_file(source), self.staging.stage_file(source))

    def test_files_staged_together_share_a_folder(self):
        paths = [self.source('convo.png', b'image'), self.source('convo.idx', b'index')]

        version_dir = self.staging.stage_files(paths + [os.path.join(self.sources, 'missing.ttf')])

        self.assertEqual({'convo.png': b'image', 'convo.idx': b'index'}, listing(version_dir))

    def test_a_written_version_is_named_by_its_contents(self):
        def writer(content):
            return lambda path: write(path, content) or True

        first = self.staging.write_file('Eirika.png', writer(b'one'))
        again = self.staging.write_file('Eirika.png', writer(b'one'))
        other = self.staging.write_file('Eirika.png', writer(b'two'))

        self.assertEqual(first, again)
        self.assertNotEqual(first, other)
        self.assertEqual(b'one', read(first))
        self.assertEqual(b'two', read(other))

    def test_a_failed_write_leaves_nothing_behind(self):
        session_dir = os.path.dirname(os.path.dirname(self.staging.stage_file(self.source('a.png', b'a'))))
        before = os.listdir(session_dir)

        with self.assertRaises(OSError):
            self.staging.write_file('Eirika.png', lambda path: False)

        self.assertEqual(before, os.listdir(session_dir))

    def test_ending_removes_the_session_and_its_empty_project_folder(self):
        self.staging.stage_file(self.source('Eirika.png', b'eirika'))

        self.staging.end()

        self.assertEqual([], os.listdir(os.path.join(self.tmp, 'staging')))

    def test_opening_another_project_drops_the_last_ones_files(self):
        staged = self.staging.stage_file(self.source('Eirika.png', b'eirika'))

        self.staging.start(os.path.join(self.tmp, 'other.ltproj'))
        restaged = self.staging.stage_file(self.source('Seth.png', b'seth'))

        self.assertFalse(os.path.exists(staged))
        self.assertIn(os.sep + 'other' + os.sep, restaged)

    def test_a_crashed_sessions_files_go_and_a_running_ones_stay(self):
        running = self.staging.stage_file(self.source('Eirika.png', b'eirika'))
        crashed_dir = os.path.join(self.tmp, 'staging', 'my_game', 'crashed')
        os.makedirs(crashed_dir)
        write(os.path.join(crashed_dir, LOCK_FILE), b'')
        write(os.path.join(crashed_dir, 'Seth.png'), b'seth')

        self.make_staging()  # The next editor to start

        self.assertFalse(os.path.exists(crashed_dir))
        self.assertTrue(os.path.exists(running))

    def test_staging_falls_back_to_the_temp_folder_when_the_main_one_cannot_be_made(self):
        write(os.path.join(self.tmp, 'staging'), b'a file where the folder would go')

        staged = self.staging.stage_file(self.source('Eirika.png', b'eirika'))

        self.assertTrue(os.path.normcase(staged).startswith(os.path.normcase(os.path.join(self.tmp, 'fallback'))))
        self.assertEqual(b'eirika', read(staged))

    def test_staging_before_a_project_is_loaded_fails(self):
        staging = Staging(os.path.join(self.tmp, 'staging'))
        with self.assertRaises(AssertionError):
            staging.stage_file(self.source('Eirika.png', b'eirika'))


class StagingEditorCase(unittest.TestCase):
    """The editor's history and staging on a copy of the test project, with file and
    message dialogs patched"""
    @classmethod
    def setUpClass(cls):
        import sys
        from app.editor.editor_locale import init_locale
        init_locale()
        from PyQt5.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication(sys.argv)
        # Shared, since the tests check that nothing writes into it
        cls.proj_dir = tempfile.mkdtemp()
        cls.proj = os.path.join(cls.proj_dir, 'staging_test.ltproj')
        shutil.copytree('testing_proj.ltproj', cls.proj)

    @classmethod
    def tearDownClass(cls):
        # The tests load a temporary project, which the sprites point into
        RESOURCES.load('testing_proj.ltproj', CURRENT_SERIALIZATION_VERSION)
        DB.load('testing_proj.ltproj', CURRENT_SERIALIZATION_VERSION)
        shutil.rmtree(cls.proj_dir, ignore_errors=True)

    def setUp(self):
        from app.editor.edit_history import HISTORY
        from app.editor.file_manager.staging import STAGING
        from app.editor.settings import MainSettingsController
        logging.disable(logging.CRITICAL)
        self.addCleanup(logging.disable, logging.NOTSET)
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.sources = os.path.join(self.tmp, 'sources')
        os.mkdir(self.sources)
        for patcher in (patch.object(MainSettingsController, 'get_current_project', lambda _: self.proj),
                        patch.object(MainSettingsController, 'get_last_open_path', lambda _: self.sources),
                        patch.object(MainSettingsController, 'set_last_open_path', lambda _, path: None),
                        patch.object(STAGING, 'root', os.path.join(self.tmp, 'staging')),
                        patch.object(STAGING, 'fallback_root', lambda: os.path.join(self.tmp, 'fallback')),
                        # A message box would wait forever for someone to close it
                        patch('PyQt5.QtWidgets.QMessageBox.critical'),
                        patch('PyQt5.QtWidgets.QMessageBox.warning'),
                        patch('PyQt5.QtWidgets.QMessageBox.information')):
            patcher.start()
            self.addCleanup(patcher.stop)
        DB.load(self.proj, CURRENT_SERIALIZATION_VERSION)
        RESOURCES.load(self.proj, CURRENT_SERIALIZATION_VERSION)
        HISTORY.clear()
        STAGING.start(self.proj)
        self.addCleanup(STAGING.end)
        self.staging = STAGING
        self.history = HISTORY
        self.project_files = fingerprint(self.proj)

    def own_project(self):
        """A copy of the project for this test alone to write to, loaded"""
        self.proj = os.path.join(self.tmp, 'staging_test.ltproj')
        shutil.copytree('testing_proj.ltproj', self.proj)
        DB.load(self.proj, CURRENT_SERIALIZATION_VERSION)
        RESOURCES.load(self.proj, CURRENT_SERIALIZATION_VERSION)

    def assertProjectUntouched(self):
        self.assertEqual(self.project_files, fingerprint(self.proj))

    def assertStaged(self, path):
        self.assertTrue(self.staging.is_staged(path), path)
        self.assertTrue(os.path.exists(path), path)

    def image(self, name, width, height, color) -> str:
        from PyQt5.QtGui import QColor, QImage
        image = QImage(width, height, QImage.Format_ARGB32)
        image.fill(QColor(color))
        path = os.path.join(self.sources, name)
        self.assertTrue(image.save(path))
        return path

    def open(self, tab_type, resource_type):
        from app.editor.data_editor import SingleResourceEditor
        dialog = SingleResourceEditor(tab_type, [resource_type])
        self.addCleanup(dialog.stop_history)
        self.addCleanup(dialog.hide)
        return dialog

    def no_project(self):
        from app.editor.settings import MainSettingsController
        return patch.object(MainSettingsController, 'get_current_project', lambda _: None)

    def choose_files(self, *paths):
        return patch('PyQt5.QtWidgets.QFileDialog.getOpenFileNames', return_value=(list(paths), True))

    def choose_file(self, path):
        return patch('PyQt5.QtWidgets.QFileDialog.getOpenFileName', return_value=(path, True))


class EditorStagingTests(StagingEditorCase):
    """Imports and editors that change a file's bytes write into staging, never into
    the project or beside the file the user chose"""
    def test_an_imported_portrait_points_at_its_staged_copy(self):
        from app.editor.portrait_editor import portrait_model
        source = self.image('Lady.png', 160, 112, '#80a080')
        before = read(source)

        with self.choose_files(source):
            portrait, = portrait_model.create_new(None)

        self.assertStaged(portrait.full_path)
        self.assertEqual(before, read(portrait.full_path))
        self.assertProjectUntouched()

    def test_a_gba_portrait_import_converts_in_staging_and_leaves_its_source_alone(self):
        from app.editor.portrait_editor import portrait_model
        source = self.image('Lady.png', 128, 112, '#ff0000')  # Not the colorkey
        before = read(source)

        with self.choose_files(source), patch.object(portrait_model, 'auto_frame_portrait'):
            portrait, = portrait_model.create_new(None)

        self.assertStaged(portrait.full_path)
        self.assertEqual('Lady_lt.png', os.path.basename(portrait.full_path))
        self.assertEqual(before, read(source))
        self.assertEqual(['Lady.png'], os.listdir(self.sources))
        self.assertProjectUntouched()

    def test_colorkeying_a_portrait_writes_a_new_version_that_undo_takes_back(self):
        from app.editor.portrait_editor import portrait_model
        portrait = RESOURCES.portraits.get('Eirika')
        # A portrait whose corner is not the colorkey
        with self.history.change_set('Import'), self.history.modifying([(portrait, RESOURCES.portraits)]):
            portrait.pixmap = None
            portrait.full_path = self.staging.stage_file(self.image('Eirika.png', 160, 112, '#ff0000'))
        red_path = portrait.full_path
        red = read(red_path)

        with self.history.change_set('Colorkey'), self.history.modifying([(portrait, RESOURCES.portraits)]):
            portrait_model.auto_colorkey(portrait)

        self.assertStaged(portrait.full_path)
        self.assertNotEqual(red_path, portrait.full_path)
        self.assertEqual(red, read(red_path))
        self.assertProjectUntouched()
        self.history.undo()
        self.assertEqual(red_path, portrait.full_path)

    def test_graying_a_map_sprite_writes_a_new_version_that_undo_takes_back(self):
        from app.editor.map_sprite_editor.new_map_sprite_tab import NewMapSpriteDatabase
        dialog = self.open(NewMapSpriteDatabase, 'map_sprites')
        map_sprite = RESOURCES.map_sprites[0]
        dialog.tab.on_select(map_sprite.nid)
        stand = map_sprite.stand_full_path

        dialog.tab.right_frame.gray_button_clicked()
        self.history.commit()

        self.assertStaged(map_sprite.stand_full_path)
        self.assertProjectUntouched()
        dialog.undo()
        self.assertEqual(stand, map_sprite.stand_full_path)

    def test_a_gba_map_sprite_imports_without_a_saved_project(self):
        from app.editor.map_sprite_editor import map_sprite_model
        from app.editor.map_sprite_editor.new_map_sprite_tab import NewMapSpriteDatabase
        dialog = self.open(NewMapSpriteDatabase, 'map_sprites')
        stand = self.image('Lady.png', 16, 48, '#000000')
        move = self.image('Lady_move.png', 32, 32 * 15, '#000000')

        with self.no_project(), patch('PyQt5.QtWidgets.QFileDialog.getOpenFileName', side_effect=[(stand, True), (move, True)]), \
                patch.object(map_sprite_model.editor_utilities, 'convert_default_palette_pixmap', return_value=None):
            map_sprite = map_sprite_model.create_new(dialog.tab)

        self.assertEqual('Lady-stand.png', os.path.basename(map_sprite.stand_full_path))
        self.assertStaged(map_sprite.stand_full_path)
        self.assertStaged(map_sprite.move_full_path)
        self.assertProjectUntouched()

    def test_a_movie_background_is_named_by_its_file_and_stages_its_frames_together(self):
        from app.editor.panorama_editor.panorama_tab import PanoramaDatabase
        dialog = self.open(PanoramaDatabase, 'panoramas')
        movie_dir = os.path.join(self.sources, 'take2')  # A digit in the folder
        os.mkdir(movie_dir)
        self.sources = movie_dir
        frames = [self.image('rain%d.png' % idx, 240, 160, '#000000') for idx in range(3)]

        with self.choose_files(frames[0]):
            panorama = dialog.tab.model.create_new_movie()

        self.assertEqual('rain', panorama.nid)
        for path in panorama.get_all_paths():
            self.assertStaged(path)
        self.assertProjectUntouched()

    def test_an_imported_font_stages_its_image_and_index_together(self):
        from app.editor.font_editor.font_tab import FontDatabase
        dialog = self.open(FontDatabase, 'fonts')
        image = os.path.join(self.sources, 'chapter.png')
        shutil.copyfile(os.path.join(self.proj, 'resources', 'fonts', 'chapter.png'), image)
        shutil.copyfile(os.path.join(self.proj, 'resources', 'fonts', 'chapter.idx'), image[:-4] + '.idx')

        with self.choose_file(image):
            font = dialog.tab.left_frame.model.create_new()

        self.assertStaged(font.image_path())
        self.assertStaged(font.index_path())
        self.assertProjectUntouched()

    def test_a_fonts_fallback_ttf_goes_into_a_new_version_beside_its_image(self):
        from app.editor.font_editor.font_tab import FontDatabase
        dialog = self.open(FontDatabase, 'fonts')
        dialog.tab.left_frame.set_current_row(0)
        form = dialog.tab.right_frame
        font = form.current
        file_name = font.file_name
        ttf = os.path.join(self.sources, 'Fallback.ttf')
        write(ttf, b'not really a font')

        with self.choose_file(ttf), patch.object(form, '_reinit_bmp_font'):
            form._browse_ttf()
        self.history.commit()

        self.assertEqual('Fallback.ttf', font.fallback_ttf)
        self.assertStaged(font.ttf_path())
        self.assertStaged(font.image_path())
        self.assertProjectUntouched()
        dialog.undo()
        self.assertEqual(file_name, font.file_name)

    def test_a_mapchip_tileset_imports_without_a_saved_project(self):
        from app.editor.tile_editor.tile_tab import TileSetDatabase
        from app.editor.tile_editor import tile_model
        from PyQt5.QtGui import QPixmap
        dialog = self.open(TileSetDatabase, 'tilesets')
        config = os.path.join(self.sources, 'Forest.mapchip_config')
        write(config, b'')
        pix = QPixmap(16, 16)
        with self.no_project(), self.choose_files(config), self.choose_file(self.image('palette.png', 16, 16, '#000000')), \
                patch.object(tile_model, 'read_mapchip_file', return_value=[1]), \
                patch.object(tile_model, 'read_palette_file', return_value=[1]), \
                patch.object(tile_model, 'draw_tileset_from_mapchip', return_value=pix):
            tileset = dialog.tab.model.create_new()

        self.assertEqual('Forest.png', os.path.basename(tileset.full_path))
        self.assertStaged(tileset.full_path)
        self.assertProjectUntouched()

    def test_each_import_points_at_a_staged_copy(self):
        from app.editor.icon_editor.icon_tab import Icon16Database, MapIconDatabase
        from app.editor.map_animation_editor.map_animation_tab import MapAnimationDatabase
        from app.editor.sound_editor.sound_tab import MusicDatabase, SFXDatabase
        from app.editor.tile_editor.tile_tab import TileSetDatabase
        imports = [
            (Icon16Database, 'icons16', lambda tab: tab.full_model, lambda: self.image('Lady.png', 16, 16, '#000000')),
            (MapIconDatabase, 'map_icons', lambda tab: tab.full_model, lambda: self.image('Lady.png', 16, 16, '#000000')),
            (SFXDatabase, 'sfx', lambda tab: tab.model, lambda: self.sound('Lady.ogg')),
            (MusicDatabase, 'music', lambda tab: tab.model, lambda: self.sound('Lady.ogg')),
            (MapAnimationDatabase, 'animations', lambda tab: tab.left_frame.model, lambda: self.image('Lady.png', 16, 16, '#000000')),
            (TileSetDatabase, 'tilesets', lambda tab: tab.model, lambda: self.image('Lady.png', 16, 16, '#000000')),
        ]
        for tab_type, resource_type, model, source in imports:
            with self.subTest(resource_type):
                dialog = self.open(tab_type, resource_type)
                with self.choose_files(source()):
                    model(dialog.tab).create_new()

                self.assertStaged(getattr(RESOURCES, resource_type)[-1].full_path)
        self.assertProjectUntouched()

    def test_a_music_variant_points_at_a_staged_copy(self):
        from app.editor.sound_editor.sound_dialog import ModifyMusicDialog
        song = RESOURCES.music[0]
        dialog = ModifyMusicDialog(RESOURCES.music, [song], None)
        self.addCleanup(dialog.deleteLater)

        with self.choose_file(self.sound('Lady_intro.ogg')):
            dialog.load_intro_variant()
        with self.choose_file(self.sound('Lady_battle.ogg')):
            dialog.load_battle_variant()

        self.assertStaged(song.intro_full_path)
        self.assertStaged(song.battle_full_path)

    def sound(self, name) -> str:
        path = os.path.join(self.sources, name)
        write(path, b'not really a sound')
        return path

    def test_saving_the_project_copies_a_staged_import_in(self):
        from app.editor.portrait_editor import portrait_model
        self.own_project()
        source = self.image('Lady.png', 160, 112, '#80a080')
        with self.choose_files(source):
            portrait, = portrait_model.create_new(None)
        RESOURCES.portraits.append(portrait)

        RESOURCES.save(self.proj)

        saved = os.path.join(self.proj, 'resources', 'portraits', 'Lady.png')
        self.assertEqual(os.path.normcase(saved), os.path.normcase(portrait.full_path))
        self.assertEqual(read(source), read(saved))


class SaveKeepsUndoableFilesTests(StagingEditorCase):
    """A project save overwrites, and Remove Unused Resources deletes, files that undo
    can still point a resource at"""
    def setUp(self):
        super().setUp()
        from app.editor.file_manager.project_file_backend import ProjectFileBackend
        from app.editor.settings import MainSettingsController
        self.own_project()
        self.history.clear()
        self.preferences = {}
        for patcher in (patch.object(MainSettingsController, 'set_current_project', lambda _, value: None),
                        patch.object(MainSettingsController, 'append_or_bump_project', lambda _, name, path: None),
                        patch.object(MainSettingsController, 'get_preference',
                                     lambda _, pref: self.preferences.get(pref, pref.definition.default_value)),
                        patch.object(ProjectFileBackend, 'display_fatal_errors', lambda _: None)):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.backend = ProjectFileBackend(None, None)
        self.eirika = read(self.portrait_file('Eirika'))

    def portrait_file(self, nid) -> str:
        return os.path.join(self.proj, 'resources', 'portraits', nid + '.png')

    def save(self):
        self.assertTrue(self.backend.save())

    def remove_unused(self):
        self.backend.clean(self.backend.get_unused_files())

    def test_undo_past_a_save_finds_a_replaced_file_as_it_was(self):
        portrait = RESOURCES.portraits.get('Eirika')
        with self.history.change_set('Replace'), self.history.modifying([(portrait, RESOURCES.portraits)]):
            portrait.pixmap = None
            portrait.full_path = self.staging.stage_file(self.image('Eirika.png', 160, 112, '#ff0000'))
        red = read(portrait.full_path)

        self.save()

        self.assertEqual(red, read(self.portrait_file('Eirika')))
        self.history.undo()
        self.assertEqual(self.eirika, read(portrait.full_path))
        self.history.redo()
        self.assertEqual(red, read(portrait.full_path))

    def test_undo_past_remove_unused_finds_a_deleted_resources_file(self):
        portrait = RESOURCES.portraits.get('Eirika')
        RESOURCES.portraits.remove_key('Eirika')
        self.history.commit()

        self.save()
        self.remove_unused()

        self.assertFalse(os.path.exists(self.portrait_file('Eirika')))
        self.history.undo()
        self.assertIs(portrait, RESOURCES.portraits.get('Eirika'))
        self.assertEqual(self.eirika, read(portrait.full_path))

    def test_undo_past_remove_unused_finds_a_renamed_resources_old_file(self):
        portrait = RESOURCES.portraits.get('Eirika')
        self.history.rename(RESOURCES.portraits, portrait, 'Lady')

        self.save()
        self.remove_unused()

        self.assertEqual(self.eirika, read(self.portrait_file('Lady')))
        self.assertFalse(os.path.exists(self.portrait_file('Eirika')))
        self.history.undo()
        self.assertEqual('Eirika', portrait.nid)
        self.assertEqual(self.eirika, read(portrait.full_path))

    def test_two_resources_that_swap_names_save_under_each_others_names(self):
        eirika, seth = RESOURCES.portraits.get('Eirika'), RESOURCES.portraits.get('Seth')
        seth_bytes = read(self.portrait_file('Seth'))
        self.history.rename(RESOURCES.portraits, eirika, 'Swap')
        self.history.rename(RESOURCES.portraits, seth, 'Eirika')
        self.history.rename(RESOURCES.portraits, eirika, 'Seth')

        self.save()

        self.assertEqual(self.eirika, read(self.portrait_file('Seth')))
        self.assertEqual(seth_bytes, read(self.portrait_file('Eirika')))

    def test_a_backup_save_keeps_a_renamed_resources_file(self):
        from app.editor.settings.preference_definitions import Preference
        self.preferences[Preference.SAVE_BACKUP] = True
        portrait = RESOURCES.portraits.get('Eirika')
        self.history.rename(RESOURCES.portraits, portrait, 'Lady')

        self.save()

        self.assertEqual(self.eirika, read(self.portrait_file('Lady')))


if __name__ == '__main__':
    unittest.main()
