from app.tests import qt_headless  # noqa: F401 -- before any QApplication

from PyQt5.QtWidgets import QApplication

from app.data.database.database import DB
from app.data.resources.resources import RESOURCES
from app.tests.test_staging import StagingEditorCase


class ResourcePickerTests(StagingEditorCase):
    """A form that lists resources lists them again when another editor changes them"""
    def add_in_another_editor(self, data, record):
        with self.history.change_set('Import %s' % record.nid):
            data.append(record)
        QApplication.processEvents()  # Open dialogs show the change once the event that made it is done

    def items(self, combo_box) -> list:
        return [combo_box.itemText(idx) for idx in range(combo_box.count())]

    def test_the_credit_panorama_box_lists_a_panorama_added_while_it_is_open(self):
        from app.data.resources.panoramas import Panorama
        from app.data.resources.resource_types import ResourceType
        from app.editor.credit_editor.new_credit_tab import NewCreditDatabase
        from app.editor.data_editor import SingleDatabaseEditor
        dialog = SingleDatabaseEditor(NewCreditDatabase)
        self.addCleanup(dialog.stop_history)
        form = dialog.tab.right_frame
        dialog.tab.tree_list.select_item(DB.credit[0].nid)
        form.type_box.edit.setCurrentIndex(form.CREDIT_TYPES.index(ResourceType.PANORAMAS))
        panorama_box = form.desc_box.currentWidget().panorama_box.edit

        self.add_in_another_editor(RESOURCES.panoramas, Panorama('Sky', 'Sky.png', 1))

        self.assertIn('Sky', self.items(panorama_box))

    def test_the_map_animation_preview_lists_a_map_sprite_added_while_it_is_open(self):
        from app.data.resources.map_sprites import MapSprite
        from app.editor.map_animation_editor.map_animation_tab import MapAnimationDatabase
        dialog = self.open(MapAnimationDatabase, 'animations')
        unit_box = dialog.tab.right_frame.preview_box.edit.unit_box
        chosen = unit_box.currentText()

        self.add_in_another_editor(RESOURCES.map_sprites, MapSprite('Lady', 'Lady-stand.png', 'Lady-move.png'))

        self.assertIn('Lady', self.items(unit_box))
        self.assertEqual(chosen, unit_box.currentText())


if __name__ == '__main__':
    import unittest
    unittest.main()
