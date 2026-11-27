from typing import List, Tuple

from app.constants import FRAMERATE, TILEHEIGHT, TILEWIDTH, WINHEIGHT, WINWIDTH
# from app.data.resources.resources import RESOURCES
from app.data.database.database import DB
from app.engine import action, background, banner, base_surf
from app.engine import config as cf
from app.engine import (convoy_funcs, engine, gui, image_mods,
                        item_funcs, item_system, menus, text_funcs,
                        trade, skill_system, icons)
from app.engine.background import SpriteBackground
from app.engine.combat import interaction
from app.engine.fluid_scroll import FluidScroll
from app.engine.fonts import FONT
from app.engine.game_state import game
from app.engine.input_manager import get_input_manager
from app.engine.sound import get_sound_thread
from app.engine.sprites import SPRITES
from app.engine.state import MapState, State
from app.events import triggers


def setup_units():
    # Force place any required units
    for unit in game.get_units_in_party():
        possible_position = game.get_next_formation_spot()
        if 'Required' in unit.tags and possible_position and not unit.position:
            action.ArriveOnMap(unit, possible_position).do()

    # Force reset all units
    action.do(action.ResetAll([unit for unit in game.units if not unit.dead]))


class PrepMainState(State):
    name = 'prep_main'
    transparent = True  # Mantém o mapa de batalha visível ao fundo

    def start(self):
        self.fluid = FluidScroll()

        # Sequência oficial FE3H com rótulos curtos: 12:00 no topo, sentido horário a cada 45°
        self.ring_options = [
            "Units",
            "Inventory",
            "Save",
            "System",
            "Quit",
            "Market",
            "Support",
            "Map"
        ]

        disabled = []
        if not self._get_market_items():
            disabled.append("Market")

        # Centralizado exatamente no meio da tela (120, 80) com raio circular de 46px
        self.menu = menus.RadialMenu(
            center_option="Fight",
            ring_options=self.ring_options,
            center_pos=(WINWIDTH // 2, WINHEIGHT // 2),
            radius=(76, 76),
            disabled_options=disabled
        )

        # Estados de submenus modais
        self.active_modal = None
        self.sub_menu = None

        game.state.change('transition_in')
        return 'repeat'

    def begin(self):
        self.fluid.reset_on_change_state()
        if game.memory.pop('save_and_quit_pending', False):
            game.state.clear()
            game.state.change('title_start')
            return

        if self.menu:
            if self._get_market_items():
                self.menu.disabled_options.discard("Market")
            else:
                self.menu.disabled_options.add("Market")

    def _get_active_player_units(self):
        return [u for u in game.get_units_in_party() if u.team == 'player']

    def _can_start_battle(self) -> bool:
        return any(u.team == 'player' and u.position for u in game.units)

    # -------------------------------------------------------------------------
    # Abertura dos Submenus Modais
    # -------------------------------------------------------------------------
    def _open_inventory_submenu(self):
        """Abre o submenu modal com Items, Skills e Reclass."""
        self.active_modal = 'INVENTORY'
        sub_options = ["Items", "Skills", "Reclass"]
        box_w = 80
        box_x = (WINWIDTH - box_w) // 2
        box_y = (WINHEIGHT - (len(sub_options) * 16 + 16)) // 2
        self.sub_menu = menus.Choice(None, sub_options, topleft=(box_x, box_y), background='menu_bg_base')
        get_sound_thread().play_sfx('Select 1')

    def _open_quit_modal(self):
        """Abre o modal de saída com a opção de salvar antes de sair."""
        self.active_modal = 'QUIT'
        quit_options = ["Save & Quit", "Quit", "Cancel"]
        box_w = 110
        box_x = (WINWIDTH - box_w) // 2
        box_y = (WINHEIGHT - (len(quit_options) * 16 + 16)) // 2
        self.sub_menu = menus.Choice(None, quit_options, topleft=(box_x, box_y), background='menu_bg_base')
        # Inicia sobre 'Cancel' por segurança
        self.sub_menu.move_to(2)
        get_sound_thread().play_sfx('Select 5')

    def _get_market_items(self) -> list:
        """Lê o estoque nativo alimentado pelos comandos add_market_item do Editor."""
        raw_items = getattr(game, 'market_items', None)
        if not raw_items:
            return []
        nids = raw_items.keys() if isinstance(raw_items, dict) else raw_items
        return [nid for nid in nids if DB.items.get(nid)]

    # -------------------------------------------------------------------------
    # Tratamento de Entrada
    # -------------------------------------------------------------------------
    def take_input(self, event):
        first_push = self.fluid.update()
        directions = self.fluid.get_directions()
        units = self._get_active_player_units()

        # 1. Entrada no Submenu de INVENTORY
        if self.active_modal == 'INVENTORY':
            self.sub_menu.handle_mouse()
            if 'DOWN' in directions:
                if self.sub_menu.move_down(first_push):
                    get_sound_thread().play_sfx('Select 5')
            elif 'UP' in directions:
                if self.sub_menu.move_up(first_push):
                    get_sound_thread().play_sfx('Select 5')

            if event == 'BACK':
                get_sound_thread().play_sfx('Select 4')
                self.active_modal = None
                self.sub_menu = None

            elif event == 'SELECT':
                choice = self.sub_menu.get_current()
                if not units:
                    get_sound_thread().play_sfx('Error')
                    return

                self.active_modal = None
                self.sub_menu = None

                if choice == "Items":
                    get_sound_thread().play_sfx('Select 1')
                    if not game.memory.get('prep_bg'):
                        game.memory['prep_bg'] = background.create_background('rune_background')
                    game.memory['current_unit'] = None
                    game.state.change('prep_manage')
                elif choice == "Skills":
                    get_sound_thread().play_sfx('Select 1')
                    game.memory['current_unit'] = units[0]
                    if 'base_skills_select' in game.state.all_states:
                        game.state.change('base_skills_select')
                    else:
                        game.state.change('prep_manage')
                elif choice == "Reclass":
                    get_sound_thread().play_sfx('Select 1')
                    game.memory['current_unit'] = units[0]
                    if 'class_change_choice' in game.state.all_states:
                        game.state.change('class_change_choice')
                    elif 'promotion_choice' in game.state.all_states:
                        game.state.change('promotion_choice')
                    else:
                        game.state.change('prep_manage')
            return

        # 2. Entrada no Modal de QUIT
        if self.active_modal == 'QUIT':
            self.sub_menu.handle_mouse()
            if 'DOWN' in directions:
                if self.sub_menu.move_down(first_push):
                    get_sound_thread().play_sfx('Select 5')
            elif 'UP' in directions:
                if self.sub_menu.move_up(first_push):
                    get_sound_thread().play_sfx('Select 5')

            if event == 'BACK':
                get_sound_thread().play_sfx('Select 4')
                self.active_modal = None
                self.sub_menu = None

            elif event == 'SELECT':
                choice = self.sub_menu.get_current()
                if choice == "Save & Quit":
                    get_sound_thread().play_sfx('Select 1')
                    self.active_modal = None
                    self.sub_menu = None
                    game.memory['save_kind'] = 'prep'
                    game.memory['save_and_quit_pending'] = True
                    game.state.change('in_chapter_save')

                elif choice == "Quit":
                    get_sound_thread().play_sfx('Select 1')
                    self.active_modal = None
                    self.sub_menu = None
                    game.state.clear()
                    game.state.change('title_start')

                elif choice == "Cancel":
                    get_sound_thread().play_sfx('Select 4')
                    self.active_modal = None
                    self.sub_menu = None
            return

        # 3. Navegação Normal na Roda Radial
        self.menu.handle_input(directions, first_push)

        if event == 'SELECT':
            choice = self.menu.get_current()

            if choice == "Fight":
                if self._can_start_battle():
                    get_sound_thread().play_sfx('Select 1')
                    game.state.change('transition_pop')
                else:
                    get_sound_thread().play_sfx('Error')

            elif choice == "Units":
                get_sound_thread().play_sfx('Select 1')
                game.state.change('prep_pick_units')

            elif choice == "Inventory":
                self._open_inventory_submenu()

            elif choice == "Save":
                get_sound_thread().play_sfx('Select 1')
                game.memory['save_kind'] = 'prep'
                game.state.change('in_chapter_save')

            elif choice == "System":
                get_sound_thread().play_sfx('Select 1')
                game.state.change('settings_menu')

            elif choice == "Quit":
                self._open_quit_modal()

            elif choice == "Market":
                market_items = self._get_market_items()
                if not units or not market_items:
                    get_sound_thread().play_sfx('Error')
                    return

                get_sound_thread().play_sfx('Select 1')
                if not game.memory.get('prep_bg'):
                    game.memory['prep_bg'] = background.create_background('rune_background')
                game.memory['current_unit'] = units[0]
                game.state.change('prep_market')

            elif choice == "Support":
                get_sound_thread().play_sfx('Select 1')
                if not game.memory.get('base_bg'):
                    game.memory['base_bg'] = background.create_background('settings_background')
                if 'base_supports' in game.state.all_states:
                    game.state.change('base_supports')
                elif 'prep_support' in game.state.all_states:
                    game.state.change('prep_support')
                else:
                    get_sound_thread().play_sfx('Error')

            elif choice == "Map":
                get_sound_thread().play_sfx('Select 1')
                if 'prep_formation' in game.state.all_states:
                    game.state.change('prep_formation')
                else:
                    game.state.change('prep_map')

    def update(self):
        super().update()
        if self.sub_menu:
            self.sub_menu.update()
        if self.menu and "Market" in self.menu.disabled_options and self._get_market_items():
            self.menu.disabled_options.discard("Market")

    def _draw_active_title_card(self, surf):
        cur = self.menu.get_current()
        title_text = "To Battle" if cur == "Fight" else cur

        text_w = FONT['text'].width(title_text)
        card_w = max(72, ((text_w + 16 + 7) // 8) * 8)
        card_h = 24
        card_x = (WINWIDTH - card_w) // 2
        card_y = 6

        card_surf = base_surf.create_base_surf(card_w, card_h, 'menu_bg_base')
        card_surf = image_mods.make_translucent(card_surf, 0.1)

        t_x = (card_w - text_w) // 2
        t_y = (card_h - FONT['text'].height) // 2
        FONT['text-yellow'].blit(title_text, card_surf, (t_x, t_y))
        surf.blit(card_surf, (card_x, card_y))

    def _draw_active_title_card(self, surf):
        cur = self.menu.get_current()
        title_text = "To Battle" if cur == "Fight" else self.full_names.get(cur, cur)

        text_w = FONT['text'].width(title_text)
        card_w = max(72, ((text_w + 16 + 7) // 8) * 8)
        card_h = 24
        card_x = (WINWIDTH - card_w) // 2
        card_y = 6

        card_surf = base_surf.create_base_surf(card_w, card_h, 'menu_bg_base')
        card_surf = image_mods.make_translucent(card_surf, 0.1)

        t_x = (card_w - text_w) // 2
        t_y = (card_h - FONT['text'].height) // 2
        FONT['text-yellow'].blit(title_text, card_surf, (t_x, t_y))
        surf.blit(card_surf, (card_x, card_y))

    def draw(self, surf):
        surf = super().draw(surf)

        if self.menu:
            self.menu.draw(surf)

        if self.active_modal and self.sub_menu:
            self.sub_menu.draw(surf)

        return surf

class PrepPickUnitsState(State):
    name = 'prep_pick_units'
    transparent = True

    def start(self):
        self.fluid = FluidScroll()
        player_units = game.get_units_in_party()
        stuck_units = [unit for unit in player_units if unit.position and not game.check_for_region(unit.position, 'formation')]
        unstuck_units = [unit for unit in player_units if unit not in stuck_units]

        self.units = stuck_units + sorted(unstuck_units, key=lambda unit: bool(unit.position), reverse=True)
        self.menu = menus.Table(None, self.units, (6, 2), (110, 24))
        self.menu.set_mode('position')
        # As on the GBA (ProcPrepUnit_Idle), the hand stops at the left and right edges
        self.menu.wrap_rows = False

        self.bg = background.create_background('rune_background')
        game.memory['prep_bg'] = self.bg

        game.state.change('transition_in')
        return 'repeat'

    def begin(self):
        self.fluid.reset_on_change_state()
        # If come back from info menu
        unit = game.memory.get('current_unit')
        if unit and unit in self.units:
            idx = self.units.index(unit)
            self.menu.move_to(idx)
        game.memory['current_unit'] = None

    def order_party(self):
        '''Run on exiting the prep menu. Saves the order for future levels with the party.
        Saved order is unique to current party - will not effect other parties'''
        party = game.parties[game.current_party]
        party.party_prep_manage_sort_order = [u.nid for u in sorted(self.units, key=lambda unit: bool(unit.position), reverse=True)]

    def take_input(self, event):
        first_push = self.fluid.update()
        directions = self.fluid.get_directions()

        self.menu.handle_mouse()
        # As on the GBA (ProcPrepUnit_Idle), the hand only makes a sound when it moves
        moved = False
        if 'DOWN' in directions:
            moved = self.menu.move_down(first_push)
        elif 'UP' in directions:
            moved = self.menu.move_up(first_push)
        elif 'LEFT' in directions:
            moved = self.menu.move_left(first_push)
        elif 'RIGHT' in directions:
            moved = self.menu.move_right(first_push)
        if moved:
            get_sound_thread().play_sfx('Select 5')

        # As on the GBA (PrepUnit_HandlePressA), picking a unit makes the select sound,
        # sending one back the cancel sound, and a unit that can't be picked or sent back the miss
        if event == 'SELECT':
            unit = self.menu.get_current()
            pair_up_valid = DB.constants.value('pairup') and not DB.constants.value('attack_stance_only')
            if not unit:
                get_sound_thread().play_sfx('Error')
                return
            if unit.position and not game.check_for_region(unit.position, 'formation'):
                get_sound_thread().play_sfx('Error')  # Locked/Lord character
            elif unit.position and 'Required' in unit.tags:
                get_sound_thread().play_sfx('Error')  # Required unit, can't be removed
            elif unit.position:
                get_sound_thread().play_sfx('Select 4')
                if unit.traveler:
                    action.do(action.Separate(unit, game.get_unit(unit.traveler), None, False))
                action.do(action.LeaveMap(unit))
            elif pair_up_valid and game.get_rescuer(unit) and game.get_rescuer(unit).position:
                get_sound_thread().play_sfx('Select 4')
                action.do(action.Separate(game.get_rescuer(unit), unit, None, False))
            else:
                possible_position = game.get_next_formation_spot()
                is_fatigued = False
                if DB.constants.value('fatigue') and game.game_vars.get('_fatigue') == 1:
                    if unit.get_fatigue() >= unit.get_max_fatigue():
                        is_fatigued = True
                if 'Blacklist' in unit.tags:  # Blacklisted unit can't be added
                    is_fatigued = True
                num_slots = game.level_vars.get('_prep_slots')
                if num_slots is None:
                    num_slots = len(game.get_all_formation_spots())
                on_map = [unit for unit in game.units if unit.position and unit in game.get_units_in_party()
                          and game.check_for_region(unit.position, 'formation')]
                if pair_up_valid:
                    on_map += [unit for unit in game.units if unit in game.get_units_in_party() and not unit.position and game.get_rescuer(unit) and game.get_rescuer(unit).position]
                if not is_fatigued and len(on_map) < num_slots:
                    if possible_position:
                        get_sound_thread().play_sfx('Select 1')
                        action.do(action.ArriveOnMap(unit, possible_position))
                        action.do(action.Reset(unit))
                    elif pair_up_valid and not all(unit.traveler for unit in on_map if unit.position):
                        get_sound_thread().play_sfx('Select 1')
                        next_unit = next((unit for unit in on_map if unit.position and not unit.traveler))
                        action.do(action.PairUp(unit, next_unit))
                    else:
                        get_sound_thread().play_sfx('Error')  # Nowhere to put them
                else:
                    get_sound_thread().play_sfx('Error')  # Fatigued, or every slot is taken

        elif event == 'BACK':
            self.order_party()
            get_sound_thread().play_sfx('Select 4')
            game.state.change('transition_pop')

        elif event == 'INFO':
            get_sound_thread().play_sfx('Select 1')
            game.memory['scroll_units'] = game.get_units_in_party()
            game.memory['current_unit'] = self.menu.get_current()
            game.memory['next_state'] = 'info_menu'
            game.state.change('transition_to')

    def update(self):
        self.menu.update()

    def draw_pick_units_card(self, surf):
        bg_surf = base_surf.create_base_surf(132, 24, 'menu_bg_white')
        player_units = game.get_units_in_party()
        on_map = [unit for unit in game.units if unit.position and unit in player_units and game.check_for_region(unit.position, 'formation')]
        pair_up_valid = DB.constants.value('pairup') and not DB.constants.value('attack_stance_only')
        if pair_up_valid:
            on_map += [unit for unit in game.units if unit in player_units and not unit.position and game.get_rescuer(unit) and game.get_rescuer(unit).position]
        num_slots = game.level_vars.get('_prep_slots')
        if num_slots is None:
            num_slots = len(game.get_all_formation_spots())
        num_on_map = len(on_map)
        pick_s = ['Pick ', str(num_slots - num_on_map), ' units  ', str(num_on_map), '/', str(num_slots)]
        pick_f = ['text', 'text-blue', 'text', 'text-blue', 'text', 'text-blue']
        left_justify = 8
        for word, font in zip(pick_s, pick_f):
            FONT[font].blit(word, bg_surf, (left_justify, 4))
            left_justify += FONT[font].width(word)
        surf.blit(bg_surf, (110, 4))

    def draw_fatigue_card(self, surf):
        # Useful for telling at a glance which units are fatigued
        bg_surf = base_surf.create_base_surf(132, 24)
        topleft = (110, 128 + 4)
        unit = self.menu.get_current()
        if 'Blacklist' in unit.tags:
            text = text_funcs.translate('Away')
        elif unit.get_fatigue() >= unit.get_max_fatigue():
            text = text_funcs.translate('Fatigued')
        else:
            text = text_funcs.translate('Ready!')
        FONT['text'].blit_center(text, bg_surf, (66, 4))
        surf.blit(bg_surf, topleft)

    def draw(self, surf):
        if self.bg:
            self.bg.draw(surf)
        if self.menu.get_current():
            menus.draw_unit_items(surf, (4, 44), self.menu.get_current(), include_top=True)

        self.draw_pick_units_card(surf)
        if DB.constants.value('fatigue') and game.game_vars.get('_fatigue'):
            self.draw_fatigue_card(surf)

        self.menu.draw(surf)
        return surf


def _handle_info():
    if game.cursor.get_hover():
        get_sound_thread().play_sfx('Select 1')
        game.memory['next_state'] = 'info_menu'
        game.memory['current_unit'] = game.cursor.get_hover()
        game.state.change('transition_to')
    elif region := game.cursor.get_previewable_region():
        get_sound_thread().play_sfx('Select 1')
        did_trigger = game.events.trigger(triggers.Preview(game.cursor.position, region))
        if did_trigger and region.only_once:
            action.do(action.RemoveRegion(region))
    else:
        get_sound_thread().play_sfx('Select 3')
        game.boundary.toggle_all_enemy_attacks()


def _move_on_map(unit, pos):
    """The unit flies from the tile it stands on to pos, an empty one"""
    old_pos = unit.position
    action.do(action.LeaveMap(unit))
    action.do(action.ArriveOnMap(unit, pos))
    unit.sprite.begin_swap_arc(old_pos)


def _swap_on_map(unit1, unit2):
    """Two units on the map trade places, each flying to the other's tile"""
    pos1, pos2 = unit1.position, unit2.position
    action.do(action.LeaveMap(unit1))
    action.do(action.LeaveMap(unit2))
    action.do(action.ArriveOnMap(unit1, pos2))
    action.do(action.ArriveOnMap(unit2, pos1))
    unit1.sprite.begin_swap_arc(pos1)
    unit2.sprite.begin_swap_arc(pos2)


def _units_in_flight():
    return [unit for unit in game.get_player_units() if unit.sprite.transition_state == 'swap_arc']


class PrepFormationState(MapState):
    name = 'prep_formation'

    def start(self):
        game.highlight.show_formation(game.get_all_formation_spots())

    def begin(self):
        game.cursor.show()
        game.boundary.show()

    def take_input(self, event):
        if _units_in_flight():
            return  # As on the GBA, nothing can be done until reordered units have landed

        game.cursor.take_input()

        if event == 'INFO':
            _handle_info()

        elif event == 'AUX':
            pass

        elif event == 'SELECT':
            cur_unit = game.cursor.get_hover()
            if cur_unit:
                # solo unit on a formation tile
                if not cur_unit.traveler and game.check_for_region(game.cursor.position, 'formation'):
                    get_sound_thread().play_sfx('Select 3')
                    game.memory['formation_unit'] = cur_unit
                    game.state.change('prep_formation_select')
                # paired up unit on a formation tile
                elif cur_unit.traveler and game.check_for_region(game.cursor.position, 'formation'):
                    get_sound_thread().play_sfx('Select 1')
                    game.memory['formation_unit'] = game.get_unit(cur_unit.traveler)
                    game.memory['child_menu'] = menus.Choice(cur_unit, ['Continue', 'Switch'])
                    game.state.change('prep_formation_menu')
                else:
                    get_sound_thread().play_sfx('Select 2')
                    player_team_enemies = DB.teams.enemies
                    if cur_unit.team in player_team_enemies:
                        get_sound_thread().play_sfx('Select 3')
                        game.boundary.toggle_unit(cur_unit)
                    else:
                        get_sound_thread().play_sfx('Error')
            elif region := game.cursor.get_previewable_region():
                get_sound_thread().play_sfx('Select 1')
                did_trigger = game.events.trigger(triggers.Preview(game.cursor.position, region))
                if did_trigger and region.only_once:
                    action.do(action.RemoveRegion(region))

        elif event == 'BACK':
            get_sound_thread().play_sfx('Select 1')
            if game.memory.get('_prep_outline'):
                game.memory['_prep_outline'].fade_in()
            game.state.back()

        elif event == 'START':
            if DB.constants.value('initiative'):
                get_sound_thread().play_sfx('Select 5')
                game.initiative.toggle_draw()
            elif DB.constants.value('minimap') and game.game_vars.get('_minimap', True):
                get_sound_thread().play_sfx('Select 5')
                game.state.change('minimap')
            else:
                get_sound_thread().play_sfx('Error')

    def update(self):
        super().update()
        game.highlight.handle_hover()

    def draw(self, surf):
        surf = super().draw(surf)
        # The hand rides above each reordered unit while it flies, as on the GBA
        for unit in _units_in_flight():
            x = (unit.position[0] - game.camera.get_x()) * TILEWIDTH + unit.sprite.offset[0] + PrepFormationSelectState.marker_left
            y = (unit.position[1] - game.camera.get_y()) * TILEHEIGHT + unit.sprite.offset[1] - PrepFormationSelectState.marker_height
            surf.blit(PrepFormationSelectState.marker, (x, y))
        if game.memory.get('_prep_outline'):
            game.memory['_prep_outline'].draw(surf)
        return surf

    def finish(self):
        game.ui_view.remove_unit_display()
        game.cursor.hide()
        game.highlight.hide_formation()
        game.highlight.remove_highlights()


class PrepFormationSelectState(MapState):
    name = 'prep_formation_select'
    marker = SPRITES.get('menu_hand_rotated')
    # Where the GBA draws its hands, in pixels right of the tile's left edge and
    # above its top. The one over the picked unit, and over a unit in flight, stays
    # at marker_height
    marker_left = 3
    marker_height = 12
    # The one over the cursor bobs down from marker_bob_height: how far it hangs
    # below that on each frame. It rests at the bottom and at the top and is quick
    # in between
    marker_bob_height = 14
    # And it is held this high over a tile nothing can be put down on
    marker_blocked_height = 10
    marker_offset = [5] * 4 + [3] * 3 + [2] + [1] * 3 + [0] * 4 + [1] * 3 + [2] + [3] * 3

    def start(self):
        game.cursor.formation_show()
        self.last_update = engine.get_time()
        self.counter = 0
        self.unit = game.memory.get('formation_unit') or game.cursor.get_hover()

    def back(self):
        game.state.back()
        game.ui_view.remove_unit_display()
        game.highlight.remove_highlights()

    def take_input(self, event):
        game.cursor.take_input()

        if event == 'SELECT':
            hovered_unit = game.cursor.get_hover()
            pair_up_valid = DB.constants.value('pairup') and not DB.constants.value('attack_stance_only')

            if game.check_for_region(game.cursor.position, 'formation'):
                get_sound_thread().play_sfx('FormationSelect')
                # If hovered unit is not a player or is the current_unit
                # Error
                if hovered_unit and (hovered_unit.team != 'player' or hovered_unit is self.unit or \
                                        hovered_unit is game.get_rescuer(self.unit)):
                    get_sound_thread().play_sfx('Error')
                # Else if duo unit
                # Swap us
                elif hovered_unit and hovered_unit.traveler:
                    game.memory['child_menu'] = menus.Choice(self.unit, ['Switch', 'Swap'])
                    game.state.change('prep_formation_menu')
                # Else if solo unit and can pair-up
                # Give option between pair up and swap
                elif hovered_unit and pair_up_valid:
                    game.memory['child_menu'] = menus.Choice(self.unit, ['Pair Up', 'Swap'])
                    game.state.change('prep_formation_menu')
                # Else if solo unit but cannot pair-up and I'm on the map
                # Swap us
                elif hovered_unit and self.unit.position:
                    _swap_on_map(self.unit, hovered_unit)
                    self.back()
                # Else if solo unit but cannot pair-up and I'm not on the map
                # Send solo unit to bench and put me there, unless solo unit is REQUIRED
                elif hovered_unit:
                    # Can't sendt the hovered unit back
                    if 'Required' in hovered_unit.tags:
                        get_sound_thread().play_sfx('Error')
                    else:  # Send the hovered unit back
                        action.do(action.Separate(game.get_rescuer(self.unit), self.unit, None, False))
                        action.do(action.LeaveMap(hovered_unit))
                        action.do(action.ArriveOnMap(self.unit, game.cursor.position))
                        self.back()
                # Else no unit
                # Put me there
                else:
                    if self.unit.position:
                        _move_on_map(self.unit, game.cursor.position)
                        self.back()
                    else:
                        game.memory['child_menu'] = menus.Choice(self.unit, ['Separate', 'Swap'])
                        game.state.change('prep_formation_menu')
            else:
                get_sound_thread().play_sfx('Error')

        elif event == 'BACK':
            get_sound_thread().play_sfx('Select 4')
            # As on the GBA, the cursor goes back to the unit that was picked up
            game.cursor.set_pos(self.unit_position())
            self.back()

        elif event == 'AUX':
            game.cursor.set_pos(self.unit_position())

        elif event == 'INFO':
            _handle_info()

    def unit_position(self):
        """Where the picked up unit is: on its own tile, or on its carrier's"""
        return self.unit.position or game.get_rescuer(self.unit).position

    def draw(self, surf):
        surf = super().draw(surf)

        # Draw static hand
        if self.unit:
            pos = self.unit_position()
            x = (pos[0] - game.camera.get_x()) * TILEWIDTH + self.marker_left
            y = (pos[1] - game.camera.get_y()) * TILEHEIGHT - self.marker_height
            surf.blit(self.marker, (x, y))

        hovered_unit = game.cursor.get_hover()
        pos = game.cursor.position
        if game.check_for_region(pos, 'formation') or (hovered_unit and hovered_unit.team == 'player' and hovered_unit.traveler):
            frames_passed = (engine.get_time() - self.last_update) // FRAMERATE
            self.counter = frames_passed % len(self.marker_offset)
            height = self.marker_bob_height - self.marker_offset[self.counter]
        else:
            # Nothing can be put down here: the hand keeps still, over the cursor's blinking X
            height = self.marker_blocked_height
        # The cursor's offset is how far it still is from its tile: the hand slides with it
        x = (pos[0] - game.camera.get_x()) * TILEWIDTH - game.cursor.offset_x + self.marker_left
        y = (pos[1] - game.camera.get_y()) * TILEHEIGHT - game.cursor.offset_y - height
        surf.blit(self.marker, (x, y))

        return surf


class PrepFormationMenuState(MapState):
    name = 'prep_formation_menu'

    def start(self):
        self.unit = game.memory['formation_unit']  # Unit that you originally clicked first
        self.menu = game.memory['child_menu']
        game.memory['child_menu'] = None

    def begin(self):
        self.fluid.reset_on_change_state()

    def take_input(self, event):
        def swap_duo_unit(hovered_unit):
            # Hovered unit nevers moves, just the traveler
            traveler = game.get_unit(hovered_unit.traveler)
            # If the originally selected unit was on the map
            if self.unit.position:
                old_unit_position = self.unit.position
                action.do(action.Separate(hovered_unit, traveler, None, False))
                action.do(action.PairUp(self.unit, hovered_unit))
                action.do(action.ArriveOnMap(traveler, old_unit_position))
            # The moving unit was a traveler
            else:
                carrier = game.get_rescuer(self.unit)
                action.do(action.Separate(hovered_unit, traveler, None, False))
                action.do(action.Separate(carrier, self.unit, None, False))
                action.do(action.PairUp(self.unit, hovered_unit))
                action.do(action.PairUp(traveler, carrier))

        first_push = self.fluid.update()
        directions = self.fluid.get_directions()

        did_move = self.menu.handle_mouse()
        if 'DOWN' in directions:
            if self.menu.move_down(first_push):
                get_sound_thread().play_sfx('Select 6')
        elif 'UP' in directions:
            if self.menu.move_up(first_push):
                get_sound_thread().play_sfx('Select 6')

        if event == 'BACK':
            get_sound_thread().play_sfx('Select 4')
            game.state.back()

        elif event == 'SELECT':
            get_sound_thread().play_sfx('Select 1')
            selection = self.menu.get_current()
            hovered_unit = game.cursor.get_hover()

            if selection == 'Pair Up':
                # Guaranteed that hovered unit exists and is on a formation and is by itself
                if self.unit.position:
                    # Unit was a solo unit
                    action.do(action.LeaveMap(self.unit))
                    action.do(action.PairUp(self.unit, hovered_unit))
                else:
                    # Unit was a duo unit
                    action.do(action.Separate(game.get_rescuer(self.unit), self.unit, None, False))
                    action.do(action.PairUp(self.unit, hovered_unit))
                game.state.back()
                game.state.back()

            elif selection == 'Swap':
                # NOT guaranteed that hovered unit exists
                if self.unit.position:
                    # Unit was a solo unit
                    unit_to_move = self.unit
                else:
                    # Unit was a duo unit
                    unit_to_move = game.get_rescuer(self.unit)
                if hovered_unit:
                    _swap_on_map(unit_to_move, hovered_unit)
                else:
                    _move_on_map(unit_to_move, game.cursor.position)
                game.state.back()
                game.state.back()

            elif selection == 'Separate':
                # guaranteed that we are hovering over an empty formation tile
                action.do(action.Separate(game.get_rescuer(self.unit), self.unit, None, False))
                action.do(action.ArriveOnMap(self.unit, game.cursor.position))
                game.state.back()
                game.state.back()

            elif selection == 'Continue':
                # guaranteed that we are hovering over a duo unit on a formation
                game.state.back()
                game.state.change('prep_formation_select')

            elif selection == 'Switch':
                # guaranteed that we are hovering over a duo unit on a formation
                if hovered_unit.traveler is self.unit.nid:
                    # currently at [Continue, Switch] option menu after select a duo unit
                    action.do(action.SwitchPaired(game.get_rescuer(self.unit), self.unit))
                    game.state.back()
                else:
                    # currently at [Switch, Swap] option menu after hover over a duo unit
                    swap_duo_unit(hovered_unit)
                    game.state.back()
                    game.state.back()

    def update(self):
        super().update()
        self.menu.update()

    def draw(self, surf):
        surf = super().draw(surf)
        surf = self.menu.draw(surf)
        return surf


def draw_funds(surf):
    # Draw R: Info display
    helper = get_input_manager().get_button_name('INFO').upper()
    FONT['text-yellow'].blit(helper, surf, (123, 143))
    FONT['text'].blit(': Info', surf, (123 + FONT['text-blue'].width(helper), 143))
    # Draw Funds display
    surf.blit(SPRITES.get('funds_display'), (168, 137))
    money = str(game.get_money())
    FONT['text-blue'].blit_right(money, surf, (219, 141))


class PrepManageState(State):
    name = 'prep_manage'

    def start(self):
        self.fluid = FluidScroll()

        units = game.get_units_in_party()
        self.units = sorted(units, key=lambda unit: bool(unit.position), reverse=True)
        self.menu = menus.Table(None, self.units, (4, 3), (6, 0))
        # As on the GBA (PrepItemScreen_DpadKeyHandler), the hand stops at the left and right edges
        self.menu.wrap_rows = False
        if self.name.startswith('base'):
            self.menu.set_mode('unit')
        else:
            self.menu.set_mode('prep_manage')  # Gray out undeployed units in prep

        # Display
        self.quick_disp = self.create_quick_disp()

        if self.name.startswith('base') and game.memory.get('base_bg'):
            self.bg = game.memory.get('base_bg') or background.create_background('settings_background')
        else:
            self.bg = background.create_background('rune_background')
        game.memory['prep_bg'] = self.bg
        game.memory['manage_menu'] = self.menu

        game.state.change('transition_in')
        return 'repeat'

    def begin(self):
        self.fluid.reset_on_change_state()
        # If come back from info menu
        unit = game.memory.get('current_unit')
        if unit and unit in self.units:
            idx = self.units.index(unit)
            self.menu.move_to(idx)
        game.memory['current_unit'] = None

    def create_quick_disp(self):
        sprite = SPRITES.get('buttons')
        buttons = [sprite.subsurface(0, 66, 14, 13), sprite.subsurface(0, 165, 33, 9)]
        font = FONT.get('ui_prep', FONT['text'])
        commands = ['Manage', 'Optimize All']
        commands = [text_funcs.translate(c) for c in commands]
        size = (49 + max(font.width(c) for c in commands), 40)
        bg_surf = base_surf.create_base_surf(size[0], size[1], 'menu_bg_brown')
        bg_surf = image_mods.make_translucent(bg_surf, 0.1)
        bg_surf.blit(buttons[0], (20 - buttons[0].get_width()//2, 18 - buttons[0].get_height()))
        bg_surf.blit(buttons[1], (20 - buttons[1].get_width()//2, 32 - buttons[1].get_height()))
        for idx, command in enumerate(commands):
            font.blit(command, bg_surf, (38, idx * 16 + 3))
        return bg_surf

    def take_input(self, event):
        first_push = self.fluid.update()
        directions = self.fluid.get_directions()

        self.menu.handle_mouse()
        if 'DOWN' in directions:
            if self.menu.move_down(first_push):
                get_sound_thread().play_sfx('Select 5')
        elif 'UP' in directions:
            if self.menu.move_up(first_push):
                get_sound_thread().play_sfx('Select 5')
        elif 'LEFT' in directions:
            if self.menu.move_left(first_push):
                get_sound_thread().play_sfx('Select 5')
        elif 'RIGHT' in directions:
            if self.menu.move_right(first_push):
                get_sound_thread().play_sfx('Select 5')

        if event == 'SELECT':
            unit = self.menu.get_current()
            game.memory['current_unit'] = unit
            if self.name == 'base_manage':
                game.state.change('base_manage_select')
            else:
                game.state.change('prep_manage_select')
            get_sound_thread().play_sfx('Select 1')
        elif event == 'BACK':
            game.state.change('transition_pop')
            get_sound_thread().play_sfx('Select 4')
        elif event == 'INFO':
            get_sound_thread().play_sfx('Select 1')
            game.memory['scroll_units'] = game.get_units_in_party()
            game.memory['current_unit'] = self.menu.get_current()
            game.memory['next_state'] = 'info_menu'
            game.state.change('transition_to')
        elif event == 'START':
            get_sound_thread().play_sfx('Select 1')
            # convoy_funcs.optimize_all()
            if game.game_vars.get('_convoy'):
                game.state.change('optimize_all_choice')
            else:
                game.alerts.append(banner.Custom("Convoy not available"))
                game.state.change('alert')

    def update(self):
        self.menu.update()

    def draw(self, surf):
        if self.bg:
            self.bg.draw(surf)
        self.menu.draw(surf)
        menus.draw_unit_items(surf, (6, 72), self.menu.get_current(), include_face=True, shimmer=2)
        surf.blit(self.quick_disp, (WINWIDTH//2 + 10, WINHEIGHT//2 + 9))
        draw_funds(surf)
        return surf


class OptimizeAllChoiceState(State):
    name = 'optimize_all_choice'
    transparent = True
    bg_surf = None

    def start(self):
        options = ['Yes', 'No']
        self.menu = menus.Choice(None, options, 'center', None)  # Clear background
        self.menu.set_horizontal(True)

        width = sum(option.width() + 8 for option in self.menu.options) + 16
        owidth = FONT['text'].width('Optimize All?') + 8
        self.bg_surf = base_surf.create_base_surf(max(width, owidth), 40)
        FONT['text'].blit('Optimize All?', self.bg_surf, (self.bg_surf.get_width()//2 - owidth//2 + 4, 4))

    def take_input(self, event):
        self.menu.handle_mouse()
        if event == 'RIGHT':
            if self.menu.move_down():
                get_sound_thread().play_sfx('Select 6')
        elif event == 'LEFT':
            if self.menu.move_up():
                get_sound_thread().play_sfx('Select 6')

        elif event == 'BACK':
            get_sound_thread().play_sfx('Select 4')
            game.state.back()

        elif event == 'SELECT':
            selection = self.menu.get_current()
            if selection == 'Yes':
                get_sound_thread().play_sfx('Select 1')
                convoy_funcs.optimize_all()
            else:
                get_sound_thread().play_sfx('Select 4')
            game.state.back()

    def update(self):
        self.menu.update()

    def draw(self, surf):
        if self.bg_surf:
            surf.blit(self.bg_surf, (WINWIDTH//2 - self.bg_surf.get_width()//2, WINHEIGHT//2 - 28))
        surf = self.menu.draw(surf)
        return surf


class PrepManageSelectState(State):
    name = 'prep_manage_select'

    def start(self):
        self.fluid = FluidScroll()

        self.bg = game.memory['prep_bg']
        self.menu = game.memory['manage_menu']
        self.unit = game.memory['current_unit']
        self.current_index = self.menu.current_index

        options = ['Trade', 'Restock', 'Give all', 'Optimize', 'Use', 'Market']
        # Replace Optimize with Repair when the repair shop is available
        if DB.constants.value('repair_shop'):
            options[3] = 'Repair'
        # Replace Use with Items when the convoy is available
        if game.game_vars.get('_convoy'):
            options[4] = 'Items'
        ignore = self.get_ignore()
        self.select_menu = menus.Table(self.unit, options, (3, 2), (120, 80))
        self.select_menu.set_ignore(ignore)

    def get_ignore(self) -> list:
        ignore = [False, True, True, True, True, True]
        if game.game_vars.get('_convoy'):
            # Turn Optimize and Items on
            ignore = [False, True, True, False, False, True]
            tradeable_items = item_funcs.get_all_tradeable_items(self.unit)
            if tradeable_items:
                ignore[2] = False  # Give all
            if any(convoy_funcs.can_restock(item) for item in tradeable_items):
                ignore[1] = False  # Restock
        else:  # Handle Use
            if any((item_funcs.can_be_used_in_base(self.unit, item) for item in self.unit.items)):
                ignore[4] = False
        if self.name == 'base_manage_select':
            if game.game_vars.get('_base_market') and game.market_items:
                ignore[5] = False
        else:
            if game.game_vars.get('_prep_market') and game.market_items:
                ignore[5] = False
        if DB.constants.value('repair_shop'):
            ignore[3] = not game.game_vars.get('_repair_shop', True) or not item_funcs.has_repair(self.unit)
        if skill_system.no_trade(self.unit):
            ignore[0] = True
        return ignore

    def begin(self):
        self.fluid.reset_on_change_state()
        ignore = self.get_ignore()
        self.select_menu.set_ignore(ignore)
        self.menu.move_to(self.current_index)

    def take_input(self, event):
        first_push = self.fluid.update()
        directions = self.fluid.get_directions()

        self.select_menu.handle_mouse()
        # As on the GBA (sub_80996E8), moving among the commands makes the grid's sound
        if 'DOWN' in directions:
            if self.select_menu.move_down(first_push):
                get_sound_thread().play_sfx('Select 5')
        elif 'UP' in directions:
            if self.select_menu.move_up(first_push):
                get_sound_thread().play_sfx('Select 5')
        elif 'RIGHT' in directions:
            if self.select_menu.move_right(first_push):
                get_sound_thread().play_sfx('Select 5')
        elif 'LEFT' in directions:
            if self.select_menu.move_left(first_push):
                get_sound_thread().play_sfx('Select 5')

        if event == 'SELECT':
            get_sound_thread().play_sfx('Select 1')
            choice = self.select_menu.get_current()
            if choice == 'Trade':
                game.state.change('prep_trade_select')
            elif choice == 'Give all':
                tradeable_items = item_funcs.get_all_tradeable_items(self.unit)
                for item in tradeable_items:
                    convoy_funcs.store_item(item, self.unit)
                # Could have given away an item that would let us Restock/Repair/Use etc.
                # Recheck what should be ignored
                self.select_menu.set_ignore(self.get_ignore())
            elif choice == 'Items':
                if self.name.startswith('base'):
                    game.memory['next_state'] = 'base_items'
                else:
                    game.memory['next_state'] = 'prep_items'
                game.state.change('transition_to')
            elif choice == 'Restock':
                game.state.change('prep_restock')
            elif choice == 'Optimize':
                convoy_funcs.optimize(self.unit)
            elif choice == 'Market':
                game.memory['next_state'] = 'prep_market'
                game.state.change('transition_to')
            elif choice == 'Repair':
                game.memory['next_state'] = 'repair_shop'
                game.state.change('transition_to')
            elif choice == 'Use':
                game.state.change('prep_use')

        elif event == 'BACK':
            get_sound_thread().play_sfx('Select 4')
            game.state.back()

    def update(self):
        self.menu.update()
        self.select_menu.update()

    def draw(self, surf):
        if self.bg:
            self.bg.draw(surf)
        self.menu.draw(surf)
        menus.draw_unit_items(surf, (6, 72), self.unit, include_face=True, include_top=True, shimmer=2)
        self.select_menu.draw(surf)
        draw_funds(surf)
        return surf


class PrepTradeSelectState(State):
    name = 'prep_trade_select'

    def start(self):
        self.fluid = FluidScroll()

        self.menu = game.memory['manage_menu']
        self.bg = game.memory['prep_bg']
        self.unit = game.memory['current_unit']
        self.current_index = self.menu.current_index
        self.menu.set_fake_cursor(self.current_index)

        if game.state.from_transition():
            game.state.change('transition_in')
            return 'repeat'

    def begin(self):
        self.fluid.reset_on_change_state()

    def take_input(self, event):
        first_push = self.fluid.update()
        directions = self.fluid.get_directions()

        self.menu.handle_mouse()
        if 'DOWN' in directions:
            if self.menu.move_down(first_push):
                get_sound_thread().play_sfx('Select 5')
        elif 'UP' in directions:
            if self.menu.move_up(first_push):
                get_sound_thread().play_sfx('Select 5')
        elif 'LEFT' in directions:
            if self.menu.move_left(first_push):
                get_sound_thread().play_sfx('Select 5')
        elif 'RIGHT' in directions:
            if self.menu.move_right(first_push):
                get_sound_thread().play_sfx('Select 5')

        if event == 'SELECT':
            unit2 = self.menu.get_current()
            if skill_system.no_trade(unit2):
                get_sound_thread().play_sfx('Error')
            else:
                game.memory['unit1'] = self.unit
                game.memory['unit2'] = unit2
                game.memory['next_state'] = 'prep_trade'
                game.state.change('transition_to')

        elif event == 'BACK':
            get_sound_thread().play_sfx('Select 4')
            game.state.change('transition_pop')

        elif event == 'INFO':
            get_sound_thread().play_sfx('Select 1')
            game.memory['scroll_units'] = game.get_units_in_party()
            game.memory['current_unit'] = self.menu.get_current()
            game.memory['next_state'] = 'info_menu'
            game.state.change('transition_to')

    def update(self):
        self.menu.update()

    def draw(self, surf):
        if self.bg:
            self.bg.draw(surf)
        menus.draw_unit_items(surf, (6, 72), self.unit, include_face=True, shimmer=2)
        menus.draw_unit_items(surf, (126, 72), self.menu.get_current(), include_face=True, right=False, shimmer=2)

        self.menu.draw(surf)

        return surf

    def finish(self):
        self.menu.set_fake_cursor(None)


class PrepItemsState(State):
    name = 'prep_items'

    trade_name_surf = SPRITES.get('trade_name')

    def start(self):
        self.fluid = FluidScroll()

        self.bg = game.memory.get('prep_bg')
        if not self.bg:
            self.bg = background.create_background('rune_background')
        self.unit = game.memory['current_unit']
        include_other_units_items = game.memory.get('include_other_units', False) or (self.name != 'supply_items')
        game.memory['include_other_units'] = False  # Reset
        self.menu = menus.Convoy(self.unit, (WINWIDTH - 116, 40), include_other_units_items)

        self.state = 'free'
        self.sub_menu = None

        self._proceed_with_targets_item = False

        game.state.change('transition_in')
        return 'repeat'

    def begin(self):
        if self._proceed_with_targets_item:
            self.state = 'free'
            self._proceed_with_targets_item = False
            if game.memory.get('item') and game.memory.get('item').data.get('target_item'):
                item = game.memory.get('item')
                action.do(action.HasTraded(self.unit))
                interaction.start_combat(self.unit, None, item)
                return 'repeat'

        self.fluid.reset_on_change_state()
        self.menu.update_options()
        if self.name.startswith('base'):
            base_music = game.game_vars.get('_base_music')
            if base_music:
                get_sound_thread().fade_in(base_music)

    def take_input(self, event):
        first_push = self.fluid.update()
        directions = self.fluid.get_directions()

        # As on the GBA, nothing can be done while a page of the convoy slides in
        if self.menu.is_sliding():
            return

        if self.state in ('free', 'trade_convoy', 'trade_inventory'):
            self.menu.handle_mouse()
            if 'DOWN' in directions:
                if self.menu.move_down(first_push):
                    get_sound_thread().play_sfx('Select 6')
            elif 'UP' in directions:
                if self.menu.move_up(first_push):
                    get_sound_thread().play_sfx('Select 6')
            elif 'LEFT' in directions:
                if self.menu.move_left(first_push):
                    get_sound_thread().play_sfx('TradeRight')
            elif 'RIGHT' in directions:
                if self.menu.move_right(first_push):
                    get_sound_thread().play_sfx('TradeRight')
        elif self.sub_menu:
            self.sub_menu.handle_mouse()
            if 'DOWN' in directions:
                if self.sub_menu.move_down(first_push):
                    get_sound_thread().play_sfx('Select 6')
            elif 'UP' in directions:
                if self.sub_menu.move_up(first_push):
                    get_sound_thread().play_sfx('Select 6')

        if event == 'SELECT':
            get_sound_thread().play_sfx('Select 1')
            if self.state == 'free':
                current = self.menu.get_current()
                context = self.menu.get_context()
                if context == 'inventory':
                    if current:
                        self.state = 'owner_item'
                        options = []
                        if item_system.storeable(self.unit, current):
                            options.append('Store')
                        if item_system.tradeable(self.unit, current):
                            options.append('Trade')
                        if self.name != 'supply_items' and \
                                item_funcs.can_be_used_in_base(self.unit, current):
                            options.append('Use')
                        if convoy_funcs.can_restock(current):
                            options.append('Restock')
                        if not options:
                            options.append('Nothing')
                        top = self.menu.get_current_index() * 16 + 68 - 8 * len(options)
                        left = 96
                        top = min(top, WINHEIGHT - 4 - 16 * len(options))
                        self.sub_menu = menus.Choice(current, options, (left, top))
                    else:
                        self.menu.move_to_convoy()
                elif context == 'convoy':
                    if current:
                        if self.name != 'supply_items' and \
                                item_funcs.can_be_used_in_base(self.unit, current):
                            self.state = 'convoy_item'
                            topleft = (80, (self.menu.get_current_index() - self.menu.get_scrolled_index()) * 16 + 36)
                            if item_funcs.inventory_full(self.unit, current):
                                options = ['Trade', 'Use']
                            else:
                                options = ['Take', 'Use']
                            self.sub_menu = menus.Choice(current, options, topleft)
                        else:
                            action.do(action.HasTraded(self.unit))
                            if item_funcs.inventory_full(self.unit, current):
                                self.state = 'trade_inventory'
                                self.menu.move_to_inventory()
                            else:
                                if current.owner_nid:
                                    unit = game.get_unit(current.owner_nid)
                                    convoy_funcs.give_item(current, unit, self.unit)
                                else:
                                    convoy_funcs.take_item(current, self.unit)
                                self.menu.update_options()
                    else:
                        pass  # Nothing happens

            elif self.state == 'owner_item':
                current = self.sub_menu.get_current()
                item = self.menu.get_current()
                if current == 'Store':
                    action.do(action.HasTraded(self.unit))
                    convoy_funcs.store_item(item, self.unit)
                    self.menu.update_options()
                    self.menu.move_to_item_type(item)
                    self.state = 'free'
                elif current == 'Trade':
                    self.state = 'trade_convoy'
                    self.menu.move_to_convoy()
                    self.menu.update_options()
                elif current == 'Use':
                    if item_system.targets_items(self.unit, item):
                        game.memory['target'] = self.unit
                        game.memory['item'] = item
                        self._proceed_with_targets_item = True
                        game.state.change('item_targeting')
                    else:
                        action.do(action.HasTraded(self.unit))
                        interaction.start_combat(self.unit, None, item)
                        self.state = 'free'
                elif current == 'Restock':
                    action.do(action.HasTraded(self.unit))
                    convoy_funcs.restock(item)
                    self.menu.update_options()
                    self.state = 'free'
                elif current == 'Nothing':
                    self.state = 'free'
                self.sub_menu = None

            elif self.state == 'convoy_item':
                current = self.sub_menu.get_current()
                item = self.menu.get_current()
                if current == 'Take':
                    action.do(action.HasTraded(self.unit))
                    if item.owner_nid:
                        unit = game.get_unit(item.owner_nid)
                        convoy_funcs.give_item(item, unit, self.unit)
                    else:
                        convoy_funcs.take_item(item, self.unit)
                    self.state = 'free'
                elif current == 'Trade':
                    self.state = 'trade_inventory'
                    self.menu.move_to_inventory()
                elif current == 'Use':
                    if item_system.targets_items(self.unit, item):
                        game.memory['target'] = self.unit
                        game.memory['item'] = item
                        self._proceed_with_targets_item = True
                        game.state.change('item_targeting')
                    else:
                        action.do(action.HasTraded(self.unit))
                        interaction.start_combat(self.unit, None, item)
                        self.state = 'free'
                elif current == 'Nothing':
                    self.state = 'free'
                self.sub_menu = None
                self.menu.update_options()

            elif self.state == 'trade_convoy':
                unit_item = self.menu.get_inventory_current()
                convoy_item = self.menu.get_convoy_current()
                if trade.check_trade(unit_item, self.unit, convoy_item, None):
                    action.do(action.HasTraded(self.unit))
                    convoy_funcs.trade_items(convoy_item, unit_item, self.unit)
                    self.menu.unlock()
                    self.menu.update_options()
                    self.state = 'free'
                else:
                    get_sound_thread().play_sfx('Error')

            elif self.state == 'trade_inventory':
                convoy_item = self.menu.get_convoy_current()
                unit_item = self.menu.get_inventory_current()
                if trade.check_trade(unit_item, self.unit, convoy_item, None):
                    action.do(action.HasTraded(self.unit))
                    convoy_funcs.trade_items(convoy_item, unit_item, self.unit)
                    self.menu.unlock()
                    self.menu.update_options()
                    self.state = 'free'
                else:
                    get_sound_thread().play_sfx('Error')

        elif event == 'BACK':
            if self.menu.info_flag:
                self.menu.toggle_info()
                get_sound_thread().play_sfx('Info Out')
            elif self.state == 'free':
                get_sound_thread().play_sfx('Select 4')
                game.state.change('transition_pop')
            elif self.state == 'owner_item':
                self.sub_menu = None
                self.state = 'free'
            elif self.state == 'convoy_item':
                self.sub_menu = None
                self.state = 'free'
            elif self.state == 'trade_convoy':
                self.menu.move_to_inventory()
                self.menu.unlock()
                self.menu.update_options()
                self.state = 'free'
            elif self.state == 'trade_inventory':
                self.menu.move_to_convoy()
                self.menu.unlock()
                self.menu.update_options()
                self.state = 'free'

        elif event == 'AUX':
            if self.menu.next_help_page():
                get_sound_thread().play_sfx('Select 6')

        elif event == 'INFO':
            if self.state in ('free', 'trade_convoy', 'trade_inventory'):
                self.menu.toggle_info()
                if self.menu.info_flag:
                    get_sound_thread().play_sfx('Info In')
                else:
                    get_sound_thread().play_sfx('Info Out')

    def update(self):
        self.menu.update()
        if self.sub_menu:
            self.sub_menu.update()

    def draw(self, surf):
        if self.bg:
            self.bg.draw(surf)
        self.menu.draw(surf)
        if self.sub_menu:
            self.sub_menu.draw(surf)
        if self.menu.info_flag:
            self.menu.draw_info(surf)
        return surf


class PrepRestockState(State):
    name = 'prep_restock'

    def start(self):
        self.fluid = FluidScroll()

        self.bg = game.memory['prep_bg']
        self.unit = game.memory['current_unit']
        self.unit_menu = game.memory['manage_menu']

        topleft = (6, 72)
        self.menu = menus.Inventory(self.unit, self.unit.items, topleft)
        # ignore = [not convoy_funcs.can_restock(item) for item in self.unit.items]
        ignore = [not convoy_funcs.can_restock(option.get()) if option.get() else True for option in self.menu.options]
        self.menu.set_ignore(ignore)

    def begin(self):
        self.fluid.reset_on_change_state()

    def take_input(self, event):
        first_push = self.fluid.update()
        directions = self.fluid.get_directions()

        self.menu.handle_mouse()
        if 'DOWN' in directions:
            get_sound_thread().play_sfx('Select 5')
            self.menu.move_down(first_push)
        elif 'UP' in directions:
            get_sound_thread().play_sfx('Select 5')
            self.menu.move_up(first_push)

        if event == 'SELECT':
            get_sound_thread().play_sfx('Select 1')
            item = self.menu.get_current()
            convoy_funcs.restock(item)
            true_ignore = [not convoy_funcs.can_restock(item) for item in self.unit.items]
            ignore = [not convoy_funcs.can_restock(option.get()) if option.get() else True for option in self.menu.options]
            if all(true_ignore):
                self.menu.set_ignore(ignore)
                game.state.back()
            else:
                self.menu.set_ignore(ignore)

        elif event == 'BACK':
            get_sound_thread().play_sfx('Select 4')
            game.state.back()

        elif event == 'AUX':
            if self.menu.next_help_page():
                get_sound_thread().play_sfx('Select 6')

        elif event == 'INFO':
            self.menu.toggle_info()
            if self.menu.info_flag:
                get_sound_thread().play_sfx('Info In')
            else:
                get_sound_thread().play_sfx('Info Out')

    def update(self):
        self.menu.update()
        self.unit_menu.update()

    def draw(self, surf):
        if self.bg:
            self.bg.draw(surf)
        self.unit_menu.draw(surf)
        self.menu.draw(surf)
        return surf


class PrepUseState(State):
    name = 'prep_use'

    def start(self):
        self.fluid = FluidScroll()

        self.bg = game.memory['prep_bg']
        self.unit = game.memory['current_unit']
        self.unit_menu = game.memory['manage_menu']

        self._proceed_with_targets_item = False

        topleft = (6, 72)
        self.menu = menus.Inventory(self.unit, self.unit.items, topleft)

    def begin(self):
        if self._proceed_with_targets_item:
            self._proceed_with_targets_item = False
            if game.memory.get('item') and game.memory.get('item').data.get('target_item'):
                item = game.memory.get('item')
                action.do(action.HasTraded(self.unit))
                interaction.start_combat(self.unit, None, item)
                return 'repeat'

        self.fluid.reset_on_change_state()
        self.menu.update_options(self.unit.items)
        ignore = self.get_ignore()
        self.menu.set_ignore(ignore)
        if all(ignore):
            game.state.back()

    def get_ignore(self) -> List[bool]:
        items = [option.get() for option in self.menu.options]
        ignore = [not item_funcs.can_be_used_in_base(self.unit, item)
                  for item in items]
        return ignore

    def take_input(self, event):
        first_push = self.fluid.update()
        directions = self.fluid.get_directions()

        self.menu.handle_mouse()
        if 'DOWN' in directions:
            get_sound_thread().play_sfx('Select 5')
            self.menu.move_down(first_push)
        elif 'UP' in directions:
            get_sound_thread().play_sfx('Select 5')
            self.menu.move_up(first_push)

        if event == 'SELECT':
            get_sound_thread().play_sfx('Select 1')
            item = self.menu.get_current()
            # Actually Use item
            if item_system.targets_items(self.unit, item):
                game.memory['target'] = self.unit
                game.memory['item'] = item
                self._proceed_with_targets_item = True
                game.state.change('item_targeting')
            else:
                action.do(action.HasTraded(self.unit))
                interaction.start_combat(self.unit, None, item)

        elif event == 'BACK':
            get_sound_thread().play_sfx('Select 4')
            game.state.back()

        elif event == 'AUX':
            if self.menu.next_help_page():
                get_sound_thread().play_sfx('Select 6')

        elif event == 'INFO':
            self.menu.toggle_info()
            if self.menu.info_flag:
                get_sound_thread().play_sfx('Info In')
            else:
                get_sound_thread().play_sfx('Info Out')

    def update(self):
        self.menu.update()
        self.unit_menu.update()

    def draw(self, surf):
        if self.bg:
            self.bg.draw(surf)
        self.unit_menu.draw(surf)
        self.menu.draw(surf)
        return surf


class PrepMarketState(State):
    name = 'prep_market'

    def start(self):
        self.fluid = FluidScroll()

        self.bg = game.memory.get('prep_bg') or background.create_background('rune_background')
        units = game.get_units_in_party()
        self.unit = game.memory.get('current_unit') or (units[0] if units else None)

        # menus.Market exige um UnitObject válido como owner para desenhar a aba e paginar o Comboio
        self.sell_menu = menus.Market(self.unit, None, (WINWIDTH - 164, 40), disp_value='sell')
        market_items = item_funcs.create_items(self.unit, game.market_items.keys())
        show_stock = any(stock >= 0 for stock in game.market_items.values())
        self.buy_menu = menus.Market(self.unit, market_items, (WINWIDTH - 164, 40), disp_value='buy', show_stock=show_stock)
        self.display_menu = self.buy_menu
        self.sell_menu.set_takes_input(False)
        self.buy_menu.set_takes_input(False)

        options = ["Buy", "Sell"]
        # None no Choice evita duplicar a plaqueta de nome acima de Buy / Sell
        self.choice_menu = menus.Choice(None, options, (20, 24), 'menu_bg_brown')
        self.choice_menu.gem = False
        self.menu = self.choice_menu

        self.state = 'free'  # 'free', 'buy', 'sell'
        self.money_counter_disp = gui.PopUpDisplay((66, WINHEIGHT - 40))

        # Estado da janela de confirmação
        self.confirming = False
        self.confirm_mode = None   # 'buy' ou 'sell'
        self.confirm_item = None
        self.confirm_price = 0
        self.confirm_idx = 0       # 0 = Yes | 1 = No
        self.confirm_cursor = menus.Cursor()

        game.state.change('transition_in')
        return 'repeat'

    def begin(self):
        self.fluid.reset_on_change_state()

    def update_options(self):
        self.buy_menu.update_options()
        self.sell_menu.update_options()

    def _open_confirm(self, mode: str, item, price: int):
        self.confirming = True
        self.confirm_mode = mode
        self.confirm_item = item
        self.confirm_price = price
        self.confirm_idx = 0

    def _close_confirm(self):
        self.confirming = False
        self.confirm_mode = None
        self.confirm_item = None
        self.confirm_price = 0
        self.confirm_idx = 0

    def _execute_buy(self, item, value: int):
        get_sound_thread().play_sfx('GoldExchange')
        game.set_money(game.get_money() - value)
        action.do(action.UpdateRecords('money', (game.current_party, -value)))
        self.money_counter_disp.start(-value)
        self.menu.decrement_stock()
        if isinstance(game.market_items, dict) and item.nid in game.market_items:
            game.market_items[item.nid] -= 1

        # Envia a compra diretamente para o Comboio
        new_item = item_funcs.create_item(None, item.nid)
        game.register_item(new_item)
        action.PutItemInConvoy(new_item).do()
        self.update_options()

    def _execute_sell(self, item, value: int):
        get_sound_thread().play_sfx('GoldExchange')
        game.set_money(game.get_money() + value)
        action.do(action.UpdateRecords('money', (game.current_party, value)))
        self.money_counter_disp.start(value)
        if item.owner_nid:
            owner = game.get_unit(item.owner_nid)
            action.RemoveItem(owner, item).do()
        else:
            action.RemoveItemFromConvoy(item).do()
        self.update_options()

    def take_input(self, event):
        first_push = self.fluid.update()
        directions = self.fluid.get_directions()

        # ---------------------------------------------------------------------
        # 1. Input da Tela de Confirmação (Yes / No)
        # ---------------------------------------------------------------------
        if self.confirming:
            if ('LEFT' in directions or 'UP' in directions) and first_push:
                if self.confirm_idx != 0:
                    self.confirm_idx = 0
                    get_sound_thread().play_sfx('Select 5')
            elif ('RIGHT' in directions or 'DOWN' in directions) and first_push:
                if self.confirm_idx != 1:
                    self.confirm_idx = 1
                    get_sound_thread().play_sfx('Select 5')

            if event == 'BACK':
                get_sound_thread().play_sfx('Select 4')
                self._close_confirm()

            elif event == 'SELECT':
                if self.confirm_idx == 0:
                    mode = self.confirm_mode
                    item = self.confirm_item
                    price = self.confirm_price
                    self._close_confirm()
                    if mode == 'buy':
                        self._execute_buy(item, price)
                    elif mode == 'sell':
                        self._execute_sell(item, price)
                else:
                    get_sound_thread().play_sfx('Select 4')
                    self._close_confirm()
            return

        # ---------------------------------------------------------------------
        # 2. Input Normal da Loja
        # ---------------------------------------------------------------------
        if self.display_menu.is_sliding():
            return

        self.menu.handle_mouse()
        if 'DOWN' in directions:
            if self.menu.move_down(first_push):
                get_sound_thread().play_sfx('Select 6')
            if self.state == 'free':
                current = self.menu.get_current()
                self.display_menu = self.buy_menu if current == 'Buy' else self.sell_menu
        elif 'UP' in directions:
            if self.menu.move_up(first_push):
                get_sound_thread().play_sfx('Select 6')
            if self.state == 'free':
                current = self.menu.get_current()
                self.display_menu = self.buy_menu if current == 'Buy' else self.sell_menu
        elif 'LEFT' in directions:
            get_sound_thread().play_sfx('TradeRight')
            self.display_menu.move_left(first_push)
        elif 'RIGHT' in directions:
            get_sound_thread().play_sfx('TradeRight')
            self.display_menu.move_right(first_push)

        if event == 'SELECT':
            if self.state == 'buy':
                item = self.menu.get_current()
                if item:
                    value = item_funcs.buy_price(self.unit, item)
                    if game.get_money() - value >= 0 and self.menu.get_stock() != 0:
                        get_sound_thread().play_sfx('Select 1')
                        self._open_confirm('buy', item, value)
                    else:
                        get_sound_thread().play_sfx('Select 4')
                else:
                    get_sound_thread().play_sfx('Select 4')

            elif self.state == 'sell':
                item = self.menu.get_current()
                if item:
                    value = item_funcs.sell_price(self.unit, item)
                    if value:
                        get_sound_thread().play_sfx('Select 1')
                        self._open_confirm('sell', item, value)
                    else:
                        get_sound_thread().play_sfx('Select 4')
                else:
                    get_sound_thread().play_sfx('Select 4')

            elif self.state == 'free':
                current = self.menu.get_current()
                if current == 'Buy':
                    self.menu = self.buy_menu
                    self.state = 'buy'
                    self.display_menu = self.buy_menu
                else:
                    self.menu = self.sell_menu
                    self.state = 'sell'
                    self.display_menu = self.sell_menu
                self.menu.set_takes_input(True)

        elif event == 'BACK':
            if self.state == 'buy' or self.state == 'sell':
                if self.menu.info_flag:
                    self.menu.toggle_info()
                    get_sound_thread().play_sfx('Info Out')
                else:
                    get_sound_thread().play_sfx('Select 4')
                    self.state = 'free'
                    self.menu.set_takes_input(False)
                    self.menu = self.choice_menu
            else:
                get_sound_thread().play_sfx('Select 4')
                game.state.change('transition_pop')

        elif event == 'AUX':
            if self.menu.next_help_page():
                get_sound_thread().play_sfx('Select 6')

        elif event == 'INFO':
            if self.state == 'buy' or self.state == 'sell':
                self.menu.toggle_info()
                if self.menu.info_flag:
                    get_sound_thread().play_sfx('Info In')
                else:
                    get_sound_thread().play_sfx('Info Out')

    def update(self):
        if self.confirming:
            self.confirm_cursor.update()
        else:
            self.menu.update()

    def _draw_confirm_modal(self, surf):
        from app.engine import icons

        box_w, box_h = 144, 64
        box_x = (WINWIDTH - box_w) // 2
        box_y = (WINHEIGHT - box_h) // 2
        box = base_surf.create_base_surf(box_w, box_h, 'menu_bg_base')

        # 1. Título da transação ("Buy for 460G?" / "Sell for 230G?")
        action_word = 'Buy' if self.confirm_mode == 'buy' else 'Sell'
        prompt = f"{action_word} for {self.confirm_price}G?"
        FONT['text-yellow'].blit_center(prompt, box, (box_w // 2, 6))

        # 2. Ícone e nome do item centralizados
        item_name = self.confirm_item.name
        name_w = FONT['text'].width(item_name)
        item_x = max(8, (box_w - (18 + name_w)) // 2)
        icons.draw_item(box, self.confirm_item, (item_x, 20), cooldown=False)
        FONT['text'].blit(item_name, box, (item_x + 18, 22))

        # 3. Opções Yes / No lado a lado
        yes_font = FONT['text-yellow'] if self.confirm_idx == 0 else FONT['text']
        no_font = FONT['text-yellow'] if self.confirm_idx == 1 else FONT['text']
        yes_font.blit('Yes', box, (40, 42))
        no_font.blit('No', box, (94, 42))

        surf.blit(box, (box_x, box_y))

        # 4. Cursor nativo apontando para a opção ativa
        cursor_x = (box_x + 24) if self.confirm_idx == 0 else (box_x + 78)
        cursor_y = box_y + 42
        self.confirm_cursor.draw(surf, cursor_x, cursor_y)

    def draw(self, surf):
        if self.bg:
            self.bg.draw(surf)
        self.choice_menu.draw(surf)
        self.display_menu.draw(surf)

        # Money
        surf.blit(SPRITES.get('funds_display'), (10, WINHEIGHT - 24))
        money = str(game.get_money())
        FONT['text-blue'].blit_right(money, surf, (61, WINHEIGHT - 20))
        self.money_counter_disp.draw(surf)

        if self.display_menu.info_flag:
            self.display_menu.draw_info(surf)

        if self.confirming and self.confirm_item:
            self._draw_confirm_modal(surf)

        return surf