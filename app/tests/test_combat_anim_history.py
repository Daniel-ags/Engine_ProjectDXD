import os
from unittest.mock import patch

from app.tests import qt_headless  # noqa: F401 -- before any QApplication

from app.data.database.database import DB
from app.data.resources.resources import RESOURCES
from app.tests.test_staging import StagingEditorCase


class CombatEditorHistoryTests(StagingEditorCase):
    """The combat animation, effect and palette editors record their edits like every
    other resource editor, and write their images into staging"""
    project = 'default.ltproj'

    def setUp(self):
        super().setUp()
        from app.editor.combat_animation_editor.new_combat_animation_tab import get_full_editor
        self.dialog = get_full_editor()
        self.addCleanup(self.dialog.stop_history)
        self.addCleanup(self.dialog.hide)
        self.anim_tab, self.effect_tab, self.palette_tab = self.dialog.tabs
        self.assassin = RESOURCES.combat_anims.get('Assassin')

    def show_anim(self):
        self.dialog.tab_bar.setCurrentWidget(self.anim_tab)
        self.anim_tab.tree_list.select_item('Assassin')
        return self.anim_tab.right_frame

    def show_palette(self, nid):
        self.dialog.tab_bar.setCurrentWidget(self.palette_tab)
        self.palette_tab.tree_list.select_item(nid)
        return self.palette_tab.right_frame

    def click_easel(self, form, coord):
        from PyQt5.QtCore import QEvent, QPointF, Qt
        from PyQt5.QtGui import QMouseEvent
        easel = form.easel_widget
        point = easel.mapFromScene(QPointF((coord[0] + .5) * easel.palette_size, (coord[1] + .5) * easel.palette_size))
        easel.mousePressEvent(QMouseEvent(QEvent.MouseButtonPress, point, Qt.LeftButton, Qt.LeftButton, Qt.NoModifier))

    def add_pose(self, form, nid):
        with patch('PyQt5.QtWidgets.QInputDialog.getItem', return_value=('Custom', True)),                 patch('PyQt5.QtWidgets.QInputDialog.getText', return_value=(nid, True)):
            form.add_new_pose()

    def test_undo_takes_back_an_edit_to_a_combat_animation(self):
        form = self.show_anim()
        form.weapon_box.setValue('Sword')

        self.add_pose(form, 'Taunt')
        self.assertIn('Taunt', self.assassin.weapon_anims.get('Sword').poses)
        self.dialog.undo()

        self.assertNotIn('Taunt', self.assassin.weapon_anims.get('Sword').poses)

    def test_an_undo_keeps_the_weapon_and_pose_shown(self):
        form = self.show_anim()
        weapon_anim = self.assassin.weapon_anims[1]
        pose_nid = weapon_anim.poses[-1].nid
        form.weapon_box.setValue(weapon_anim.nid)
        self.add_pose(form, 'Taunt')
        form.pose_box.setValue(pose_nid)

        self.dialog.undo()

        self.assertNotIn('Taunt', self.assassin.weapon_anims.get(weapon_anim.nid).poses)
        self.assertEqual(weapon_anim.nid, form.weapon_box.currentText())
        self.assertEqual(pose_nid, form.pose_box.currentText())
        self.assertEqual(pose_nid, form.timeline_menu.current_pose.nid)

    def test_ok_writes_nothing_into_the_project(self):
        form = self.show_anim()
        form.weapon_box.setValue('Sword')
        self.add_pose(form, 'Taunt')

        self.dialog.accept()

        self.assertIn('Taunt', self.assassin.weapon_anims.get('Sword').poses)
        self.assertProjectUntouched()

    def test_moving_a_palette_slot_writes_a_new_sheet_that_undo_takes_back(self):
        import app.editor.utilities as editor_utilities
        form = self.show_palette('Assassin0_GenericBlue')
        form.autoselect_frame()
        sheet = self.assassin.weapon_anims[0].full_path
        palette = RESOURCES.combat_palettes.get('Assassin0_GenericBlue')
        used = [coord for coord in editor_utilities.get_coords_used_in_frame(form.current_frame) if coord != (0, 0)]
        coord = used[0]
        new_coord = next(other for other in palette.colors if other not in ((0, 0), coord))
        form.easel_widget.current_coord = coord

        self.click_easel(form, new_coord)

        moved = self.assassin.weapon_anims[0].full_path
        self.assertNotEqual(sheet, moved)
        self.assertStaged(moved)
        self.assertProjectUntouched()
        self.dialog.undo()
        self.assertEqual(sheet, self.assassin.weapon_anims[0].full_path)
        self.dialog.redo()
        self.assertEqual(moved, self.assassin.weapon_anims[0].full_path)

    def test_the_palette_editor_lets_go_of_a_frame_whose_animation_was_deleted(self):
        from PyQt5.QtWidgets import QApplication
        form = self.show_palette('Assassin0_GenericBlue')
        form.autoselect_frame()
        self.assertIsNotNone(form.current_frame)

        with self.history.change_set('Delete Assassin'):
            RESOURCES.combat_anims.remove_key('Assassin')
        QApplication.processEvents()

        self.assertIsNone(form.current_frame)

    def test_renaming_a_sound_renames_it_in_combat_timelines_as_one_undo_step(self):
        from app.editor.sound_editor.sound_dialog import ModifySFXDialog
        def plays(poses, nid):
            return any(command.nid == 'sound' and command.value[0] == nid
                       for pose in poses for command in pose.timeline)
        def assassin_plays(nid):
            return any(plays(weapon_anim.poses, nid) for weapon_anim in RESOURCES.combat_anims.get('Assassin').weapon_anims)
        arrow = RESOURCES.combat_effects.get('Arrow')
        dialog = ModifySFXDialog(RESOURCES.sfx, [RESOURCES.sfx.get('Bow')], None)
        self.addCleanup(dialog.deleteLater)

        dialog.nid_box.edit.setText('Longbow')
        dialog.nid_done_editing()
        effect_dialog = ModifySFXDialog(RESOURCES.sfx, [RESOURCES.sfx.get('Bow Miss')], None)
        self.addCleanup(effect_dialog.deleteLater)
        effect_dialog.nid_box.edit.setText('Longbow Miss')
        effect_dialog.nid_done_editing()

        self.assertTrue(assassin_plays('Longbow'))
        self.assertFalse(assassin_plays('Bow'))
        self.assertTrue(plays(arrow.poses, 'Longbow Miss'))
        self.history.undo()
        self.history.undo()
        self.assertTrue(assassin_plays('Bow'))
        self.assertFalse(assassin_plays('Longbow'))
        self.assertTrue(plays(arrow.poses, 'Bow Miss'))

    def sound_editor(self):
        from app.editor.sound_editor.sound_tab import get_full_editor
        dialog = get_full_editor()
        self.addCleanup(dialog.stop_history)
        music_tab, sfx_tab = dialog.tabs
        return dialog, music_tab, sfx_tab

    def delete_row(self, tab, nid, answer):
        """Deletes the sound named nid from the tab, answering the deletion dialog, and
        returns the titles of the tabs it showed"""
        from app.editor.reference_dialogs import DeletionDialog
        shown = []
        def inform(tabs, parent):
            shown.extend(tab.label for tab in tabs)
            return answer
        row = [sound.nid for sound in tab._data].index(nid)
        index = tab.proxy_model.mapFromSource(tab.model.index(row, 0))
        tab.view.selectRow(index.row())  # The view deletes the rows selected
        with patch.object(DeletionDialog, 'inform', staticmethod(inform)):
            tab.view.delete(index)
        return shown

    def assassin_plays(self, nid) -> bool:
        return any(command.has_sound() and command.value[0] == nid
                   for weapon_anim in RESOURCES.combat_anims.get('Assassin').weapon_anims
                   for pose in weapon_anim.poses for command in pose.timeline)

    def test_deleting_a_sound_removes_what_plays_it_as_one_undo_step(self):
        dialog, _, sfx_tab = self.sound_editor()

        shown = self.delete_row(sfx_tab, 'Bow', True)

        self.assertIn('Combat Animations', shown)
        self.assertNotIn('Bow', RESOURCES.sfx)
        self.assertFalse(self.assassin_plays('Bow'))
        dialog.undo()
        self.assertIn('Bow', RESOURCES.sfx)
        self.assertTrue(self.assassin_plays('Bow'))

    def test_a_sound_deletion_declined_changes_nothing(self):
        _, _, sfx_tab = self.sound_editor()

        self.delete_row(sfx_tab, 'Bow', False)

        self.assertIn('Bow', RESOURCES.sfx)
        self.assertTrue(self.assassin_plays('Bow'))

    def test_deleting_a_song_clears_what_names_it_as_one_undo_step(self):
        from app.data.database import references
        from app.data.resources.resource_types import ResourceType
        dialog, music_tab, _ = self.sound_editor()
        users = len(references.find_referrers(DB, ResourceType.MUSIC, 'Distant Roads'))

        shown = self.delete_row(music_tab, 'Distant Roads', True)

        self.assertTrue(shown)
        self.assertNotIn('Distant Roads', RESOURCES.music)
        self.assertEqual([], references.find_referrers(DB, ResourceType.MUSIC, 'Distant Roads'))
        dialog.undo()
        self.assertIn('Distant Roads', RESOURCES.music)
        self.assertEqual(users, len(references.find_referrers(DB, ResourceType.MUSIC, 'Distant Roads')))

    def test_undo_takes_back_a_palette_color(self):
        form = self.show_palette('Assassin0_GenericBlue')
        palette = RESOURCES.combat_palettes.get('Assassin0_GenericBlue')
        coord, color = next((coord, color) for coord, color in palette.colors.items() if coord != (0, 0) and color != (0, 0, 0))

        self.click_easel(form, coord)  # Paints the painting color, black

        self.assertEqual((0, 0, 0), palette.colors[coord])
        self.dialog.undo()
        self.assertEqual(color, palette.colors[coord])

    def test_renaming_a_palette_and_what_names_it_is_one_undo_step(self):
        self.show_palette('Assassin0_GenericBlue')

        self.assertTrue(self.palette_tab.attempt_change_nid('Assassin0_GenericBlue', 'Blue2'))

        self.assertIn(['GenericBlue', 'Blue2'], self.assassin.palettes)
        self.dialog.undo()
        self.assertIn('Assassin0_GenericBlue', RESOURCES.combat_palettes)
        self.assertIn(['GenericBlue', 'Assassin0_GenericBlue'], self.assassin.palettes)

    def test_a_legacy_weapon_import_points_at_a_staged_sheet(self):
        from app.editor.combat_animation_editor import combat_animation_imports
        script = self.legacy_export('Assassin-Lance', ['GenericBlue'])

        combat_animation_imports.import_from_legacy(self.assassin, script)

        self.assertStaged(self.assassin.weapon_anims.get('Lance').full_path)
        self.assertProjectUntouched()

    def test_a_legacy_effect_import_points_at_a_staged_sheet(self):
        from app.editor.combat_animation_editor import combat_animation_imports
        script = self.legacy_export('Spark', ['Spark'])

        effect = combat_animation_imports.import_effect_from_legacy(script)

        self.assertStaged(effect.full_path)
        self.assertProjectUntouched()

    def legacy_export(self, base, palette_names) -> str:
        """Writes a legacy animation export of one frame, and returns its script"""
        from PyQt5.QtGui import QImage, qRgb
        for palette_name in palette_names:
            image = QImage(2, 1, QImage.Format_RGB32)
            image.setPixel(0, 0, qRgb(40, 80, 200))
            image.setPixel(1, 0, qRgb(16, 16, 16))
            image.save(os.path.join(self.sources, '%s-%s.png' % (base, palette_name)))
        with open(os.path.join(self.sources, '%s-Index.txt' % base), 'w') as fp:
            fp.write('F0;0,0;2,1;0,0\n')
        script = os.path.join(self.sources, '%s-Script.txt' % base)
        with open(script, 'w') as fp:
            fp.write('pose;Stand\nframe;1;F0\n')
        return script

    def test_a_gba_import_stages_its_sheets(self):
        from app.editor.combat_animation_editor import combat_animation_imports
        from app.tests.test_gba_script_import import SCRIPT, critical_backdrop_frame, ordinary_frame, write_frame
        write_frame(os.path.join(self.sources, 'Lance-0.png'), ordinary_frame)
        write_frame(os.path.join(self.sources, 'Lance-1.png'), critical_backdrop_frame)
        script = os.path.join(self.sources, 'Lance.txt')
        with open(script, 'w') as fp:
            fp.write(SCRIPT)

        combat_animation_imports.import_from_gba(self.assassin, script)

        self.assertStaged(self.assassin.weapon_anims.get('Lance').full_path)
        self.assertProjectUntouched()

    def test_an_ltanim_import_stages_its_sheets(self):
        form = self.show_anim()
        with patch('PyQt5.QtWidgets.QFileDialog.getExistingDirectory', return_value=self.sources):
            form.export_anim()
        with patch('PyQt5.QtWidgets.QFileDialog.getExistingDirectory', return_value=os.path.join(self.sources, 'Assassin.ltanim')):
            form.import_anim()

        imported = RESOURCES.combat_anims[-1]
        self.assertNotEqual('Assassin', imported.nid)
        for weapon_anim in imported.weapon_anims:
            self.assertStaged(weapon_anim.full_path)


if __name__ == '__main__':
    import unittest
    unittest.main()
