import logging
import unittest
from unittest.mock import patch

from app.tests import qt_headless  # noqa: F401 -- before any QApplication

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication

from app.data.database import references
from app.data.database.database import DB
from app.data.database.database_types import DatabaseType as DType
from app.data.resources.resources import RESOURCES
from app.data.serialization.versions import CURRENT_SERIALIZATION_VERSION
from app.extensions.custom_gui import DeletionDialog


class HistoryCase(unittest.TestCase):
    """The testing project, loaded fresh with an empty history. Nothing here saves it."""
    @classmethod
    def setUpClass(cls):
        import sys
        from app.editor.editor_locale import init_locale
        init_locale()
        cls.app = QApplication.instance() or QApplication(sys.argv)

    def setUp(self):
        from app.editor.edit_history import HISTORY
        self.history = HISTORY
        logging.disable(logging.CRITICAL)
        self.addCleanup(logging.disable, logging.NOTSET)
        DB.load('testing_proj.ltproj', CURRENT_SERIALIZATION_VERSION)
        RESOURCES.load('testing_proj.ltproj', CURRENT_SERIALIZATION_VERSION)
        HISTORY.clear()
        # A deletion dialog left to show would wait forever for someone to close it
        patcher = patch.object(DeletionDialog, 'exec_', return_value=0)
        patcher.start()
        self.addCleanup(patcher.stop)

    def choose_swap(self, nid):
        """The deletion dialog answers with the swap named nid"""
        def get_swap(tabs, swap_box, parent=None):
            return next(record for record in swap_box.model._data if record.nid == nid), True
        patcher = patch.object(DeletionDialog, 'get_swap', side_effect=get_swap)
        patcher.start()
        self.addCleanup(patcher.stop)

    def open(self, dialog):
        self.addCleanup(dialog.accept)
        return dialog

    def edit(self, dialog, nid, column, value):
        """Types value into the row of the record named nid"""
        row = [record.nid for record in dialog.model._data].index(nid)
        dialog.model.setData(dialog.model.index(row, column), value, Qt.EditRole)

    def undo_once(self):
        self.history.undo()
        self.assertFalse(self.history.can_undo())


class ListDialogTests(HistoryCase):
    """The modal list dialogs, such as the tags, record each edit as one undo step"""
    def tags(self):
        from app.editor.tag_widget import TagDialog
        return self.open(TagDialog.create())

    def test_renaming_a_tag_renames_it_where_it_is_used_as_one_undo_step(self):
        tag = DB.tags.get('Sword')
        self.edit(self.tags(), 'Sword', 0, 'Blade')

        self.assertIn('Blade', DB.classes.get('Eirika_Lord').tags)
        self.assertEqual([], references.find_referrers(DB, DType.TAGS, 'Sword'))

        self.undo_once()
        self.assertIs(tag, DB.tags.get('Sword'))
        self.assertIn('Sword', DB.classes.get('Eirika_Lord').tags)
        self.assertEqual([], references.find_referrers(DB, DType.TAGS, 'Blade'))

    def test_deleting_a_tag_swaps_it_where_it_is_used_as_one_undo_step(self):
        self.choose_swap('Lord')
        tags = DB.classes.get('Eirika_Lord').tags[:]
        dialog = self.tags()

        dialog.model.delete(DB.tags.keys().index('Sword'))

        self.assertNotIn('Sword', DB.tags.keys())
        self.assertIn('Lord', DB.classes.get('Eirika_Lord').tags)
        self.undo_once()
        self.assertIn('Sword', DB.tags.keys())
        self.assertEqual(tags, DB.classes.get('Eirika_Lord').tags)

    def test_an_equation_edit_is_one_undo_step(self):
        from app.editor.equation_widget import EquationDialog
        expression = DB.equations.get('HIT').expression
        self.edit(self.open(EquationDialog.create()), 'HIT', 1, '99')

        self.assertEqual('99', DB.equations.get('HIT').expression)
        self.undo_once()
        self.assertEqual(expression, DB.equations.get('HIT').expression)

    def test_undoing_a_weapon_rank_rename_leaves_nothing_naming_the_new_name(self):
        from app.editor.weapon_editor.weapon_rank import RankDialog
        rank = DB.weapon_ranks.get('E')
        used = len(references.find_referrers(DB, DType.WEAPON_RANKS, 'E'))
        dialog = self.open(RankDialog.create())
        row = DB.weapon_ranks.keys().index('E')
        dialog.model.setData(dialog.model.index(row, 0), 'F', Qt.EditRole)

        self.undo_once()
        self.assertIs(rank, DB.weapon_ranks.get('E'))
        self.assertEqual('E', rank.rank)
        self.assertEqual(used, len(references.find_referrers(DB, DType.WEAPON_RANKS, 'E')))
        self.assertEqual([], references.find_referrers(DB, DType.WEAPON_RANKS, 'F'))

    def test_a_weapon_rank_requirement_and_the_caps_at_it_undo_together(self):
        from app.editor.weapon_editor.weapon_rank import RankDialog
        dialog = self.open(RankDialog.create())
        row = DB.weapon_ranks.keys().index('S')
        dialog.model.setData(dialog.model.index(row, 1), 300, Qt.EditRole)
        self.assertEqual(300, DB.classes.get('Eirika_Lord').wexp_gain['Sword'].cap)

        self.undo_once()
        self.assertEqual(251, DB.weapon_ranks.get('S').requirement)
        self.assertEqual(251, DB.classes.get('Eirika_Lord').wexp_gain['Sword'].cap)

    def test_renaming_a_support_rank_renames_it_in_affinities_as_one_undo_step(self):
        from app.editor.support_editor.support_ranks import SupportRankDialog
        self.edit(self.open(SupportRankDialog.create()), 'C', 0, 'Low')

        self.assertIn('Low', [bonus.support_rank for bonus in DB.affinities.get('Fire').bonus])
        self.undo_once()
        self.assertEqual(['C', 'B', 'A'], [bonus.support_rank for bonus in DB.affinities.get('Fire').bonus])
        self.assertEqual([], references.find_referrers(DB, DType.SUPPORT_RANKS, 'Low'))

    def test_a_translation_edit_is_one_undo_step(self):
        from app.editor.translation_widget import TranslationDialog
        text = DB.translations.get('Unit_desc').text
        self.edit(self.open(TranslationDialog.create()), 'Unit_desc', 1, 'Units')

        self.assertEqual('Units', DB.translations.get('Unit_desc').text)
        self.undo_once()
        self.assertEqual(text, DB.translations.get('Unit_desc').text)

    def test_a_game_var_slot_added_then_renamed_undoes_a_step_at_a_time(self):
        from app.editor.game_var_slot_widget import GameVarSlotDialog
        dialog = self.open(GameVarSlotDialog.create())
        dialog.model.append()
        added = DB.game_var_slots[-1]
        self.edit(dialog, added.nid, 0, 'Gold')
        self.assertIs(added, DB.game_var_slots.get('Gold'))

        self.history.undo()
        self.assertIsNone(DB.game_var_slots.get('Gold'))
        self.assertIn(added, list(DB.game_var_slots))
        self.history.undo()
        self.assertNotIn(added, list(DB.game_var_slots))


class MovementCostTests(HistoryCase):
    """The movement cost grid records each edit, and renames and deletes its
    movement types where they are named"""
    def grid(self):
        from app.editor.mcost_dialog import McostDialog
        return self.open(McostDialog())

    def answer(self, text):
        patcher = patch('app.editor.mcost_dialog.QInputDialog.getText', return_value=(text, True))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_a_movement_cost_edit_is_one_undo_step(self):
        before = DB.mcost.save()
        dialog = self.grid()
        dialog.model.setData(dialog.model.index(0, 0), '5', Qt.EditRole)

        self.assertEqual(5, DB.mcost.get((0, 0)))
        self.undo_once()
        self.assertEqual(before, DB.mcost.save())

    def test_renaming_a_movement_type_renames_it_for_classes_as_one_undo_step(self):
        self.answer('Walkers')
        dialog = self.grid()

        dialog.view.horizontalHeader().rename(DB.mcost.unit_types.index('Light Foot'))

        self.assertIn('Walkers', DB.mcost.unit_types)
        self.assertEqual('Walkers', DB.classes.get('Citizen').movement_group)
        self.undo_once()
        self.assertIn('Light Foot', DB.mcost.unit_types)
        self.assertEqual('Light Foot', DB.classes.get('Citizen').movement_group)

    def test_deleting_a_terrain_type_swaps_it_for_terrain_as_one_undo_step(self):
        self.choose_swap('Cliff')
        before = DB.mcost.save()
        dialog = self.grid()

        dialog.view.verticalHeader().delete(DB.mcost.terrain_types.index('Fence'))

        self.assertNotIn('Fence', DB.mcost.terrain_types)
        self.assertEqual('Cliff', DB.terrain.get('0').mtype)
        self.undo_once()
        self.assertEqual(before, DB.mcost.save())
        self.assertEqual('Fence', DB.terrain.get('0').mtype)

    def test_an_open_class_window_shows_a_movement_type_renamed_in_the_grid(self):
        from app.editor.class_editor.new_class_tab import NewClassDatabase
        from app.editor.data_editor import SingleDatabaseEditor
        window = SingleDatabaseEditor(NewClassDatabase)
        self.addCleanup(window.close)
        window.show()
        window.tab.tree_list.select_item('Citizen')
        self.answer('Walkers')

        self.grid().view.horizontalHeader().rename(DB.mcost.unit_types.index('Light Foot'))
        QApplication.processEvents()

        box = window.tab.right_frame.movement_box.edit
        self.assertEqual('Walkers', box.currentText())
        self.assertIn('Walkers', [box.itemText(i) for i in range(box.count())])


if __name__ == '__main__':
    unittest.main()
