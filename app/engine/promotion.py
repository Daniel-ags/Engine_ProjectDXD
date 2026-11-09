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
from app.engine.combat.preview_combat import PreviewCombat
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

        # Carrega o ícone do botão L
        buttons_sheet = SPRITES.get('buttons')
        self.btn_l = buttons_sheet.subsurface(0, 130, 24, 13) if buttons_sheet else None

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

        # Diálogo de Confirmação na Tela 2
        self.confirming = False
        self.confirm_idx = 0
        self.confirm_cursor = menus.Cursor()
        self.confirm_bg = None
        self.confirm_prompt = ""
        self.confirm_prompt_w = 0
        self.confirm_box_w = 136
        self.confirm_box_h = 48

        # Modo de visualização dos atributos na Tela 2 ('bases' ou 'growths')
        self.stat_view_mode = 'bases'

        # Instancia os chibis das classes com MapSpriteDecoration
        self.class_chibis = [
            menus.MapSpriteDecoration(c_nid, team=self.unit.team)
            for c_nid in self.class_options
        ]

        # Menu de Classes calibrado para a caixa de 72px
        options = [DB.classes.get(c_nid).name for c_nid in self.class_options]
        self.menu = menus.VisualChoice(
            self.unit, options, (6, 38),
            decorations=self.class_chibis,
            limit=3
        )
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

        # Inicializa o gerenciador encapsulado de combate da prévia
        self.preview_combat = PreviewCombat(self.unit, self.class_options)

        # Pré-carregamento dos elementos visuais e cards da Tela 2
        self.weapon_icons = []
        self.skill_cards = []
        self.name_cards = []

        for option in self.class_options:
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

        # Plataforma Melee Fixa (Duas metades unidas)
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

        self.current_desc = self._get_desc()

    def begin(self):
        self.fluid.reset_on_change_state()

    def _get_desc(self):
        current_klass = self.class_options[self.menu.get_current_index()]
        klass = DB.classes.get(current_klass)
        text = text_funcs.translate_and_text_evaluate(klass.desc, self=klass)
        d = dialog.Dialog(text.replace('\\n', '{br}'))
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
        card_h = 40  # Altura original preservada

        card_surf = base_surf.create_ornate_base_surf(card_w, card_h, 'menu_bg_base')
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
        box_x, box_y = 6, 112
        box_w = 228
        bonus_list = []

        # Inicialização explícita para satisfazer o PyLance
        mode_title = "Stats"
        target_mode = "Growths"

        # ---------------------------------------------------------------------
        # 1. Coleta dos Dados de Acordo com o Modo Ativo
        # ---------------------------------------------------------------------
        if self.stat_view_mode == 'bases':
            promo_gains = getattr(klass, 'promotion', {}) or {}
            for stat in DB.stats:
                if stat.nid == 'MOV':
                    continue
                val = promo_gains.get(stat.nid, 0)
                if val != 0 and abs(val) < 50:
                    bonus_list.append((stat.nid, val, f"{'+' if val > 0 else ''}{val}"))

            for stat_nid, val in promo_gains.items():
                if stat_nid != 'MOV' and val != 0 and abs(val) < 50 and stat_nid not in [b[0] for b in bonus_list]:
                    bonus_list.append((stat_nid, val, f"{'+' if val > 0 else ''}{val}"))

            mode_title = "Stats"
            target_mode = "Growths"

        else:
            target_growths = getattr(klass, 'growth_bonus', getattr(klass, 'growths', {})) or {}
            current_growths = getattr(self.unit_klass, 'growth_bonus', getattr(self.unit_klass, 'growths', {})) or {}

            raw_growths = []
            for stat in DB.stats:
                if stat.nid == 'MOV':
                    continue
                val = target_growths.get(stat.nid, 0) - current_growths.get(stat.nid, 0)
                if val != 0 and abs(val) < 100:
                    raw_growths.append((stat.nid, val))

            for stat_nid in target_growths.keys():
                if stat_nid != 'MOV' and stat_nid not in [b[0] for b in raw_growths]:
                    val = target_growths.get(stat_nid, 0) - current_growths.get(stat_nid, 0)
                    if val != 0 and abs(val) < 100:
                        raw_growths.append((stat_nid, val))

            include_pct = len(raw_growths) < 8
            for s_nid, val in raw_growths:
                suffix = "%" if include_pct else ""
                bonus_list.append((s_nid, val, f"{'+' if val > 0 else ''}{val}{suffix}"))

            mode_title = "Growths"
            target_mode = "Stats"

        # ---------------------------------------------------------------------
        # 2. Contêiner de Alternância [L] (card_h = text_h + 8)
        # ---------------------------------------------------------------------
        text_h = FONT['text'].height
        card_h = text_h + 8  # 16 + 8 = 24px (altura ideal)
        card_y = 93

        # Bordas laterais de 4px e envelope do ornate
        pad = 4
        off_x = 2

        # Miolo útil (descontando 4px da borda superior e 4px da inferior)
        inner_h = card_h - 8
        txt_y = (inner_h - text_h) // 2 + 8

        # Aba Única: Ícone [L] + Texto do Modo Alternativo
        btn_w = self.btn_l.get_width() if getattr(self, 'btn_l', None) else 0
        txt_w = FONT['text'].width(target_mode)
        gap = 0
        content_w = btn_w + txt_w

        hint_card_w = ((content_w + pad * 2 + 7) // 8) * 8
        hint_card = base_surf.create_ornate_base_surf(
            hint_card_w, card_h, 'menu_bg_base_overlay', translucency=0
        )

        start_x = off_x + (hint_card_w - content_w) // 2
        if getattr(self, 'btn_l', None):
            btn_h = self.btn_l.get_height()
            btn_y = (inner_h - btn_h) // 2 + 8
            hint_card.blit(self.btn_l, (start_x, btn_y))
            txt_x = start_x + btn_w + gap
        else:
            txt_x = start_x

        render_text(hint_card, ['text'], [target_mode], ['white'], (txt_x, txt_y))
        # Alinhado na borda esquerda: blit em (6 - 2 = 4)
        surf.blit(hint_card, (box_x - off_x, card_y - 4))
        # ---------------------------------------------------------------------
        # 3. Renderização com Espaçamento Unificado e Simetria Matemática
        # ---------------------------------------------------------------------
        if not bonus_list:
            empty_msg = "No stat changes upon promotion." if self.stat_view_mode == 'bases' else "No growth modifiers for this class."
            render_text(surf, ['text'], [empty_msg], ['white'], (box_x + 16, box_y + 16))
            return

        num_stats = len(bonus_list)
        box_center = box_x + box_w // 2  # Centro absoluto: x = 120

        if num_stats == 1:
            centers = [box_center]
        else:
            # Passo fixo de 24px para 9 atributos (máximo proveito dos 228px com 18px de margem em ambos os lados)
            step = min(32, (box_w - 36) // (num_stats - 1))
            total_span = (num_stats - 1) * step
            left_center = box_center - total_span // 2
            centers = [left_center + i * step for i in range(num_stats)]

        for col_idx, (s_nid, s_val, formatted_val) in enumerate(bonus_list):
            item_center_x = centers[col_idx]

            # Linha 1: Sigla do Atributo
            key_w = FONT['text'].width(s_nid)
            key_x = item_center_x - key_w // 2
            render_text(surf, ['text'], [s_nid], ['white'], (key_x, box_y + 10))

            # Linha 2: Valor Formatado (+2 / +10% / +10)
            val_color = 'green' if s_val > 0 else 'red'
            val_w = FONT['text'].width(formatted_val)
            val_x = item_center_x - val_w // 2
            render_text(surf, ['text'], [formatted_val], [val_color], (val_x, box_y + 26))

    def _get_help_targets(self, class_idx):
        if not self.skill_cards or class_idx >= len(self.class_details_items):
            return []
        items = self.class_details_items[class_idx]
        if not items:
            return []

        card_surf, card_w, card_h = self.skill_cards[class_idx]
        total_icons = len(items)
        icon_pitch = 18
        total_content_w = total_icons * icon_pitch - 2 if total_icons > 0 else FONT['text'].width("---")

        # Sincroniza a mira do cursor R com os cards
        box_x = 6
        box_y = 42  # 44 -> 42
        start_x = box_x + (card_w - total_content_w) // 2
        icons_y = box_y + 18

        targets = []
        for idx, (item_type, item_obj) in enumerate(items):
            icon_x = start_x + idx * icon_pitch
            icon_y = icons_y

            if item_type == 'skill':
                name = getattr(item_obj, 'name', 'Skill')
                desc = getattr(item_obj, 'desc', '') or "No description."
            else:
                w_obj = DB.weapons.get(item_obj) if hasattr(DB, 'weapons') and DB.weapons.get(item_obj) else None
                name = getattr(w_obj, 'name', item_obj)
                desc = getattr(w_obj, 'desc', '') or f"Grants proficiency with {name}s."

            text = f"{name}: {desc}"
            targets.append((icon_x, icon_y, text))

        return targets

    def _open_confirmation(self, klass_name):
        self.confirming = True
        self.confirm_idx = 0
        self.confirm_prompt = f"Promote to {klass_name}?"
        self.confirm_prompt_w = FONT['text'].width(self.confirm_prompt)
        min_w = 88
        self.confirm_box_w = max(min_w, ((self.confirm_prompt_w + 16 + 7) // 8) * 8)
        self.confirm_box_h = 48
        self.confirm_bg = base_surf.create_ornate_base_surf(
            self.confirm_box_w, self.confirm_box_h, 'menu_bg_base', gems='all', translucency=0
        )

    def take_input(self, event):
        first_push = self.fluid.update()
        directions = self.fluid.get_directions()

        # ---------------------------------------------------------------------
        # Tela 2: Detalhes da Promoção
        # ---------------------------------------------------------------------
        if self.in_details:
            # 1. Modo de Confirmação (Yes / No)
            if self.confirming:
                if 'LEFT' in directions or event == 'LEFT':
                    if self.confirm_idx != 0:
                        get_sound_thread().play_sfx('Select 5')
                        self.confirm_idx = 0
                elif 'RIGHT' in directions or event == 'RIGHT':
                    if self.confirm_idx != 1:
                        get_sound_thread().play_sfx('Select 5')
                        self.confirm_idx = 1

                if event == 'BACK':
                    get_sound_thread().play_sfx('Select 4')
                    self.confirming = False
                elif event == 'SELECT':
                    if self.confirm_idx == 0:  # Yes
                        get_sound_thread().play_sfx('Select 1')
                        self.confirming = False
                        self._proceed(self.class_options[self.menu.get_current_index()])
                    elif self.confirm_idx == 1:  # No
                        get_sound_thread().play_sfx('Select 4')
                        self.confirming = False
                return

            # 2. Se a inspeção estiver ativa, delega para o HelpInspector
            if self.inspector:
                if not self.inspector.handle_input(event, directions):
                    self.inspector = None
                return

            # 3. Abre a inspeção ao pressionar R (INFO)
            if event == 'INFO':
                current_idx = self.menu.get_current_index()
                targets = self._get_help_targets(current_idx)
                if targets:
                    self.inspector = help_menu.HelpInspector(targets, orientation='horizontal')
                return
            
            # Alternância de modo na caixa inferior (Bases <-> Growths)
            if event == 'AUX':
                self.stat_view_mode = 'growths' if self.stat_view_mode == 'bases' else 'bases'
                get_sound_thread().play_sfx('Select 5')
                return

            if event == 'BACK':
                get_sound_thread().play_sfx('Select 4')
                self.in_details = False
            elif event == 'SELECT':
                get_sound_thread().play_sfx('Select 1')
                current_idx = self.menu.get_current_index()
                klass = DB.classes.get(self.class_options[current_idx])
                self._open_confirmation(klass.name)
            return

        # ---------------------------------------------------------------------
        # Tela 1: Escolha da Classe
        # ---------------------------------------------------------------------
        current_idx = self.menu.get_current_index()
        self.menu.handle_mouse()
        new_idx = self.menu.get_current_index()

        if 'DOWN' in directions:
            if self.menu.move_down(first_push):
                get_sound_thread().play_sfx('Select 6')
            self.current_desc = self._get_desc()
        elif 'UP' in directions:
            if self.menu.move_up(first_push):
                get_sound_thread().play_sfx('Select 6')
            self.current_desc = self._get_desc()

        new_idx = self.menu.get_current_index()
        if current_idx != new_idx:
            self.preview_combat.change_class(new_idx)
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
            # Estabiliza o combatente imediatamente ao entrar na Tela 2
            self.preview_combat.stabilize(self.menu.get_current_index())

    def update(self):
        if not self.in_details:
            self.menu.update()
            if self.current_desc:
                self.current_desc.update()

        # Atualiza a animação do cursor e do balão durante a inspeção
        if self.inspector:
            self.inspector.update()

        if self.confirming:
            self.confirm_cursor.update()

        # Atualiza a animação de combate encapsulada
        self.preview_combat.update()

    def draw(self, surf):
        if not self.started:
            return surf

        self.bg.draw(surf)

        # ---------------------------------------------------------------------
        # Plataforma Dupla Melee Estática
        # ---------------------------------------------------------------------
        platform_y = 124 - self.right_platform.get_height()
        right_plat_x = WINWIDTH - self.right_platform.get_width() + 24
        left_plat_x = right_plat_x - self.left_platform.get_width()

        surf.blit(self.left_platform, (left_plat_x, platform_y))
        surf.blit(self.right_platform, (right_plat_x, platform_y))

        # ---------------------------------------------------------------------
        # Renderização do Combatente (Encapsulada via PreviewCombat)
        # ---------------------------------------------------------------------
        sprite_offset_x = 26
        sprite_offset_y = platform_y - (WINHEIGHT - 74)
        self.preview_combat.draw(surf, (sprite_offset_x, sprite_offset_y))

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
            current_idx = self.menu.get_current_index()

            # 1. Nome da classe centralizado no topo
            if self.name_cards:
                card_surf, card_w, card_h = self.name_cards[current_idx]
                name_x = (WINWIDTH - card_w) // 2
                surf.blit(card_surf, (name_x - 2, 8 - 4))

            # 2. Contêiner de Skills & Weapons (Movido 2px para cima: Y=42)
            if self.skill_cards:
                card_surf, card_w, card_h = self.skill_cards[current_idx]
                box_x = 6
                box_y = 38
                surf.blit(card_surf, (box_x - 2, box_y - 4))

            # 3. Rodapé populado com os Status Bônus
            surf.blit(SPRITES.get('promotion_description'), (6, 112))
            klass = DB.classes.get(self.class_options[current_idx])
            self._draw_stat_bonuses(surf, klass)

            # 4. Modo de Inspeção Unificado (Cursor com bobbing e Balão)
            if self.inspector:
                self.inspector.draw(surf)

            # 5. Diálogo de Confirmação (Promote to [Class]?) com Ornate e 4 gemas
            if self.confirming and self.confirm_bg:
                box_x = (WINWIDTH - self.confirm_box_w) // 2
                box_y = (WINHEIGHT - self.confirm_box_h) // 2
                # Desconta o envelope transparente (-2, -4) da moldura ornate
                surf.blit(self.confirm_bg, (box_x - 2, box_y - 4))

                prompt_x = box_x + (self.confirm_box_w - self.confirm_prompt_w) // 2
                render_text(surf, ['text'], [self.confirm_prompt], ['white'], (prompt_x, box_y + 8))

                center_x = box_x + self.confirm_box_w // 2
                yes_color = 'yellow' if self.confirm_idx == 0 else 'white'
                no_color = 'yellow' if self.confirm_idx == 1 else 'white'

                # Opções Yes e No perfeitamente simétricas em relação à linha central
                yes_w = FONT['text'].width("Yes")
                gap = 10
                yes_x = center_x - gap - yes_w
                no_x = center_x + gap

                render_text(surf, ['text'], ["Yes"], [yes_color], (yes_x, box_y + 26))
                render_text(surf, ['text'], ["No"], [no_color], (no_x, box_y + 26))

                # Cursor aproximado a 6px do início do texto (mesmo offset dos ícones)
                cursor_x = (yes_x - 6) if self.confirm_idx == 0 else (no_x - 6)
                self.confirm_cursor.draw(surf, cursor_x, box_y + 26)

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