import logging
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.tests import qt_headless  # noqa: F401 -- before any QApplication

from app.data.database.database import DB
from app.data.resources.resources import RESOURCES
from app.data.serialization.versions import CURRENT_SERIALIZATION_VERSION


class FormRefreshTests(unittest.TestCase):
    """A form's choices from other catalogs are the catalogs as they are when the tab resets"""
    @classmethod
    def setUpClass(cls):
        import sys
        from app.editor.editor_locale import init_locale
        init_locale()
        from PyQt5.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication(sys.argv)

    def setUp(self):
        from app.editor.edit_history import HISTORY
        logging.disable(logging.CRITICAL)
        self.addCleanup(logging.disable, logging.NOTSET)
        DB.load('testing_proj.ltproj', CURRENT_SERIALIZATION_VERSION)
        RESOURCES.load('testing_proj.ltproj', CURRENT_SERIALIZATION_VERSION)
        HISTORY.clear()

    def open(self, tab_type, parent=None):
        from app.editor.data_editor import SingleDatabaseEditor
        dialog = SingleDatabaseEditor(tab_type, parent)
        self.addCleanup(dialog.stop_history)
        self.addCleanup(dialog.hide)
        return dialog.tab

    def choices(self, combo):
        return [combo.itemText(i) for i in range(combo.count())]

    def show_after(self, tab, first, second):
        """Shows first, then second, in the tab's form"""
        tab.on_select(first.nid)
        tab.on_select(second.nid)

    def test_showing_a_unit_writes_nothing_to_it(self):
        from app.editor.edit_history import saved
        from app.editor.unit_editor.new_unit_tab import NewUnitDatabase
        tags = list(DB.tags.keys())
        first, second = DB.units[0], DB.units[1]
        first.tags, first.variant, first.affinity = tags[:1], 'Variant', DB.affinities[0].nid
        # In the reverse of the tags' own order, with one no tag has
        second.tags, second.variant, second.affinity = tags[1::-1] + ['No_Such_Tag'], None, None
        before = saved(second)
        tab = self.open(NewUnitDatabase)

        self.show_after(tab, first, second)

        self.assertEqual(before, saved(second))

    def test_showing_a_class_writes_nothing_to_it(self):
        from app.editor.edit_history import saved
        from app.editor.class_editor.new_class_tab import NewClassDatabase
        tags = list(DB.tags.keys())
        first, second = DB.classes[0], DB.classes[1]
        first.tags = tags[:1]
        second.tags = tags[1::-1] + ['No_Such_Tag']
        before = saved(second)
        tab = self.open(NewClassDatabase)

        self.show_after(tab, first, second)

        self.assertEqual(before, saved(second))

    def test_showing_a_portrait_whose_file_is_missing_writes_nothing_to_it(self):
        from app.data.resources.portraits import PortraitPrefab
        from app.editor.data_editor import SingleResourceEditor
        from app.editor.edit_history import saved
        from app.editor.portrait_editor.new_portrait_tab import NewPortraitDatabase
        missing = PortraitPrefab('Missing', 'no_such_folder/Missing.png')
        missing.face_size = (96, 80)
        RESOURCES.portraits.append(missing)
        before = saved(missing)
        dialog = SingleResourceEditor(NewPortraitDatabase, ['portraits'])
        self.addCleanup(dialog.stop_history)
        self.addCleanup(dialog.hide)

        dialog.tab.on_select('Missing')

        self.assertEqual(before, saved(missing))

    def test_ai_unit_specification_lists_tags_and_names_as_they_are(self):
        from app.editor.ai_editor.ai_properties import UnitSpecification
        from app.editor.ai_editor.ai_tab import AIDatabase
        from app.data.database.tags import Tag
        tab = self.open(AIDatabase)
        tab.left_frame.set_current_row(DB.ai.index('Attack'))  # Attacks an enemy unit
        spec = tab.right_frame.behaviour_boxes[0].target_spec.currentWidget()
        self.assertIsInstance(spec, UnitSpecification)
        DB.tags.append(Tag('Brand_New_Tag'))
        DB.units.get('Seth').name = 'Sir Seth'

        tab.reset()

        self.assertIn('Brand_New_Tag', self.choices(spec.tag_box))
        self.assertIn('Sir Seth', self.choices(spec.name_box))

    def test_terrain_status_lists_skills_as_they_are_and_keeps_the_terrains_own(self):
        from app.editor.terrain_editor.terrain_tab import TerrainDatabase
        tab = self.open(TerrainDatabase)
        terrain = tab.right_frame.current
        status = DB.skills[0].nid
        terrain.status = status
        gone = DB.skills[1].nid
        DB.skills.remove_key(gone)

        tab.reset()

        status_box = tab.right_frame.status_box.edit
        self.assertNotIn(gone, self.choices(status_box))
        self.assertEqual(status, status_box.currentText())
        self.assertEqual(status, terrain.status)

    def test_event_level_boxes_list_levels_as_they_are(self):
        from PyQt5.QtWidgets import QWidget
        from app.editor.event_editor.event_tab import EventDatabase
        from app.editor.settings import MainSettingsController
        # The event editor reaches back to the main editor for the selected level
        main_editor = QWidget()
        self.addCleanup(main_editor.deleteLater)
        main_editor.app_state_manager = SimpleNamespace(state=SimpleNamespace(selected_level=DB.levels[0].nid))
        with patch('app.editor.event_editor.event_properties.MainSettingsController',
                   lambda: MainSettingsController('lt_maker_tests', 'editor_form_refresh')):
            tab = self.open(EventDatabase, main_editor)
        filter_box = tab.left_frame.level_filter_box.edit
        filter_box.setValue('All')  # So the form shows an event
        from app.data.database.levels import LevelPrefab
        DB.levels.append(LevelPrefab('New_Level', 'New Level'))

        tab.reset()

        self.assertIn('New_Level', self.choices(filter_box))
        self.assertIn('New_Level', self.choices(tab.right_frame.level_nid_box.edit))
        self.assertEqual('All', filter_box.currentText())

    def test_event_level_filter_on_a_level_that_is_gone_shows_all(self):
        from PyQt5.QtWidgets import QWidget
        from app.editor.event_editor.event_tab import EventDatabase
        from app.editor.settings import MainSettingsController
        main_editor = QWidget()
        self.addCleanup(main_editor.deleteLater)
        main_editor.app_state_manager = SimpleNamespace(state=SimpleNamespace(selected_level=DB.levels[0].nid))
        with patch('app.editor.event_editor.event_properties.MainSettingsController',
                   lambda: MainSettingsController('lt_maker_tests', 'editor_form_refresh')):
            tab = self.open(EventDatabase, main_editor)
        filter_box = tab.left_frame.level_filter_box.edit
        level_nid = DB.levels[-1].nid
        filter_box.setValue(level_nid)
        DB.levels.remove_key(level_nid)

        tab.reset()

        self.assertEqual('All', filter_box.currentText())
        self.assertNotIn(level_nid, self.choices(filter_box))

    def event_editor(self):
        """The event editor on its first event, with the level filter on All"""
        from PyQt5.QtWidgets import QWidget
        from app.editor.event_editor.event_tab import EventDatabase
        from app.editor.settings import MainSettingsController
        main_editor = QWidget()
        self.addCleanup(main_editor.deleteLater)
        main_editor.app_state_manager = SimpleNamespace(state=SimpleNamespace(selected_level=DB.levels[0].nid))
        with patch('app.editor.event_editor.event_properties.MainSettingsController',
                   lambda: MainSettingsController('lt_maker_tests', 'editor_form_refresh')):
            tab = self.open(EventDatabase, main_editor)
        tab.left_frame.level_filter_box.edit.setValue('All')
        self.app.processEvents()
        return QWidget.window(tab), tab.right_frame

    def rename_event(self, form, name):
        form.name_box.edit.setText(name)
        form.name_box.edit.editingFinished.emit()  # As leaving the box does

    def test_event_edits_are_recorded_so_undo_takes_them_back(self):
        from app.editor.edit_history import HISTORY
        check = patch('app.editor.edit_history.CHECK_UNRECORDED', True)
        check.start()
        self.addCleanup(check.stop)
        HISTORY.clear()  # The check starts from the database as it is now
        dialog, form = self.event_editor()
        event = form.current
        nid, name, condition = event.nid, event.name, event.condition

        with patch.object(logging, 'warning') as warning:
            form.condition_box.edit.setPlainText('False')
            self.rename_event(form, name + 'X')
            HISTORY.commit()
            dialog.reject()
            self.app.processEvents()
            self.assertEqual((name + 'X', 'False'), (event.name, event.condition))  # Closing keeps them
            while HISTORY.can_undo():
                HISTORY.undo()

        self.assertEqual([], [c for c in warning.call_args_list if 'LT_EDITOR_CHECK' in c.args[0]])
        self.assertEqual((name, condition), (event.name, event.condition))
        self.assertIs(event, DB.events.get_from_nid(nid))

    def test_an_event_renames_with_what_names_it_once_its_name_is_typed_and_undo_takes_it_back(self):
        from app.events.node_events import NodeMenuEvent
        dialog, form = self.event_editor()
        event = form.current
        nid, name = event.nid, event.name
        option = NodeMenuEvent('Option')
        option.event = nid
        DB.overworlds[0].overworld_nodes[0].menu_options.append(option)

        form.name_box.edit.setText(name + 'X')
        self.assertEqual(nid, event.nid)  # Not while typing
        form.name_box.edit.editingFinished.emit()

        self.assertIs(event, DB.events.get_from_nid(event.nid))
        self.assertNotEqual(nid, event.nid)
        self.assertEqual(event.nid, DB.overworlds[0].overworld_nodes[0].menu_options.get('Option').event)

        dialog.undo()

        self.assertEqual((nid, name), (event.nid, event.name))
        self.assertIs(event, DB.events.get_from_nid(nid))
        self.assertEqual(nid, DB.overworlds[0].overworld_nodes[0].menu_options.get('Option').event)
        self.assertEqual(name, form.name_box.edit.text())

    def highlighted_event(self, frame):
        index = frame.view.currentIndex()
        source = frame.name_filtered_model.mapToSource(frame.level_filtered_model.mapToSource(index))
        return DB.events[source.row()] if source.isValid() else None

    def test_the_event_list_follows_an_event_moved_to_another_level(self):
        dialog, form = self.event_editor()
        frame = dialog.tab.left_frame
        event = form.current
        frame.level_filter_box.edit.setValue(event.level_nid)
        other_level = next(level.nid for level in DB.levels if level.nid != event.level_nid)

        form.level_nid_box.edit.setValue(other_level)

        self.assertEqual(other_level, frame.level_filter_box.edit.currentText())
        self.assertIs(event, form.current)
        self.assertIs(event, self.highlighted_event(frame))

    def test_the_event_list_follows_an_event_whose_move_to_another_level_is_undone(self):
        dialog, form = self.event_editor()
        frame = dialog.tab.left_frame
        event = form.current
        level_nid = event.level_nid
        frame.level_filter_box.edit.setValue(level_nid)
        other_level = next(level.nid for level in DB.levels if level.nid != level_nid)
        form.level_nid_box.edit.setValue(other_level)  # The filter follows the event
        self.assertEqual(other_level, frame.level_filter_box.edit.currentText())

        dialog.undo()

        self.assertEqual(level_nid, event.level_nid)
        self.assertEqual(level_nid, frame.level_filter_box.edit.currentText())
        index = frame.view.currentIndex()
        source = frame.name_filtered_model.mapToSource(frame.level_filtered_model.mapToSource(index))
        self.assertIs(event, DB.events[source.row()])

    def option_widget(self, option):
        from PyQt5.QtWidgets import QWidget
        from app.editor.overworld_editor.node_menu_properties import ModifyOptionsWidget
        parent = QWidget()
        self.addCleanup(parent.deleteLater)
        widget = ModifyOptionsWidget(DB.overworlds[0].overworld_nodes[0].menu_options, parent)
        widget.set_current(option)
        return widget

    def pick_event(self, widget, event):
        box = widget.event_box.edit
        index = next(i for i, e in enumerate(widget.event_box.model._data) if e is event)
        box.setCurrentIndex(index)
        box.activated.emit(index)  # As choosing it in the box does

    def test_a_node_menu_option_names_its_event_by_nid_and_keeps_it_through_a_rename(self):
        from app.events.node_events import NodeMenuEvent
        option = NodeMenuEvent('Option')
        DB.overworlds[0].overworld_nodes[0].menu_options.append(option)
        event = DB.events.get_from_nid('Global OnStartup')
        widget = self.option_widget(option)

        self.pick_event(widget, event)
        self.assertEqual(event.nid, option.event)

        dialog, form = self.event_editor()
        dialog.tab.left_frame.show(event)
        self.rename_event(form, 'OnBoot')
        widget.event_box.refresh()
        widget.set_current(option)  # As the overworld editor shows it again

        self.assertEqual('Global OnBoot', option.event)
        self.assertEqual('OnBoot', widget.event_box.edit.currentText())

    def test_a_node_menu_option_naming_its_event_by_name_shows_it_and_is_not_changed_by_showing(self):
        from app.events.node_events import NodeMenuEvent
        option = NodeMenuEvent('Option')
        option.event = 'OnStartup'  # As options saved before they named events by nid
        DB.overworlds[0].overworld_nodes[0].menu_options.append(option)

        widget = self.option_widget(option)
        widget.set_current(option)

        self.assertEqual('OnStartup', widget.event_box.edit.currentText())
        self.assertEqual('OnStartup', option.event)

    def test_a_node_menu_option_whose_event_is_gone_is_not_cleared_by_showing(self):
        from app.events.node_events import NodeMenuEvent
        option = NodeMenuEvent('Option')
        option.event = 'Global Gone'
        DB.overworlds[0].overworld_nodes[0].menu_options.append(option)

        self.option_widget(option)

        self.assertEqual('Global Gone', option.event)

    def test_the_node_form_keeps_the_menu_option_it_shows_when_the_main_window_resyncs(self):
        from app.editor.custom_widgets import ObjBox
        from app.editor.lib.state_editor.editor_state_manager import EditorStateManager
        from app.editor.overworld_editor.node_properties import NodePropertiesMenu
        from app.events.node_events import NodeMenuEvent
        overworld = DB.overworlds[0]
        node = overworld.overworld_nodes[0]
        first, second = NodeMenuEvent('First'), NodeMenuEvent('Second')
        second.event = 'Global OnStartup'
        node.menu_options.append(first)
        node.menu_options.append(second)
        state_manager = EditorStateManager()
        state_manager.state.selected_overworld = overworld.nid
        menu = NodePropertiesMenu(state_manager)
        self.addCleanup(menu.deleteLater)
        state_manager.change_and_broadcast('selected_node', node.nid)
        options = menu.event_box
        options.select(node.menu_options.index('Second'))

        dialog, form = self.event_editor()
        dialog.tab.left_frame.show(DB.events.get_from_nid('Global OnStartup'))
        self.rename_event(form, 'OnBoot')
        # As the main window resyncs: boxes first, then what it shows
        for box in menu.findChildren(ObjBox):
            box.refresh()
        state_manager.change_and_broadcast('selected_node', node.nid)

        self.assertIs(second, options.modify_option_widget.current)
        self.assertEqual(node.menu_options.index('Second'), options.view.currentIndex().row())
        self.assertEqual('OnBoot', options.modify_option_widget.event_box.edit.currentText())

    def test_constants_class_lists_list_classes_as_they_are(self):
        from app.editor.constant_tab import ConstantDatabase, MainExpEquation
        tab = self.open(ConstantDatabase)
        equation = tab.findChildren(MainExpEquation)[0]
        box, constant = equation.class_list_boxes[0]
        chosen = DB.classes[0].nid
        constant.value = chosen
        gone = DB.classes[1].nid
        DB.classes.remove_key(gone)

        tab.reset()

        self.assertNotIn(gone, [box.itemText(i) for i in range(box.count())])
        self.assertEqual([chosen], box.currentText())
        self.assertEqual(chosen, constant.value)

    def test_an_older_tab_lists_the_record_it_shows_when_an_undo_puts_one_back_above_it(self):
        from PyQt5.QtWidgets import QWidget
        from app.editor.faction_editor.faction_tab import FactionDatabase
        from app.extensions.custom_gui import DeletionDialog
        tab = self.open(FactionDatabase)
        view = tab.left_frame.view
        tab.left_frame.set_current_row(0)
        gone = DB.factions[0]
        with patch.object(DeletionDialog, 'inform', return_value=True), \
                patch.object(DeletionDialog, 'get_swap', return_value=(DB.factions[1], True)):
            view.delete(view.currentIndex())  # As its context menu does
        self.app.processEvents()
        shown = tab.right_frame.current
        self.assertIsNot(gone, shown)

        QWidget.window(tab).undo()
        self.app.processEvents()

        self.assertIs(shown, tab.right_frame.current)
        self.assertEqual(DB.factions.index(shown.nid), view.currentIndex().row())

    def overworld_editor(self):
        from app.editor.lib.state_editor.editor_state_manager import EditorStateManager
        from app.editor.overworld_editor.overworld_editor import OverworldEditor
        state_manager = EditorStateManager()
        state_manager.state.selected_overworld = DB.overworlds[0].nid
        editor = OverworldEditor(state_manager)
        self.addCleanup(editor.deleteLater)
        return editor, state_manager, DB.overworlds[0]

    def test_overworld_editor_selects_again_the_node_an_undo_rebuilt(self):
        from app.editor.edit_history import restore_in_place
        editor, state_manager, overworld = self.overworld_editor()
        node = overworld.overworld_nodes[0]
        editor.select_object_on_map(*node.pos)
        self.assertIs(node, editor.selected_object.obj)

        restore_in_place(overworld, overworld.save())  # As an undo does
        state_manager.change_and_broadcast('selected_overworld', overworld.nid)  # As the main window does after it

        self.assertIsNot(node, editor.selected_object.obj)
        self.assertIs(overworld.overworld_nodes.get(node.nid), editor.selected_object.obj)

    def test_overworld_editor_selects_again_the_road_an_undo_rebuilt(self):
        from app.editor.edit_history import restore_in_place
        from app.editor.overworld_editor.overworld_editor import OverworldEditorInternalTypes, SelectedObject
        editor, state_manager, overworld = self.overworld_editor()
        key, road = next(iter(overworld.map_paths.items()))
        editor.selected_object = SelectedObject(OverworldEditorInternalTypes.FINISHED_ROAD, road)

        restore_in_place(overworld, overworld.save())
        state_manager.change_and_broadcast('selected_overworld', overworld.nid)

        self.assertEqual(OverworldEditorInternalTypes.FINISHED_ROAD, editor.selected_object.type)
        self.assertIs(overworld.map_paths[key], editor.selected_object.obj)

    def test_overworld_editor_edits_are_recorded(self):
        from app.editor.edit_history import HISTORY
        check = patch('app.editor.edit_history.CHECK_UNRECORDED', True)
        check.start()
        self.addCleanup(check.stop)
        HISTORY.clear()  # The check starts from the database as it is now
        editor, state_manager, overworld = self.overworld_editor()
        node = overworld.overworld_nodes[0]
        editor.select_object_on_map(*node.pos)
        editor.on_node_tab_select(True)
        editor.on_map_right_click(node.pos[0] + 1, node.pos[1])  # Moves the node

        with patch.object(logging, 'warning') as warning:
            mark = HISTORY.mark()  # As an editor opening does

        self.assertEqual([], [c for c in warning.call_args_list if 'LT_EDITOR_CHECK' in c.args[0]])
        self.assertIsNotNone(mark)

    def test_overworld_editor_deselects_a_node_that_is_gone(self):
        from app.editor.overworld_editor.overworld_editor import OverworldEditorInternalTypes
        editor, state_manager, overworld = self.overworld_editor()
        node = overworld.overworld_nodes[0]
        editor.select_object_on_map(*node.pos)

        overworld.overworld_nodes.remove_key(node.nid)
        state_manager.change_and_broadcast('selected_overworld', overworld.nid)

        self.assertEqual(OverworldEditorInternalTypes.NONE, editor.selected_object.type)
        self.assertIsNone(state_manager.state.selected_node)


if __name__ == '__main__':
    unittest.main()
