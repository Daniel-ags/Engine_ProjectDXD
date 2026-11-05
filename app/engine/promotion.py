from app.constants import WINWIDTH, WINHEIGHT

from app.data.database.database import DB
from app.data.resources.resources import RESOURCES
from app.utilities import utils

from app.engine.fonts import FONT
from app.engine.sprites import SPRITES
from app.engine.sound import get_sound_thread
from app.engine.state import State
from app.engine import background, menus, engine, dialog, text_funcs, icons, \
    action, item_system, battle_animation, base_surf, help_menu
from app.engine.combat.mock_combat import MockCombat
from app.engine.game_state import game
from app.engine.fluid_scroll import FluidScroll
from app.engine.graphics.text.text_renderer import render_text

class PromotionChoiceState(State):
    name = 'promotion_choice'
    bg = None

    def __init__(self, name=None):
        self.name = name
        self.bg = background.create_background('settings_background')

    def _get_choices(self):
        self.class_options = game.memory.get('promo_options', None) or self.unit_klass.turns_into
        game.memory['promo_options'] = None
        return [DB.classes.get(c).name for c in self.class_options]

    def _proceed(self, next_class):
        game.memory['current_unit'] = self.unit
        game.memory['next_class'] = next_class
        game.memory['next_state'] = 'promotion'
        if self.from_map_combat:
            game.memory['_promo_finalize_turn'] = True
        game.state.change('transition_to_with_pop')

    def start(self):
        self.fluid = FluidScroll()

        self.can_go_back = game.memory.get('can_go_back', False)
        game.memory['can_go_back'] = None
        self.from_map_combat = game.memory.get('_promo_map_combat', False)
        game.memory['_promo_map_combat'] = None
        self.combat_item = game.memory.get('combat_item')
        game.memory['combat_item'] = None
        self.unit = game.memory['current_unit']
        self.unit_klass = DB.classes.get(self.unit.klass)
        display_options = self._get_choices()

        # Flag de alternância entre Tela 1 (Seleção) e Tela 2 (Detalhes)
        self.in_details = False

        # Gerenciador de inspeção com botão R
        self.inspector = None
        self.class_details_items = []

        # Menu de Classes (Tela 1) - posicionado em (14, 46) com limite de 3
        options = [DB.classes.get(c_nid).name for c_nid in self.class_options]
        self.menu = menus.Choice(self.unit, options, (10, 46))
        self.menu.set_limit(3)
        self.child_menu = None

        # Cabeçalho Superior Centralizado da Tela 1 (Ornate com tamanho modular)
        header_text = "Choose your promotion!"
        text_w = FONT['text'].width(header_text)
        header_w = ((text_w + 16 + 7) // 8) * 8
        header_h = 24
        self.header_surf = base_surf.create_ornate_base_surf(header_w, header_h, 'menu_bg_base', gems='all')
        off_x, off_y = 2, 4
        title_x = off_x + (header_w - text_w) // 2
        render_text(self.header_surf, ['text'], [header_text], ['new-white'], (title_x, off_y + 3))
        self.header_pos = ((WINWIDTH - header_w) // 2 - 2, 8 - 4)

        # Pré-carregamento dos elementos visuais e cards da Tela 2
        self.animations = []
        self.weapon_icons = []
        self.skill_cards = []
        self.name_cards = []

        for option in self.class_options:
            anim = battle_animation.get_battle_anim(self.unit, None, klass=option)
            if anim:
                # True: combatente direito olhando para a esquerda
                anim.pair(self, None, True, 0)
            self.animations.append(anim)

            klass = DB.classes.get(option)

            weapons = []
            for weapon_nid, weapon in klass.wexp_gain.items():
                if weapon.usable:
                    weapons.append(weapon_nid)
            self.weapon_icons.append(weapons)

            immediate_skills = [
                DB.skills.get(s_nid)
                for req_lvl, s_nid in klass.learned_skills
                if req_lvl <= 1 and DB.skills.get(s_nid)
            ]

            # Salva os itens em ordem para navegação com o botão R
            items = [('skill', s) for s in immediate_skills] + [('weapon', w) for w in weapons]
            self.class_details_items.append(items)

            # Cards da Tela 2
            self.skill_cards.append(self._create_skills_card(immediate_skills, weapons))
            self.name_cards.append(self._create_name_card(klass.name))

        # Plataforma Melee (Duas metades unidas)
        if game.tilemap and self.unit.position:
            terrain = game.tilemap.get_terrain(self.unit.position)
            platform_type = DB.terrain.get(terrain).platform
        else:
            platform_type = 'Floor'
        platform = RESOURCES.platforms.get(
            platform_type + '-Melee',
            RESOURCES.platforms.get('Arena-Melee', RESOURCES.platforms.get(platform_type + '-Ranged', RESOURCES.platforms.get('Arena-Ranged')))
        )
        self.left_platform = engine.image_load(platform)
        self.right_platform = engine.flip_horiz(self.left_platform.copy())

        self.anim_offset = 120
        self.target_anim_offset = False

        self.current_desc = self._get_desc()

    def begin(self):
        self.fluid.reset_on_change_state()

    def _get_desc(self):
        current_klass = self.class_options[self.menu.get_current_index()]
        klass = DB.classes.get(current_klass)
        text = text_funcs.translate_and_text_evaluate(klass.desc, self=klass)
        d = dialog.Dialog(text.replace('\n', '{br}'))
        d.position = (6, 112)
        d.text_width = WINWIDTH - 28
        d.width = d.text_width + 16
        d.font_type = 'convo'
        d.font_color = 'white'
        d.font = FONT['convo-white']
        d.draw_cursor_flag = False
        d.reformat()
        return d

    def _create_name_card(self, klass_name):
        title_w = FONT['text'].width(klass_name)
        card_w = max(48, min(WINWIDTH - 16, ((title_w + 16 + 7) // 8) * 8))
        card_h = 24
        card_surf = base_surf.create_ornate_base_surf(card_w, card_h, 'menu_bg_base', gems='all')
        off_x, off_y = 2, 4

        title_x = off_x + (card_w - title_w) // 2
        render_text(card_surf, ['text'], [klass_name], ['text-yellow'], (title_x, off_y + 3))
        return card_surf, card_w, card_h

    def _create_skills_card(self, skills, weapons=None):
        weapons = weapons or []
        title_text = "Skills & Weapons"
        title_w = FONT['text'].width(title_text)

        icon_pitch = 18
        total_icons = len(skills) + len(weapons)
        total_content_w = total_icons * icon_pitch - 2 if total_icons > 0 else FONT['text'].width("---")
        content_w = max(title_w, total_content_w)
        card_w = ((content_w + 12 + 7) // 8) * 8
        card_h = 40

        card_surf = base_surf.create_ornate_base_surf(card_w, card_h, 'menu_bg_base', gems='all')
        off_x, off_y = 2, 4

        title_x = off_x + (card_w - title_w) // 2
        render_text(card_surf, ['text'], [title_text], ['new-white'], (title_x, off_y + 3))

        start_x = off_x + (card_w - total_content_w) // 2
        icons_y = off_y + 18
        curr_x = start_x

        if skills:
            for skill in skills:
                icons.draw_skill(card_surf, skill, (curr_x, icons_y))
                curr_x += icon_pitch
        elif not weapons:
            render_text(card_surf, ['text'], ["---"], ['gray'], (curr_x, icons_y))

        if weapons:
            for weapon in weapons:
                icons.draw_weapon(card_surf, weapon, (curr_x, icons_y))
                curr_x += icon_pitch

        return card_surf, card_w, card_h

    def _draw_stat_bonuses(self, surf, klass):
        promo_gains = klass.promotion if hasattr(klass, 'promotion') and klass.promotion else {}
        bonus_list = []

        # 1. Coleta os atributos que sofrem alteração (excluindo MOV)
        for stat in DB.stats:
            if stat.nid == 'MOV':
                continue
            val = promo_gains.get(stat.nid, 0)
            if val != 0 and abs(val) < 50:
                bonus_list.append((stat.nid, val))

        for stat_nid, val in promo_gains.items():
            if stat_nid != 'MOV' and val != 0 and abs(val) < 50 and stat_nid not in [b[0] for b in bonus_list]:
                bonus_list.append((stat_nid, val))

        box_x, box_y = 6, 112
        if not bonus_list:
            text = "No stat changes upon promotion."
            render_text(surf, ['text'], [text], ['white'], (box_x + 16, box_y + 16))
            return

        # 2. Formatação em grade: linha 1 (chaves) e linha 2 (valores)
        num_stats = len(bonus_list)
        col_w = min(36, 212 // num_stats)
        total_w = num_stats * col_w
        start_x = box_x + (228 - total_w) // 2

        for col_idx, (s_nid, s_val) in enumerate(bonus_list):
            item_center_x = start_x + col_idx * col_w + col_w // 2

            key_w = FONT['text'].width(s_nid)
            key_x = item_center_x - key_w // 2
            render_text(surf, ['text'], [s_nid], ['white'], (key_x, box_y + 10))

            sign = "+" if s_val > 0 else ""
            val_text = f"{sign}{s_val}"
            val_color = 'green' if s_val > 0 else 'red'
            val_w = FONT['text'].width(val_text)
            val_x = item_center_x - val_w // 2
            render_text(surf, ['text'], [val_text], [val_color], (val_x, box_y + 26))

    def _get_help_targets(self, class_idx):
        """Monta a lista de alvos para o HelpInspector com coordenadas brutas de cada elemento."""
        if not self.skill_cards or class_idx >= len(self.class_details_items):
            return []
        items = self.class_details_items[class_idx]
        if not items:
            return []

        card_surf, card_w, card_h = self.skill_cards[class_idx]
        total_icons = len(items)
        icon_pitch = 18
        total_content_w = total_icons * icon_pitch - 2 if total_icons > 0 else FONT['text'].width("---")

        box_x = 10
        box_y = 50
        start_x = box_x + (card_w - total_content_w) // 2
        icons_y = box_y + 18

        targets = []
        for idx, (item_type, item_obj) in enumerate(items):
            icon_x = start_x + idx * icon_pitch
            icon_y = icons_y

            if item_type == 'skill':
                name = getattr(item_obj, 'name', 'Skill')
                desc = getattr(item_obj, 'desc', '') or "No description."
            else:  # weapon
                w_obj = DB.weapons.get(item_obj) if hasattr(DB, 'weapons') and DB.weapons.get(item_obj) else None
                name = getattr(w_obj, 'name', item_obj)
                desc = getattr(w_obj, 'desc', '') or f"Grants proficiency with {name}s."

            text = f"{name}: {desc}"
            # O HelpInspector aplica automaticamente o recuo nativo de (-12, +2)
            targets.append((icon_x, icon_y, text))

        return targets

    def take_input(self, event):
        first_push = self.fluid.update()
        directions = self.fluid.get_directions()

        # ---------------------------------------------------------------------
        # Tela 2: Detalhes da Promoção
        # ---------------------------------------------------------------------
        if self.in_details:
            # 1. Se a inspeção estiver aberta, delega para o HelpInspector
            if self.inspector:
                if not self.inspector.handle_input(event, directions):
                    self.inspector = None
                return

            # 2. Abertura da inspeção
            if event == 'INFO':
                current_idx = self.menu.get_current_index()
                targets = self._get_help_targets(current_idx)
                if targets:
                    self.inspector = help_menu.HelpInspector(targets, orientation='horizontal')
                return

            if event == 'BACK':
                get_sound_thread().play_sfx('Select 4')
                self.in_details = False
            elif event == 'SELECT':
                get_sound_thread().play_sfx('Select 1')
                self._proceed(self.class_options[self.menu.get_current_index()])
            return

        # ---------------------------------------------------------------------
        # Tela 1: Escolha da Classe
        # ---------------------------------------------------------------------
        current_idx = self.menu.get_current_index()
        self.menu.handle_mouse()
        new_idx = self.menu.get_current_index()
        if current_idx != new_idx:
            self.target_anim_offset = True
            self.current_desc = self._get_desc()

        if 'DOWN' in directions:
            if self.menu.move_down(first_push):
                get_sound_thread().play_sfx('Select 6')
            self.target_anim_offset = True
            self.current_desc = self._get_desc()
        elif 'UP' in directions:
            if self.menu.move_up(first_push):
                get_sound_thread().play_sfx('Select 6')
            self.target_anim_offset = True
            self.current_desc = self._get_desc()

        elif event == 'BACK':
            if self.can_go_back:
                get_sound_thread().play_sfx('Select 4')
                game.state.back()
                if self.combat_item:
                    action.do(action.HasNotAttacked(self.unit))
                    item_system.reverse_use(self.unit, self.combat_item)
            else:
                get_sound_thread().play_sfx('Error')

        elif event == 'SELECT':
            get_sound_thread().play_sfx('Select 1')
            self.in_details = True

    def update(self):
        if not self.in_details:
            self.menu.update()
            if self.current_desc:
                self.current_desc.update()

        if self.inspector:
            self.inspector.update()

        if self.target_anim_offset:
            self.anim_offset += 8
            if self.anim_offset >= 120:
                self.target_anim_offset = False
                self.anim_offset = 120
        elif self.anim_offset > 0:
            self.anim_offset -= 8
            if self.anim_offset < 0:
                self.anim_offset = 0

        anim = self.animations[self.menu.get_current_index()]
        if anim:
            anim.update()

    def draw(self, surf):
        if not self.started:
            return surf

        self.bg.draw(surf)

        current_idx = self.menu.get_current_index()

        # ---------------------------------------------------------------------
        # Plataforma Dupla Melee com a calibração de encaixe na borda
        # ---------------------------------------------------------------------
        platform_y = 124 - self.right_platform.get_height()
        right_plat_x = WINWIDTH - self.right_platform.get_width() + self.anim_offset + 28
        left_plat_x = right_plat_x - self.left_platform.get_width()

        surf.blit(self.left_platform, (left_plat_x, platform_y))
        surf.blit(self.right_platform, (right_plat_x, platform_y))

        sprite_offset_x = 26 + self.anim_offset
        sprite_offset_y = platform_y - (WINHEIGHT - 74)

        anim = self.animations[current_idx]
        if anim:
            anim.draw(surf, (sprite_offset_x, sprite_offset_y))

        # ---------------------------------------------------------------------
        # Renderização Específica de Cada Tela
        # ---------------------------------------------------------------------
        if not self.in_details:
            # TELA 1: Seleção de Classe
            if getattr(self, 'header_surf', None):
                surf.blit(self.header_surf, self.header_pos)

            if self.menu:
                self.menu.draw(surf)

            surf.blit(SPRITES.get('promotion_description'), (6, 112))
            if self.current_desc:
                self.current_desc.draw(surf)
        else:
            # TELA 2: Detalhes e Status Bônus
            # 1. Nome da classe centralizado no topo
            if self.name_cards:
                card_surf, card_w, card_h = self.name_cards[current_idx]
                name_x = (WINWIDTH - card_w) // 2
                surf.blit(card_surf, (name_x - 2, 8 - 4))

            # 2. Contêiner de Skills & Weapons
            if self.skill_cards:
                card_surf, card_w, card_h = self.skill_cards[current_idx]
                box_x = 10
                box_y = 50
                surf.blit(card_surf, (box_x - 2, box_y - 4))

            # 3. Rodapé populado com os Status Bônus
            surf.blit(SPRITES.get('promotion_description'), (6, 112))
            klass = DB.classes.get(self.class_options[current_idx])
            self._draw_stat_bonuses(surf, klass)

            # 4. Modo de Inspeção Unificado
            if self.inspector:
                self.inspector.draw(surf)

        return surf

class ClassChangeChoiceState(PromotionChoiceState):
    name = 'class_change_choice'

    def _get_choices(self):
        if game.memory.get('promo_options', None):
            self.class_options = game.memory['promo_options']
            game.memory['promo_options'] = None
        elif not self.unit.generic:
            unit_prefab = DB.units.get(self.unit.nid)
            self.class_options = [c for c in unit_prefab.alternate_classes if c != self.unit.klass]
        else:
            self.class_options = [c.nid for c in DB.classes.values() if c.nid != self.unit.klass]
        if DB.constants.value('class_change_same_tier'):
            self.class_options = [c for c in self.class_options if DB.classes.get(c).tier == DB.classes.get(self.unit.klass).tier]
        return [DB.classes.get(c).name for c in self.class_options]

    def _proceed(self, next_class):
        game.memory['current_unit'] = self.unit
        game.memory['next_class'] = next_class
        game.memory['next_state'] = 'class_change'
        if self.from_map_combat:
            game.memory['_promo_finalize_turn'] = True
        game.state.change('transition_to_with_pop')

class PromotionState(State, MockCombat):
    name = 'promotion'
    bg = None

    def _finalize(self, current_time):
        self.state = 'level_up'
        self.last_update = current_time
        game.exp_instance.append((self.unit, 0, self, 'promote'))
        game.state.change('exp')

    def start(self):
        self.create_background()

        self.finalize_turn = game.memory.pop('_promo_finalize_turn', False)

        music = 'music_%s' % self.name
        self.promotion_song = None
        if game.game_vars.get('_' + music):
            self.promotion_song = \
                get_sound_thread().fade_in(game.game_vars.get('_' + music), fade_in=50)
        elif DB.constants.value(music):
            self.promotion_song = \
                get_sound_thread().fade_in(DB.constants.value(music), fade_in=50)

        self.unit = game.memory['current_unit']
        color = game.teams.get(self.unit.team).combat_color

        self.right_battle_anim = battle_animation.get_battle_anim(self.unit, None)
        next_class = game.memory['next_class']
        self.left_battle_anim = battle_animation.get_battle_anim(self.unit, None, klass=next_class)
        self.current_battle_anim = self.right_battle_anim

        platform_type = 'Floor'
        platform = RESOURCES.platforms[platform_type + '-Melee']
        self.left_platform = engine.image_load(platform)
        self.right_platform = engine.flip_horiz(self.left_platform.copy())

        self.name_tag = SPRITES.get('combat_name_right_' + color).copy()
        width = FONT['text-brown'].width(self.unit.name)
        FONT['text-brown'].blit(self.unit.name, self.name_tag, (36 - width // 2, 8))

        self.setup_dark()
        self.last_update = engine.get_time()
        self.state = 'init'

        if not self.right_battle_anim or not self.left_battle_anim:
            self._finalize(engine.get_time())
        else:
            game.state.change('transition_in')
            self.left_battle_anim.pair(self, self.right_battle_anim, False, 0)
            self.right_battle_anim.pair(self, self.left_battle_anim, True, 0)

        return 'repeat'

    def begin(self):
        self.last_update = engine.get_time()

    def start_anim(self, effect_nid):
        anim = self.current_battle_anim
        effect = anim.get_effect(effect_nid, pose='Attack')
        if effect:
            anim.add_effect(effect)

    def update(self):
        current_time = engine.get_time() - self.last_update
        self.current_state = self.state

        if self.state == 'init':
            if current_time > utils.frames2ms(25):
                self.state = 'right'
                self.start_anim('Promotion1')

        elif self.state == 'right':
            if not self.current_battle_anim.child_effects:
                self.current_battle_anim = self.left_battle_anim
                self.state = 'left'
                self.start_anim('Promotion2')

        elif self.state == 'left':
            if not self.current_battle_anim.child_effects:
                self.state = 'wait'

        elif self.state == 'wait':
            if current_time > utils.frames2ms(100):
                self._finalize(engine.get_time())

        elif self.state == 'level_up':
            self.state = 'leave'

        elif self.state == 'leave':
            if current_time > utils.frames2ms(10):
                if self.finalize_turn:
                    game.state.clear()
                    game.state.change('free')
                    self.unit.wait()
                else:
                    game.state.change('transition_pop')
                self.state = 'done'
                if self.promotion_song:
                    get_sound_thread().fade_back()
                return 'repeat'

        if self.state != self.current_state:
            self.last_update = engine.get_time()

        if self.current_battle_anim:
            self.current_battle_anim.update()

        if self.state == 'done':
            return 'repeat'

    def draw(self, surf):
        if self.bg:
            self.bg.draw(surf)
        else:
            return surf

        top = WINHEIGHT - 72
        combat_surf = engine.copy_surface(self.combat_surf)
        combat_surf.blit(self.left_platform, (WINWIDTH//2 - self.left_platform.get_width(), top))
        combat_surf.blit(self.right_platform, (WINWIDTH//2, top))
        self.color_ui(combat_surf)
        surf.blit(combat_surf, (0,0))

        if self.current_battle_anim:
            self.current_battle_anim.draw(surf)

        combat_surf = engine.copy_surface(self.combat_surf)
        combat_surf.blit(self.name_tag, (WINWIDTH + 3 - self.name_tag.get_width(), 0))
        self.color_ui(combat_surf)
        surf.blit(combat_surf, (0, 0))

        self.foreground.draw(surf)

        return surf

class ClassChangeState(PromotionState):
    name = 'class_change'

    def _finalize(self, current_time):
        self.state = 'level_up'
        self.last_update = current_time
        game.exp_instance.append((self.unit, 0, self, 'class_change'))
        game.state.change('exp')