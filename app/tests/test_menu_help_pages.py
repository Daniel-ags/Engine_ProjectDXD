import unittest
from unittest.mock import patch

from app.data.database.database import DB
from app.engine import engine, feat_choice, item_component_access, item_funcs, menus, skill_component_access
from app.engine.info_menu.multi_desc import PagedHelpDialog
from app.tests.engine_harness import EngineTestCase

# testing_proj level 0: Eirika starts on (4, 5)
LEVEL = '0'
UNIT_POS = (4, 5)

class MenuHelpPagesTests(EngineTestCase):
    """
    Items and skills can carry further help pages through their multi desc components,
    but only the info menu could reach them. Every other menu showed the first page alone
    """

    def setUp(self):
        super().setUp()
        self.harness = self.start_harness()
        self.harness.start_level(LEVEL)
        self.harness.run_until_state('free')
        self.game = self.harness.game
        self.unit = self.game.get_unit('Eirika')
        self.item = self.unit.items[0]
        self.surf = engine.create_surface((240, 160), transparent=True)

    def give_pages(self, item, nids=None):
        component = item_component_access.get_component('multi_desc_skill')
        component.value = nids or [skill.nid for skill in list(DB.skills)[:2]]
        component.item = item
        item.components.append(component)

    def current_page(self, menu) -> int:
        return menu.options[menu.current_index].help_box.page

    def test_shop_menu_turns_pages_and_wraps(self):
        item = item_funcs.create_item(None, self.item.nid, assign_ownership=False)
        self.give_pages(item)
        menu = menus.Shop(self.unit, [item], disp_value='buy')
        menu.toggle_info()
        menu.draw(self.surf)
        self.assertEqual(3, len(menu.options[0].help_box.get_pages()))
        self.assertTrue(menu.next_help_page())
        self.assertEqual(1, self.current_page(menu))
        menu.draw(self.surf)
        self.assertTrue(menu.next_help_page())
        self.assertTrue(menu.next_help_page())
        self.assertEqual(0, self.current_page(menu))

    def test_no_turn_while_help_is_closed(self):
        self.give_pages(self.item)
        menu = menus.Inventory(self.unit, self.unit.items)
        self.assertFalse(menu.next_help_page())
        self.assertEqual(0, self.current_page(menu))

    def test_item_without_further_pages_does_not_turn(self):
        menu = menus.Inventory(self.unit, self.unit.items)
        menu.toggle_info()
        menu.draw(self.surf)
        self.assertFalse(menu.next_help_page())

    def test_further_pages_are_not_built_until_shown(self):
        self.give_pages(self.item)
        menu = menus.Inventory(self.unit, self.unit.items)
        self.assertIsNone(menu.options[0].help_box.pages)

    def test_page_goes_back_to_the_first_after_the_box_was_left(self):
        self.give_pages(self.item)
        help_box = menus.Inventory(self.unit, self.unit.items).options[0].help_box
        with patch.object(engine, 'get_time', return_value=5000):
            help_box.draw(self.surf, (0, 0))
            help_box.next_page()
            help_box.draw(self.surf, (0, 0))
            self.assertEqual(1, help_box.page)
        with patch.object(engine, 'get_time', return_value=7000):
            help_box.draw(self.surf, (0, 0))
            self.assertEqual(0, help_box.page)

    def test_trade_turns_the_page_of_the_side_with_the_hand(self):
        partner = next(unit for unit in self.game.units if unit.team == 'player' and unit is not self.unit)
        self.give_pages(self.item)
        menu = menus.Trade(self.unit, partner)
        self.assertFalse(menu.next_help_page())
        menu.toggle_info()
        menu.draw(self.surf)
        self.assertTrue(menu.next_help_page())
        self.assertEqual(1, self.current_page(menu.menu1))

    def test_convoy_turns_the_page_of_the_inventory(self):
        self.give_pages(self.item)
        menu = menus.Convoy(self.unit, (124, 40))
        menu.selection_index = 0
        self.assertFalse(menu.next_help_page())
        menu.toggle_info()
        menu.draw_info(self.surf)
        self.assertTrue(menu.next_help_page())
        self.assertEqual(1, self.current_page(menu.inventory))

    def test_convoy_turns_the_page_of_a_stored_item(self):
        stored = item_funcs.create_item(None, self.item.nid, assign_ownership=False)
        self.game.register_item(stored)
        self.give_pages(stored)
        self.game.get_party().convoy.append(stored)
        menu = menus.Convoy(self.unit, (124, 40))
        convoy_menu = next(m for m in menu.menus.values() if m.options[0].get() is stored)
        menu.selection_index = menu.menu_index + 1
        while menu.get_menu() is not convoy_menu:
            menu.menu_index += 1
            menu.selection_index += 1
        menu.toggle_info()
        menu.draw_info(self.surf)
        self.assertTrue(menu.next_help_page())
        self.assertEqual(1, self.current_page(convoy_menu))

    def test_market_turns_the_page_of_a_listed_item(self):
        item = item_funcs.create_item(None, self.item.nid, assign_ownership=False)
        self.game.register_item(item)
        self.give_pages(item)
        menu = menus.Market(self.unit, [item], (76, 40), disp_value='buy')
        market_menu = next(m for m in menu.menus.values() if m.options[0].get() is item)
        menu.selection_index = menu.order.index(next(k for k, m in menu.menus.items() if m is market_menu)) + 1
        menu.toggle_info()
        menu.draw_info(self.surf)
        self.assertTrue(menu.next_help_page())
        self.assertEqual(1, self.current_page(market_menu))

    def test_feat_prefab_turns_pages(self):
        # Feats are skill prefabs, not skill objects
        skills = list(DB.skills)
        component = skill_component_access.get_component('multi_desc_skill')
        component.value = [skills[1].nid]
        skills[0].components.append(component)
        help_box = feat_choice.SkillOption(0, skills[0]).get_help_box()
        self.assertIsInstance(help_box, PagedHelpDialog)
        self.assertTrue(help_box.next_page())
        help_box.draw(self.surf, (0, 0))

    def test_item_menu_turns_pages_with_the_aux_button(self):
        harness = self.harness
        self.give_pages(self.item)
        harness.select_unit('Eirika')
        harness.run_until_state('move')
        harness.press('SELECT')
        harness.run_until_state('menu')
        harness.choose('Item')
        harness.run_until_state('item')
        menu = self.game.state.current_state().menu
        harness.press('AUX')
        self.assertEqual(0, self.current_page(menu))  # Help is closed
        harness.press('INFO')
        harness.step()
        harness.press('AUX')
        self.assertEqual(1, self.current_page(menu))
        harness.step(5)

if __name__ == '__main__':
    unittest.main()
