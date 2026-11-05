import logging
import unittest

from app.tests import qt_headless  # noqa: F401 -- before any QApplication

from app.data.database.database import DB
from app.data.resources.resources import RESOURCES
from app.data.serialization.versions import CURRENT_SERIALIZATION_VERSION


class MapSpriteIconTests(unittest.TestCase):
    """Recolored map sprite icons are kept, and a kept icon is always the one the
    sprite, the frame and the team's palette make now"""
    @classmethod
    def setUpClass(cls):
        import sys
        from PyQt5.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication(sys.argv)

    def setUp(self):
        from app.editor.map_sprite_editor import map_sprite_model
        logging.disable(logging.CRITICAL)
        self.addCleanup(logging.disable, logging.NOTSET)
        DB.load('testing_proj.ltproj', CURRENT_SERIALIZATION_VERSION)
        RESOURCES.load('testing_proj.ltproj', CURRENT_SERIALIZATION_VERSION)
        self.model = map_sprite_model
        self.sprite = RESOURCES.map_sprites.get('Archer')
        self.team = DB.teams.get('enemy')

    def icon(self, num=0, active=False):
        return self.model.get_map_sprite_icon(self.sprite.nid, num, active, self.team.nid)

    def made_now(self, num=0, active=False):
        """The icon made from scratch, as if nothing were kept"""
        self.model.RECOLORED_ICONS.clear()
        return self.icon(num, active).toImage()

    def test_same_icon_is_kept(self):
        self.assertIs(self.icon(), self.icon())
        self.assertIsNot(self.icon(0), self.icon(1))
        self.assertIsNot(self.icon(active=False), self.icon(active=True))

    def test_palette_recolored_in_place(self):
        from app.editor.edit_history import HISTORY
        HISTORY.clear()
        before = self.icon().toImage()
        palette = RESOURCES.combat_palettes.get(self.team.map_sprite_palette)
        coord = next(coord for coord, color in palette.colors.items() if color != (0, 0, 0))
        # As the palette editor recolors it
        with HISTORY.modifying([(palette, RESOURCES.combat_palettes)]):
            palette.colors[coord] = (0, 0, 0)
        after = self.icon().toImage()
        self.assertNotEqual(before, after)
        self.assertEqual(after, self.made_now())
        HISTORY.undo()
        self.assertEqual(before, self.icon().toImage())

    def test_team_given_another_palette(self):
        before = self.icon().toImage()
        self.team.map_sprite_palette = 'map_sprite_green'
        after = self.icon().toImage()
        self.assertNotEqual(before, after)
        self.assertEqual(after, self.made_now())

    def test_new_sprite_sheet(self):
        from PyQt5.QtGui import QColor
        before = self.icon().toImage()
        sheet = self.sprite.standing_pixmap.copy()
        sheet.fill(QColor(0, 0, 0))
        self.sprite.standing_pixmap = sheet
        after = self.icon().toImage()
        self.assertNotEqual(before, after)
        self.assertEqual(after, self.made_now())


class ListIconTests(unittest.TestCase):
    """Icons cut from icon sheets and portraits are kept, and a kept one is always
    the one the sheet and the record make now. A list's folder and empty icons are
    made once without one folder's contents showing in the next."""
    @classmethod
    def setUpClass(cls):
        import sys
        from PyQt5.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication(sys.argv)

    def setUp(self):
        logging.disable(logging.CRITICAL)
        self.addCleanup(logging.disable, logging.NOTSET)
        DB.load('testing_proj.ltproj', CURRENT_SERIALIZATION_VERSION)
        RESOURCES.load('testing_proj.ltproj', CURRENT_SERIALIZATION_VERSION)
        self.item = next(item for item in DB.items if RESOURCES.icons16.get(item.icon_nid))

    def made_now(self, make):
        """The icon made from scratch, as if nothing were kept"""
        from app.editor import utilities as editor_utilities
        editor_utilities.ICON_CUTS.clear()
        return make().toImage()

    def test_same_icon_is_kept(self):
        from app.editor.item_editor import item_model
        self.assertIs(item_model.get_pixmap(self.item), item_model.get_pixmap(self.item))

    def test_item_pointed_at_another_icon(self):
        from app.editor.item_editor import item_model
        before = item_model.get_pixmap(self.item).toImage()
        x, y = self.item.icon_index
        self.item.icon_index = (x + 1, y)
        after = item_model.get_pixmap(self.item).toImage()
        self.assertNotEqual(before, after)
        self.assertEqual(after, self.made_now(lambda: item_model.get_pixmap(self.item)))

    def test_new_icon_sheet(self):
        from PyQt5.QtGui import QColor
        from app.editor.item_editor import item_model
        before = item_model.get_pixmap(self.item).toImage()
        sheet = RESOURCES.icons16.get(self.item.icon_nid)
        new_pixmap = sheet.pixmap.copy()
        new_pixmap.fill(QColor(0, 0, 0))
        sheet.pixmap = new_pixmap
        after = item_model.get_pixmap(self.item).toImage()
        self.assertNotEqual(before, after)
        self.assertEqual(after, self.made_now(lambda: item_model.get_pixmap(self.item)))

    def test_new_portrait(self):
        from PyQt5.QtGui import QColor
        from app.editor.portrait_editor import portrait_model
        portrait = RESOURCES.portraits[0]
        before = portrait_model.get_chibi(portrait.nid).toImage()
        new_pixmap = portrait.pixmap.copy()
        new_pixmap.fill(QColor(0, 0, 0))
        portrait.pixmap = new_pixmap
        after = portrait_model.get_chibi(portrait.nid).toImage()
        self.assertNotEqual(before, after)
        self.assertEqual(after, self.made_now(lambda: portrait_model.get_chibi(portrait.nid)))

    def test_folder_contents_stay_in_their_folder(self):
        from PyQt5.QtCore import QSize
        from PyQt5.QtGui import QIcon
        from app.editor.item_editor import item_model
        from app.editor.lib.components.nested_list import create_folder_icon
        empty = create_folder_icon(None, 32).pixmap(QSize(32, 32)).toImage()
        holding = create_folder_icon(QIcon(item_model.get_pixmap(self.item)), 32).pixmap(QSize(32, 32)).toImage()
        self.assertNotEqual(empty, holding)
        self.assertEqual(empty, create_folder_icon(None, 32).pixmap(QSize(32, 32)).toImage())


if __name__ == '__main__':
    unittest.main()
