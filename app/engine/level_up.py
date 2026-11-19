import math
from typing import Callable, List, Tuple
from app.utilities.typing import NID

from app.constants import TILEWIDTH, TILEHEIGHT, WINWIDTH, WINHEIGHT
from app.data.resources.resources import RESOURCES
from app.data.database.database import DB

from app.utilities import utils
from app.engine import engine, image_mods, icons, unit_funcs, aura_funcs, \
    action, banner, skill_system, exp_funcs, item_funcs, base_surf, menus, help_menu
from app.engine.sprites import SPRITES
from app.engine.sound import get_sound_thread
from app.engine.fonts import FONT
from app.engine.fluid_scroll import FluidScroll
from app.events import triggers
from app.engine.state import State
from app.engine.state_machine import SimpleStateMachine
from app.engine.animations import Animation
from app.engine.game_state import game
from app.engine.graphics.text.text_renderer import render_text, text_width
from app.utilities.enums import HAlignment

from app.engine.objects.unit import UnitObject
from app.engine.source_type import SourceType

class ExpState(State):
    name = 'exp'
    transparent = True
    state = None
    music_lowered = False

    # The GBA waits 10 frames between the exp bar and the banner. Half a frame
    # is taken off, since a frame is 16 or 17 ms
    banner_wait_time = utils.frames2ms(9.5)
    # On the map it then brings the music down to half over 16 frames, and only
    # once it is down shows the banner, 18 frames on. After the banner it brings
    # the music back up the same way, and the level up screen comes 19 frames on.
    # In battle the music is left as it is
    music_fade_time = utils.frames2ms(16)
    music_down_time = utils.frames2ms(17.5)
    music_up_time = utils.frames2ms(18.5)

    dark_fuzz_background = image_mods.make_translucent(SPRITES.get('bg_black'), 0.66)

    def start(self):
        if game.exp_instance:
            self.unit, self.exp_gain, self.combat_object, self.starting_state = \
                game.exp_instance.pop()
        else:
            game.state.back()
            return 'repeat'

        self.method = None
        if game.memory.get('exp_method'):
            self.method = game.memory.pop('exp_method')

        self.old_exp = self.unit.exp
        self.old_level = self.unit.level
        self.unit_klass = DB.classes.get(self.unit.klass)
        self.auto_promote = exp_funcs.has_autopromote(self.unit)

        # For mana
        self.old_mana = self.unit.get_mana()
        self.max_mana = self.unit.get_max_mana()
        self.mana_to_gain = 0
        if game.mana_instance:
            mana_instances_for_unit = [instance for instance in game.mana_instance if instance[0].nid == self.unit.nid]
            for instance in mana_instances_for_unit:
                self.mana_to_gain += instance[1]
                game.mana_instance.remove(instance)
            if self.mana_to_gain + self.old_mana > self.max_mana:
                self.mana_to_gain = self.max_mana - self.old_mana
        self.mana_bar = None

        self.state = SimpleStateMachine(self.starting_state)
        self.start_time = engine.get_time()

        self.exp_bar = None
        self.level_up_animation = None
        self.level_up_screen = None

        if not self.auto_promote:
            max_exp = 100 * (self.unit_klass.max_level - self.old_level) - self.old_exp
            self.exp_gain = min(self.exp_gain, max_exp)

        self.total_time_for_exp = max(1, utils.frames2ms(abs(self.exp_gain)))

        self.stat_changes = None
        self.new_wexp = None

        if not (exp_funcs.can_give_exp(self.unit, self.exp_gain) or self.mana_to_gain or
                self.starting_state in ('promote', 'class_change', 'stat_booster')):
            game.state.back()
            return 'repeat'

        self.source = 'exp_gain'
        if self.starting_state == 'stat_booster':
            self.source = 'stat_change'
        elif self.starting_state == 'class_change':
            self.source = 'class_change'
        elif self.starting_state == 'promote':
            self.source = 'promote'

        self.level_up_sound_played = False

    def begin(self):
        game.cursor.hide()

    def end(self):
        get_sound_thread().stop_sfx('Experience Gain')
        self.restore_music()

    def restore_music(self):
        if self.music_lowered:
            get_sound_thread().unmute(fade=self.music_fade_time)
            self.music_lowered = False

    def create_level_up_logo(self):
        if self.combat_object:
            anim = RESOURCES.animations.get('LevelUpBattle')
            if anim:
                anim = Animation(anim, (0, 6))
                anim.set_tint_after_delay(40)
                self.level_up_animation = anim
        else:
            if self.unit.position:
                x, y = self.unit.position
                left = (x - game.camera.get_x() - 2) * TILEWIDTH
                top = (y - game.camera.get_y() - 1) * TILEHEIGHT
                pos = (left, top)
            else:
                pos = (WINWIDTH // 2, WINHEIGHT // 2)
            anim = RESOURCES.animations.get('LevelUpMap')
            if anim:
                anim = Animation(anim, pos)
                self.level_up_animation = anim

    def update(self):
        current_time = engine.get_time()

        if self.state.get_state() == 'init':
            self.exp_bar = ExpBar(self.old_exp, center=not self.combat_object)
            self.start_time = current_time

            if self.mana_to_gain:
                self.mana_bar = ManaBar(self.old_mana, center=not self.combat_object)
                self.mana_bar.bar_max = self.unit.get_max_mana()

            self.state.change('exp_wait')

        elif self.state.get_state() == 'exp_wait':
            self.exp_bar.update(self.old_exp)
            if self.mana_bar:
                self.mana_bar.update(self.old_mana)
            if current_time - self.start_time > 466:
                self.state.change('exp0')
                self.start_time = current_time
                get_sound_thread().play_sfx('Experience Gain', True)

        elif self.state.get_state() == 'exp0':
            progress = utils.clamp((current_time - self.start_time) / float(self.total_time_for_exp), 0, 1)
            exp_set = int(self.old_exp + progress * self.exp_gain)
            self.exp_bar.update(exp_set)

            if self.mana_bar:
                mana_set = int(self.old_mana + progress * self.mana_to_gain)
                self.mana_bar.update(mana_set)

            if exp_set >= self.old_exp + self.exp_gain:
                get_sound_thread().stop_sfx('Experience Gain')

            if exp_set >= 100:
                if self.unit.level >= self.unit_klass.max_level:
                    get_sound_thread().stop_sfx('Experience Gain')
                    if self.auto_promote:
                        self.exp_bar.update(100)
                        get_sound_thread().play_sfx('Level Up')
                    else:
                        self.exp_bar.update(99)
                    self.state.clear()
                    self.state.change('prepare_promote')
                    self.state.change('exp_leave')
                    self.exp_bar.fade_out()
                    self.start_time = current_time
                else:
                    self.state.change('exp100')

            if exp_set < 0 and self.exp_gain < 0:
                if self.unit.level > 1:
                    self.state.change('exp-100')
                else:
                    get_sound_thread().stop_sfx('Experience Gain')

            if current_time - self.start_time >= self.total_time_for_exp + 500:
                get_sound_thread().stop_sfx('Experience Gain')
                self.state.clear()
                self.state.change('exp_leave')
                self.exp_bar.fade_out()
                self.start_time = current_time

        elif self.state.get_state() == 'exp_leave':
            if self.exp_bar.update():
                action.do(action.GainExp(self.unit, self.exp_gain))
                if self.mana_to_gain:
                    action.do(action.ChangeMana(self.unit, self.mana_to_gain))
                action.do(action.UpdateRecords('exp_gain', (self.unit.nid, self.exp_gain, self.unit.klass)))
                self.state.back()
                self.start_time = current_time
                if len(self.state.state) <= 0:
                    game.state.back()

        elif self.state.get_state() == 'exp100':
            progress = (current_time - self.start_time) / float(self.total_time_for_exp)
            exp_set = int(min(self.old_exp + (self.exp_gain * progress) - 100, self.old_exp + self.exp_gain - 100))
            self.exp_bar.update(exp_set)

            if exp_set >= self.old_exp + self.exp_gain - 100:
                get_sound_thread().stop_sfx('Experience Gain')

            if current_time - self.start_time >= self.total_time_for_exp + 333:
                old_growth_points = self.unit.growth_points.copy()
                self.stat_changes = unit_funcs.get_next_level_up(self.unit, self.unit.get_internal_level(), self.method)
                action.do(action.GrowthPointChange(self.unit, old_growth_points, self.unit.growth_points))
                action.do(action.IncLevel(self.unit))
                action.do(action.ApplyStatChanges(self.unit, self.stat_changes, self.name == 'bonus_exp'))
                action.do(action.UpdateRecords('level_gain', (self.unit.nid, self.unit.level, self.unit.klass)))
                self.state.clear()
                self.state.change('level_up')
                self.state.change('banner_wait')
                self.state.change('exp_leave')
                self.exp_bar.fade_out()
                self.start_time = current_time

        elif self.state.get_state() == 'exp-100':
            progress = (current_time - self.start_time) / float(self.total_time_for_exp)
            exp_set = int(max(100 + self.old_exp + (self.exp_gain * progress), 100 + self.old_exp + self.exp_gain))
            self.exp_bar.update(exp_set)

            if exp_set <= 100 + self.old_exp + self.exp_gain:
                get_sound_thread().stop_sfx('Experience Gain')

            if current_time - self.start_time >= self.total_time_for_exp + 333:
                old_growth_points = self.unit.growth_points.copy()
                stat_changes = unit_funcs.get_next_level_up(self.unit, self.unit.get_internal_level() - 1, self.method)
                self.stat_changes = {nid: -value for nid, value in stat_changes.items()}
                action.do(action.GrowthPointChange(self.unit, old_growth_points, self.unit.growth_points))
                action.do(action.SetLevel(self.unit, self.unit.level - 1))
                action.do(action.ApplyStatChanges(self.unit, self.stat_changes, self.name == 'bonus_exp'))
                self.state.clear()
                self.state.change('level_up')
                self.state.change('banner_wait')
                self.state.change('exp_leave')
                self.exp_bar.fade_out()
                self.start_time = current_time

        # The GBA's pause between the exp bar and the banner
        elif self.state.get_state() == 'banner_wait':
            if current_time - self.start_time > self.banner_wait_time:
                self.state.back()
                if self.combat_object:
                    # Made on the frame it is first shown: a banner timed in
                    # milliseconds counts them from when it is made
                    self.create_level_up_logo()
                else:
                    # As on the GBA, the music is at half its volume under the banner
                    get_sound_thread().lower(0.5, fade=self.music_fade_time)
                    self.music_lowered = True
                    self.state.change('music_down')
                    self.start_time = current_time

        # On the map, the banner waits for the music to come down
        elif self.state.get_state() == 'music_down':
            if current_time - self.start_time > self.music_down_time:
                self.state.back()
                self.create_level_up_logo()

        # And the level up screen waits for it to come back up
        elif self.state.get_state() == 'music_up':
            if current_time - self.start_time > self.music_up_time:
                self.state.back()
                self.start_time = current_time

        elif self.state.get_state() == 'level_up':
            if not self.level_up_sound_played:
                get_sound_thread().play_sfx('Level Up')
                self.level_up_sound_played = True

            if self.level_up_animation.update():
                if self.combat_object:
                    self.combat_object.darken_ui()
                self.state.change('level_screen')
                self.start_time = current_time
                if self.music_lowered:
                    self.restore_music()
                    self.state.change('music_up')

        elif self.state.get_state() == 'level_screen':
            if not self.level_up_screen:
                self.level_up_screen = LevelUpScreen(
                    self, self.unit, self.stat_changes, self.old_level, self.unit.level, self.unit_klass)
            if self.level_up_screen.update(current_time):
                game.events.trigger(triggers.UnitLevelUp(self.unit, self.stat_changes, self.source))
                if self.combat_object:
                    self.combat_object.lighten_ui()

                # Experiência e ranks de arma
                if self.new_wexp:
                    for weapon_nid, value in self.new_wexp.items():
                        action.do(action.AddWexp(self.unit, weapon_nid, value))

                # Concessão de habilidades
                if self.starting_state != "stat_booster":
                    ExpState.give_new_personal_skills(self.unit)
                    if self.starting_state == 'class_change':
                        if DB.constants.value('learn_skills_on_reclass'):
                            ExpState.give_all_class_skills(self.unit)
                    elif self.starting_state == 'promote':
                        if DB.constants.value('learn_skills_on_promote'):
                            ExpState.give_all_class_skills(self.unit)
                    else:
                        ExpState.give_new_class_skills(self.unit)

                if game.memory.get('skill_swap_queue'):
                    self.state.change('wait_for_swap')
                    game.state.change('skill_swap_levelup')
                else:
                    if hasattr(game.state, 'temp_state'):
                        game.state.temp_state = [
                            entry for entry in game.state.temp_state
                            if 'alert' not in str(entry)
                        ]
                    self.state.clear()
                    game.state.back()
                    for _ in game.alerts:
                        game.state.change('alert')

        elif self.state.get_state() == 'wait_for_swap':
            if game.state.state and game.state.state[-1] == self:
                if game.memory.get('skill_swap_queue'):
                    game.state.change('skill_swap_levelup')
                else:
                    self.state.clear()
                    game.state.back()

        elif self.state.get_state() == 'wait_for_swap':
            # Usado exclusivamente quando uma skill masterizada/pessoal abre o SkillSwapLevelUpState
            if game.state.state and game.state.state[-1] == self:
                if game.memory.get('skill_swap_queue'):
                    game.state.change('skill_swap_levelup')
                else:
                    self.state.clear()
                    game.state.back()

        elif self.state.get_state() == 'drain_alerts':
            # Responsabilidade 2: Bombear cada banner individualmente até a fila esvaziar
            if game.state.state and game.state.state[-1] == self:
                if game.alerts:
                    game.state.change('alert')
                else:
                    self.state.clear()
                    game.state.back()

        elif self.state.get_state() == 'prepare_promote':
            self.exp_bar.update()
            if current_time - self.start_time > 100:
                class_options = self.unit_klass.turns_into
                if self.auto_promote:
                    self.exp_bar.update(0)
                    if len(class_options) > 1:
                        game.memory['current_unit'] = self.unit
                        game.state.change('promotion_choice')
                        game.state.change('transition_out')
                        self.state.clear()
                        self.state.change('wait')
                        self.start_time = current_time
                    elif len(class_options) == 1:
                        game.memory['current_unit'] = self.unit
                        game.memory['next_class'] = class_options[0]
                        game.state.change('promotion')
                        game.state.change('transition_out')
                        self.state.clear()
                        self.state.change('wait')
                        self.start_time = current_time
                    else:
                        action.do(action.SetExp(self.unit, 99))
                        game.state.back()
                else:
                    action.do(action.SetExp(self.unit, 99))
                    game.state.back()

        elif self.state.get_state() in ('promote', 'class_change'):
            if self.state.get_state() == 'promote':
                promote_action = action.Promote(self.unit, game.memory['next_class'])
            else:
                promote_action = action.ClassChange(self.unit, game.memory['next_class'])
            self.stat_changes, self.new_wexp = promote_action.get_data()
            action.do(promote_action)
            action.do(action.UpdateRecords('level_gain', (self.unit.nid, self.unit.level, self.unit.klass)))

            if self.combat_object:
                self.combat_object.darken_ui()

            self.state.clear()
            self.state.change('level_screen')
            self.start_time = current_time

        elif self.state.get_state() == 'stat_booster':
            self.stat_changes = game.memory['stat_changes']
            self.exp_gain = 0
            self.old_level = self.unit.level
            self.state.change('level_screen')
            self.start_time = current_time

        elif self.state.get_state() == 'wait':
            if current_time - self.start_time > 1000:
                game.state.back()

    def draw(self, surf):
        if not self.state:
            return surf

        if self.state.get_state() in ('init', 'exp_wait', 'exp_leave', 'exp0', 'exp100', 'exp-100', 'prepare_promote'):
            if self.mana_bar:
                self.mana_bar.draw(surf)
            if self.exp_bar:
                self.exp_bar.draw(surf)

        elif self.state.get_state() == 'level_up':
            surf.blit(self.dark_fuzz_background, (0, 0))
            if self.level_up_animation:
                # update() has already advanced it this frame
                self.level_up_animation.draw(surf)

        elif self.state.get_state() == 'level_screen':
            if self.level_up_screen:
                self.level_up_screen.draw(surf)

        return surf

    @staticmethod
    def _give_skills(unit: UnitObject, avail_skills: List[Tuple[int, NID]],
                     comparison_func: Callable[[UnitObject, int], bool], source_type):
        for level_needed, skill_nid in avail_skills:
            if comparison_func(unit, level_needed):
                if skill_nid == 'Feat':
                    game.memory['current_unit'] = unit
                    game.state.change('feat_choice')
                else:
                    # =========================================================
                    # 1. HABILIDADES DE CLASSE (SourceType.KLASS)
                    # =========================================================
                    if source_type == SourceType.KLASS:
                        if not hasattr(unit, 'class_skills') or unit.class_skills is None:
                            unit.class_skills = []
                        if skill_nid not in unit.class_skills:
                            unit.class_skills.append(skill_nid)

                        # Concede a skill ativa na classe atual (custo 0 de slots)
                        act = None
                        if not any(s.get().nid == skill_nid for s in unit._skills):
                            act = action.AddSkill(unit, skill_nid, source=unit.klass, source_type=SourceType.KLASS)
                            action.do(act)

                        # Só masteriza permanentemente se os pré-requisitos estiverem cumpridos
                        if unit.has_prerequisites(skill_nid):
                            newly_mastered = unit.learn_skill(skill_nid)
                            for mastered_nid in newly_mastered:
                                skill_obj = (
                                    act.skill_obj if (act and act.skill_obj and act.skill_obj.nid == mastered_nid)
                                    else item_funcs.create_skill(unit, mastered_nid)
                                )
                                if skill_obj and not skill_system.hidden(skill_obj, unit):
                                    msg = f"{unit.name} mastered {skill_obj.name}!"
                                    alert = banner.CustomSkillBanner(unit, skill_obj, msg)
                                    game.alerts.append(alert)

                    # =========================================================
                    # 2. HABILIDADES PESSOAIS (SourceType.PERSONAL)
                    # =========================================================
                    else:
                        if hasattr(unit, 'learned_skills') and unit.learned_skills and skill_nid in unit.learned_skills:
                            continue
                        if any(s.get().nid == skill_nid for s in unit._skills):
                            continue
                        if not unit.has_prerequisites(skill_nid):
                            continue

                        newly_mastered = unit.learn_skill(skill_nid)
                        source = unit.nid

                        if len(unit.get_equipped_skills()) < unit.max_skills:
                            act = action.AddSkill(unit, skill_nid, source=source, source_type=SourceType.PERSONAL)
                            action.do(act)

                            if act.skill_obj and not skill_system.hidden(act.skill_obj, unit):
                                msg = f"{unit.name} learned {act.skill_obj.name}!"
                                alert = banner.CustomSkillBanner(unit, act.skill_obj, msg)
                                game.alerts.append(alert)
                        else:
                            if unit.team == 'player':
                                if 'skill_swap_queue' not in game.memory or not game.memory['skill_swap_queue']:
                                    game.memory['skill_swap_queue'] = []
                                game.memory['skill_swap_queue'].append((unit, skill_nid, source, source_type))

                        # Dispara banner de maestria caso o aprendizado tenha desbloqueado alguma skill retroativa
                        for retro_nid in newly_mastered:
                            if retro_nid == skill_nid:
                                continue
                            retro_obj = item_funcs.create_skill(unit, retro_nid)
                            if retro_obj and not skill_system.hidden(retro_obj, unit):
                                msg = f"{unit.name} mastered {retro_obj.name}!"
                                alert = banner.CustomSkillBanner(unit, retro_obj, msg)
                                game.alerts.append(alert)

    @staticmethod
    def give_new_class_skills(unit: UnitObject):
        unit_klass = DB.classes.get(unit.klass)
        ExpState._give_skills(unit, unit_klass.learned_skills, lambda u, req: u.level >= req, source_type=SourceType.KLASS)

    give_all_class_skills = give_new_class_skills

    @staticmethod
    def give_new_personal_skills(unit: UnitObject):
        unit_prefab = DB.units.get(unit.nid)
        if unit_prefab:
            compare = lambda u, req: u.level >= req or u.get_internal_level() >= req
            ExpState._give_skills(unit, unit_prefab.learned_skills, compare, source_type=SourceType.PERSONAL)


class LevelUpScreen():
    bg_top = SPRITES.get('level_screen_top').convert_alpha()
    bg_bottom = SPRITES.get('level_screen_bottom').convert_alpha()
    width = bg_bottom.get_width()
    height = bg_bottom.get_height()

    # The GBA shows a stat gain every 20 frames: a frame goes to picking the
    # next one, and half a frame is taken off since a frame is 16 or 17 ms
    spark_time = utils.frames2ms(18.5)
    level_up_wait = 1366
    # The GBA's screen is gone in 9 frames. This one takes 10 to be off the screen
    scroll_out_time = utils.frames2ms(9.5)

    underline = SPRITES.get('stat_underline')

    def __init__(self, parent, unit, stat_changes, old_level, new_level, old_class):
        self.parent = parent
        self.unit = unit
        self.stat_list = [stat_changes.get(nid, 0) for nid in DB.stats.keys()][:8]
        self.old_level = old_level
        self.new_level = new_level
        self.old_class = old_class

        self.current_spark = -1
        self.unit_scroll_offset = 80
        self.screen_scroll_offset = self.width + 32
        self.underline_offset = 36

        self.animations = []
        self.arrow_animations = []
        self.simple_nums = []

        self.state = 'scroll_in'
        self.start_time = 0
        self.flipped = False
        self.flip_start_time = 0
        self.flip_timer = 0

    def make_spark(self, topleft):
        anim = RESOURCES.animations.get('StatUpSpark')
        return Animation(anim, topleft) if anim else None

    def topleft(self):
        return (6 - self.screen_scroll_offset, WINHEIGHT - 8 - self.height)

    def get_position(self, i, absolute=False):
        tl = self.topleft() if absolute else (0, 0)
        if i >= 4:
            return (self.width // 2 + 8 + tl[0], (i - 4) * 16 + 35 + tl[1])
        return (10 + tl[0], i * 16 + 35 + tl[1])

    def inc_spark(self):
        self.current_spark += 1
        if self.current_spark >= len(self.stat_list):
            return True
        elif self.stat_list[self.current_spark] == 0:
            return self.inc_spark()
        return False

    def update(self, current_time):
        if self.state == 'init_pause':
            if current_time - self.start_time > 268:
                self.state = 'scroll_in'
                self.start_time = current_time

        elif self.state == 'scroll_in':
            self.unit_scroll_offset = max(0, self.unit_scroll_offset - 8)
            self.screen_scroll_offset = max(0, self.screen_scroll_offset - 16)
            if self.unit_scroll_offset == 0 and self.screen_scroll_offset == 0:
                self.state = 'init_wait'
                self.start_time = current_time

        elif self.state == 'init_wait':
            if self.old_class.name != DB.classes.get(self.unit.klass).name:
                if current_time - self.start_time > 500:
                    if self.flip_start_time == 0:
                        self.flip_start_time = current_time
                        get_sound_thread().play_sfx('Level_Up_Level')
                    if self.flip_start_time and current_time - self.flip_start_time > 167:
                        self.flipped = True
                if current_time - self.start_time > 850:
                    self.state = 'get_next_spark'
                    self.start_time = current_time
            elif current_time - self.start_time > 500:
                if self.old_level != self.new_level:
                    self.state = 'first_spark'
                    self.animations.append(self.make_spark((87, 27)))
                    get_sound_thread().play_sfx('Level_Up_Level')
                else:
                    self.state = 'get_next_spark'
                self.start_time = current_time

        elif self.state == 'scroll_out':
            self.unit_scroll_offset += 10
            self.screen_scroll_offset += 20
            if current_time - self.start_time > self.scroll_out_time:
                return True  # Done

        elif self.state == 'first_spark':
            if current_time - self.start_time > self.spark_time:
                self.state = 'get_next_spark'
                self.start_time = current_time

        elif self.state == 'get_next_spark':
            if self.inc_spark():
                game.events.trigger(triggers.DuringUnitLevelUp(self.unit, self.parent.stat_changes, self.parent.source))
                self.state = 'level_up_wait'
                self.start_time = current_time
            else:
                pos = self.get_position(self.current_spark)
                increase = self.stat_list[self.current_spark]
                arrow_nid = 'LevelUpArrow' if increase > 0 else 'LevelDownArrow'
                anim = RESOURCES.animations.get(arrow_nid)
                if anim:
                    self.arrow_animations.append(Animation(anim, (pos[0] + 45, pos[1] - 11), hold=True))

                offset_pos = self.get_position(self.current_spark, True)
                spark = self.make_spark((offset_pos[0] + 8, offset_pos[1] - 19))
                if spark:
                    self.animations.append(spark)

                num_nid = f'LevelUpNumber{increase}' if increase > 0 else f'LevelDownNumber{-increase}'
                anim = RESOURCES.animations.get(num_nid)
                if anim:
                    self.animations.append(Animation(anim, (offset_pos[0] + 37, offset_pos[1] + 4), delay=80, hold=True))
                else:
                    color = 'white' if increase > 0 else 'purple'
                    text = f'+{increase}' if increase > 0 else str(increase)
                    stat_font = 'ui_level_up_bonus' if 'ui_level_up_bonus' in FONT else 'stat'
                    self.simple_nums.append((stat_font, color, text, (offset_pos[0] + 57, offset_pos[1] - 2), current_time))

                get_sound_thread().play_sfx('Stat Up')
                self.underline_offset = 36
                self.state = 'spark_wait'
                self.start_time = current_time

        elif self.state == 'spark_wait':
            if current_time - self.start_time > self.spark_time:
                self.state = 'get_next_spark'

        elif self.state == 'level_up_wait':
            if current_time - self.start_time > self.level_up_wait:
                self.animations.clear()
                self.simple_nums.clear()
                self.state = 'scroll_out'
                self.start_time = current_time

    def draw(self, surf):
        sprite_top = self.bg_top.copy()
        sprite_bottom = self.bg_bottom.copy()
        t = math.sin(math.radians((engine.get_time() // 10) % 180))
        new_color = image_mods.blend_colors((88, 16, -40), (-80, -32, 40), t)

        klass = self.old_class.name if not self.flipped else DB.classes.get(self.unit.klass).name
        font = FONT['narrow'] if FONT['text'].width(klass) > 60 else FONT['text']
        font.blit(klass, sprite_top, (12, 3))
        FONT['text-yellow'].blit('Lv', sprite_top, (self.width // 2 + 12, 3))

        level = str(self.old_level) if self.state in ('scroll_in', 'init_wait') and not self.flipped else str(self.new_level)
        FONT['text-new-white'].blit(level, sprite_top, (self.width // 2 + 50 - FONT['text-new-white'].width(level), 3))

        if engine.get_time() > self.flip_start_time:
            self.flip_timer = (engine.get_time() - self.flip_start_time) / 333
        else:
            self.flip_timer = 0
        if self.flip_timer:
            sprite_top = image_mods.do_flip(sprite_top, self.flip_timer)

        surf.blit(sprite_top, self.topleft())

        new_underline_surf = image_mods.change_color(self.underline, new_color)
        for idx, num in enumerate(self.stat_list[:self.current_spark + 1]):
            if num != 0:
                if idx == self.current_spark:
                    rect = (self.underline_offset, 0, new_underline_surf.get_width() - self.underline_offset, 3)
                    clipped = engine.subsurface(new_underline_surf, rect)
                    self.underline_offset = max(0, self.underline_offset - 6)
                    pos = self.get_position(idx)
                    sprite_bottom.blit(clipped, (pos[0] + self.underline_offset // 2 + 1, pos[1] + 10))
                else:
                    pos = self.get_position(idx)
                    sprite_bottom.blit(new_underline_surf, (pos[0] + 4, pos[1] + 11))

        self.arrow_animations = [a for a in self.arrow_animations if not a.update()]
        for animation in self.arrow_animations:
            animation.draw(sprite_bottom, blend=new_color)

        for idx, stat in enumerate(DB.stats.keys()):
            if idx >= len(self.stat_list):
                continue
            pos = self.get_position(idx)
            render_text(sprite_bottom, ['text'], [DB.stats.get(stat).name], ['yellow'], pos)
            val = self.unit.stats[stat] - (self.stat_list[idx] if self.current_spark < idx else 0)
            FONT['text-new-white'].blit(str(val), sprite_bottom, (pos[0] + 40 - FONT['text-new-white'].width(str(val)), pos[1]))

        icons.draw_portrait(surf, self.unit, bottomright=(WINWIDTH - 4, WINHEIGHT + self.unit_scroll_offset))
        surf.blit(sprite_bottom, self.topleft())

        self.animations = [a for a in self.animations if not a.update()]
        for animation in self.animations:
            animation.draw(surf)

        for font_k, color, text, pos, time in self.simple_nums:
            if engine.get_time() - time > 80:
                render_text(surf, [font_k], [text], [color], pos, align=HAlignment.RIGHT)

        return surf


class ExpBar():
    background = engine.subsurface(SPRITES.get('expbar'), (0, 0, 144, 24))
    begin = engine.subsurface(SPRITES.get('expbar'), (0, 24, 3, 7))
    middle = engine.subsurface(SPRITES.get('expbar'), (3, 24, 1, 7))
    end = engine.subsurface(SPRITES.get('expbar'), (4, 24, 2, 7))
    width = 144
    height = 24
    bar_max = 100

    def __init__(self, old_exp, center=True):
        self.bg_surf = self.create_bg_surf()
        self.pos = (WINWIDTH // 2 - self.width // 2, WINHEIGHT // 2 - self.height // 2) if center else (WINWIDTH // 2 - self.width // 2, WINHEIGHT - self.height)
        self.offset = self.height // 2
        self.done = False
        self.num = old_exp

    def create_bg_surf(self):
        surf = engine.create_surface((self.width, self.height), transparent=True)
        surf.blit(self.background, (0, 0))
        surf.blit(self.begin, (7, 9))
        return surf

    def fade_out(self):
        self.done = True

    def update(self, exp: float = None):
        if self.done:
            self.offset += 1
            if self.offset >= self.height // 2:
                return True
        elif self.offset > 0:
            self.offset -= 1

        if exp is not None:
            self.num = exp

    def draw(self, surf):
        new_surf = engine.copy_surface(self.bg_surf)
        idx = int(100 * max(0, self.num) / self.bar_max)
        for x in range(idx):
            new_surf.blit(self.middle, (10 + x, 9))
        new_surf.blit(self.end, (10 + idx, 9))
        FONT['number_small3'].blit_right(str(int(self.num)), new_surf, (self.width - 8, 4))
        new_surf = engine.subsurface(new_surf, (0, self.offset, self.width, self.height - self.offset * 2))
        surf.blit(new_surf, (self.pos[0], self.pos[1] + self.offset))
        return surf


class ManaBar(ExpBar):
    background = engine.subsurface(SPRITES.get('manabar'), (0, 0, 136, 24))
    begin = engine.subsurface(SPRITES.get('manabar'), (0, 24, 3, 7))
    middle = engine.subsurface(SPRITES.get('manabar'), (3, 24, 1, 7))
    end = engine.subsurface(SPRITES.get('manabar'), (4, 24, 2, 7))

    def __init__(self, old_exp, center=True):
        super().__init__(old_exp, center)
        self.pos = self.pos[0], self.pos[1] - self.height


class SkillSwapLevelUpState(State):
    name = 'skill_swap_levelup'
    transparent = True

    def __init__(self, name=None):
        super().__init__(name)
        self.unit = None
        self.new_skill_nid = None
        self.source = None
        self.source_type = None
        self.new_skill_obj = None

        self.equipped_skills = []
        self.fluid = FluidScroll()
        self.menu = None
        self.button_disp = None
        self.help_dialog = None
        self.help_pos = (0, 0)

        self.window_bg = None
        self.right_window_bg = None
        self.confirm_bg = None
        self.confirm_cursor = menus.Cursor()

        self.confirming = False
        self.pending_action = None
        self.pending_skill_idx = None
        self.confirm_idx = 0
        self.confirm_prompt = ""
        self.confirm_font = 'text'
        self.confirm_box_w = 120
        self.confirm_box_h = 52
        self.confirm_box_x = 60
        self.confirm_box_y = 54

    def start(self):
        queue = game.memory.get('skill_swap_queue', [])
        if not queue:
            game.state.back()
            return 'repeat'

        self.unit, self.new_skill_nid, self.source, self.source_type = queue.pop(0)
        self.new_skill_obj = item_funcs.create_skill(self.unit, self.new_skill_nid)
        
        # Garante a unidade viva e atualizada com as habilidades mais recentes
        live_unit = self._get_live_unit()
        self.equipped_skills = live_unit.get_equipped_skills()

        # Reseta os estados de confirmação e tooltips
        self.confirming = False
        self.pending_action = None
        self.pending_skill_idx = None
        self.confirm_idx = 0
        self.confirm_prompt = ""
        self.confirm_cursor = menus.Cursor()
        self.help_dialog = None
        self.fluid.reset_on_change_state()

        # Painel de Habilidades Ativas (Direita: x=124)
        self.box_x, self.box_y = 124, 8
        self.window_bg = image_mods.make_translucent(base_surf.create_base_surf(114, 144, 'menu_bg_base'), 0.1)

        skill_names = [s.name for s in self.equipped_skills] or ['---']
        self.menu = menus.Choice(None, skill_names, topleft=(124, 28), background=None)
        self.menu.set_limit(7)
        self.menu.width = 98
        self.menu.draw_cursor = True

        # Painel da Nova Habilidade (Esquerda: x=6)
        self.right_box_x, self.right_box_y = 6, 8
        self.right_window_bg = image_mods.make_translucent(base_surf.create_base_surf(110, 108, 'menu_bg_base'), 0.1)

        desc_text = getattr(self.new_skill_obj, 'desc', '') or "No description."
        self.new_skill_desc_lines = self._wrap_text(FONT['narrow'], desc_text, 98)
        self.button_disp = self._create_button_disp()

    def begin(self):
        self.fluid.reset_on_change_state()

    def _create_button_disp(self):
        sprite = SPRITES.get('buttons')
        if not sprite:
            return None
        bg_surf = image_mods.make_translucent(base_surf.create_base_surf(110, 24, 'menu_bg_base'), 0.1)
        bg_surf.blit(sprite.subsurface(0, 66, 14, 13), (6, 5))
        FONT['narrow'].blit('Confirm', bg_surf, (22, 5))
        bg_surf.blit(sprite.subsurface(0, 82, 14, 13), (60, 5))
        FONT['narrow'].blit('Cancel', bg_surf, (76, 5))
        return bg_surf

    def _wrap_text(self, font, text: str, max_width: int):
        words = text.split(' ')
        lines, cur_line = [], []
        for word in words:
            test_line = ' '.join(cur_line + [word])
            if font.width(test_line) <= max_width:
                cur_line.append(word)
            else:
                if cur_line:
                    lines.append(' '.join(cur_line))
                cur_line = [word]
        if cur_line:
            lines.append(' '.join(cur_line))
        return lines

    def _update_help_dialog(self):
        if not self.menu:
            return
        idx = self.menu.get_current_index()
        if idx >= len(self.equipped_skills):
            return

        hovered = self.equipped_skills[idx]
        rel_idx = idx - getattr(self.menu, 'scroll', 0)
        # Ancora o balão centralizado sobre o contêiner direito
        self.help_pos = (self.box_x + 56, self.menu.topleft[1] + (rel_idx * 16) + 8)

        desc = getattr(hovered, 'desc', '') or "No description."
        HelpDialogClass = getattr(help_menu, 'HelpDialog', getattr(help_menu, 'HelpBox', None))
        self.help_dialog = HelpDialogClass(desc) if HelpDialogClass else None

    def _open_confirmation(self, action_type, skill_idx=None):
        self.confirming = True
        self.pending_action = action_type
        self.pending_skill_idx = skill_idx
        self.confirm_idx = 0

        if action_type == 'swap' and skill_idx is not None and skill_idx < len(self.equipped_skills):
            self.confirm_prompt = f"Replace {self.equipped_skills[skill_idx].name}?"
        else:
            self.confirm_prompt = "Send to reserve?"

        standard_w = text_width('text', self.confirm_prompt)
        if standard_w > 180:
            self.confirm_font = 'narrow'
            prompt_w = text_width('narrow', self.confirm_prompt)
        else:
            self.confirm_font = 'text'
            prompt_w = standard_w

        self.confirm_box_w = max(124, min(WINWIDTH - 12, prompt_w + 24))
        self.confirm_box_x = (WINWIDTH - self.confirm_box_w) // 2
        self.confirm_bg = image_mods.make_translucent(
            base_surf.create_base_surf(self.confirm_box_w, self.confirm_box_h, 'menu_bg_base'), 0.08
        )

    def _get_live_unit(self):
        return game.get_unit(self.unit.nid) or self.unit

    def _finish_and_alert(self, unit, skill_obj, custom_text=None):
        if skill_obj and not skill_system.hidden(skill_obj, unit):
            msg = custom_text or f"{unit.name} learned {skill_obj.name}!"
            alert = banner.CustomSkillBanner(unit, skill_obj, msg)
            game.alerts.append(alert)
            self.finish(has_alert=True)
        else:
            self.finish(has_alert=False)

    def _execute_swap(self):
        unit = self._get_live_unit()
        old_skill = self.equipped_skills[self.pending_skill_idx]

        # 1. Garante o registro permanente da nova skill na reserva
        if not hasattr(unit, 'learned_skills'):
            unit.learned_skills = []
        if self.new_skill_nid not in unit.learned_skills:
            unit.learned_skills.append(self.new_skill_nid)

        # 2. Se a skill desequipada for uma aura, remove do tabuleiro e dos aliados nativamente
        if hasattr(old_skill, 'aura') and old_skill.aura and hasattr(old_skill, 'subskill'):
            if unit.position and getattr(game, 'board', None):
                aura_funcs.release_aura(unit, old_skill, game)

        # 3. Desequipa a habilidade da unidade
        if hasattr(unit, 'unequip_skill'):
            unit.unequip_skill(old_skill.nid)
        else:
            parent_skill_obj = next((s for s in unit.skills if s.nid == old_skill.nid), None)
            if parent_skill_obj:
                try:
                    action.RemoveSkill(unit, parent_skill_obj).do()
                except Exception:
                    if parent_skill_obj in unit.skills:
                        unit.skills.remove(parent_skill_obj)

        # 4. Adiciona a nova habilidade nos slots ativos da engine
        source = unit.klass if self.source_type == SourceType.KLASS else unit.nid
        act = action.AddSkill(unit, self.new_skill_nid, source=source, source_type=self.source_type)
        action.do(act)

        # 5. Se a nova skill for uma aura, propaga imediatamente pelo tabuleiro
        new_skill_obj = act.skill_obj or self.new_skill_obj
        if new_skill_obj and hasattr(new_skill_obj, 'aura') and new_skill_obj.aura and hasattr(new_skill_obj, 'subskill'):
            if unit.position and getattr(game, 'board', None):
                aura_funcs.propagate_aura(unit, new_skill_obj, game)

        # 6. Atualiza o cache de skills da unidade
        if hasattr(unit, '_visible_skills_cache'):
            unit._visible_skills_cache = None

        # 7. Dispara o banner formatado via _finish_and_alert
        skill_obj_to_show = act.skill_obj or self.new_skill_obj
        swap_text = f"{unit.name} swapped {old_skill.name} for {skill_obj_to_show.name}"
        self._finish_and_alert(unit, skill_obj_to_show, custom_text=swap_text)

    def _execute_keep_learned(self):
        unit = self._get_live_unit()
        if not hasattr(unit, 'learned_skills') or unit.learned_skills is None:
            unit.learned_skills = []
        if self.new_skill_nid not in unit.learned_skills:
            unit.learned_skills.append(self.new_skill_nid)

        reserve_text = f"{unit.name} reserved {self.new_skill_obj.name}!"
        self._finish_and_alert(unit, self.new_skill_obj, custom_text=reserve_text)

    def take_input(self, event):
        first_push = self.fluid.update()
        directions = self.fluid.get_directions()

        if self.confirming:
            if event == 'LEFT' or 'LEFT' in directions:
                if self.confirm_idx != 0:
                    get_sound_thread().play_sfx('Select 5')
                    self.confirm_idx = 0
            elif event == 'RIGHT' or 'RIGHT' in directions:
                if self.confirm_idx != 1:
                    get_sound_thread().play_sfx('Select 5')
                    self.confirm_idx = 1
            elif event in ('UP', 'DOWN') or 'UP' in directions or 'DOWN' in directions:
                get_sound_thread().play_sfx('Select 5')
                self.confirm_idx = 1 - self.confirm_idx

            if event == 'BACK':
                get_sound_thread().play_sfx('Select 4')
                self.confirming = False
            elif event == 'SELECT':
                if self.confirm_idx == 0:
                    get_sound_thread().play_sfx('Select 1')
                    self.confirming = False
                    if self.pending_action == 'swap':
                        self._execute_swap()
                    else:
                        self._execute_keep_learned()
                else:
                    get_sound_thread().play_sfx('Select 4')
                    self.confirming = False
            return

        if self.help_dialog:
            if event in ('INFO', 'BACK', 'SELECT'):
                self.help_dialog = None
                get_sound_thread().play_sfx('Info Out')
                return

            if self.menu:
                moved = False
                if 'DOWN' in directions or event == 'DOWN':
                    moved = self.menu.move_down(first_push)
                elif 'UP' in directions or event == 'UP':
                    moved = self.menu.move_up(first_push)

                if moved:
                    get_sound_thread().play_sfx('Select 5')
                    self._update_help_dialog()
            return

        if self.menu:
            self.menu.handle_mouse()

        if 'DOWN' in directions or event == 'DOWN':
            if self.menu and self.menu.move_down(first_push):
                get_sound_thread().play_sfx('Select 5')
        elif 'UP' in directions or event == 'UP':
            if self.menu and self.menu.move_up(first_push):
                get_sound_thread().play_sfx('Select 5')
        elif event == 'INFO':
            if self.menu and self.menu.get_current_index() < len(self.equipped_skills):
                self._update_help_dialog()
                get_sound_thread().play_sfx('Info In')
        elif event == 'BACK':
            get_sound_thread().play_sfx('Select 4')
            self._open_confirmation('cancel')
        elif event == 'SELECT':
            cur_idx = self.menu.get_current_index() if self.menu else 0
            if self.equipped_skills and cur_idx < len(self.equipped_skills):
                get_sound_thread().play_sfx('Select 1')
                self._open_confirmation('swap', cur_idx)

    def update(self):
        super().update()
        if self.confirming and self.confirm_cursor:
            self.confirm_cursor.update()
        elif self.menu:
            self.menu.update()

        if self.help_dialog and hasattr(self.help_dialog, 'update'):
            self.help_dialog.update()

    def finish(self, has_alert: bool = False):
        queue = game.memory.get('skill_swap_queue', [])
        if queue:
            self.start()
            if has_alert:
                game.state.change('alert')
        else:
            if 'skill_swap_queue' in game.memory:
                del game.memory['skill_swap_queue']
            game.state.back()
            if has_alert:
                game.state.change('alert')

    def draw(self, surf):
        if not getattr(self, 'window_bg', None):
            return surf

        # 1. Contêiner de Skills Ativas (Direita)
        surf.blit(self.window_bg, (self.box_x, self.box_y))
        slots_count = f"{len(self.equipped_skills)}/{self.unit.max_skills}"
        slots_color = 'yellow' if len(self.equipped_skills) < self.unit.max_skills else 'green'

        render_text(surf, ['text'], ["Skills"], ['yellow'], (self.box_x + 8, 13))
        start_x = (self.box_x + 104) - FONT['text'].width("Slots:") - FONT['text'].width(slots_count)
        render_text(surf, ['text'], ["Slots:"], ['white'], (start_x, 13))
        render_text(surf, ['text'], [slots_count], [slots_color], (start_x + FONT['text'].width("Slots:") + 3, 13))

        if self.menu:
            self.menu.draw(surf)

        # 2. Contêiner da Nova Skill (Esquerda)
        surf.blit(self.right_window_bg, (self.right_box_x, self.right_box_y))
        
        # Título "New Skill Learned" centralizado no contêiner de 110px em verde
        title_text = "New Skill Learned"
        title_w = text_width('text', title_text)
        title_x = self.right_box_x + (110 - title_w) // 2
        render_text(surf, ['text'], [title_text], ['green'], (title_x, 13))

        new_name = self.new_skill_obj.name
        name_font = 'narrow' if text_width('text', new_name) > 98 else 'text'
        render_text(surf, [name_font], [new_name], ['white'], (self.right_box_x + 6, 28))

        for idx, line in enumerate(self.new_skill_desc_lines[:6]):
            render_text(surf, ['narrow'], [line], ['white'], (self.right_box_x + 6, 44 + idx * 11))

        # Botões posicionados logo abaixo do contêiner da esquerda (x=6, y=128)
        if self.button_disp:
            surf.blit(self.button_disp, (self.right_box_x, 128))

        if self.help_dialog:
            self.help_dialog.draw(surf, self.help_pos)

        # Janela de confirmação
        if self.confirming and self.confirm_bg:
            surf.blit(self.confirm_bg, (self.confirm_box_x, self.confirm_box_y))
            prompt_w = text_width(self.confirm_font, self.confirm_prompt)
            prompt_x = self.confirm_box_x + (self.confirm_box_w - prompt_w) // 2
            render_text(surf, [self.confirm_font], [self.confirm_prompt], ['yellow'], (prompt_x, self.confirm_box_y + 7))

            center_x = self.confirm_box_x + self.confirm_box_w // 2
            render_text(surf, ['text'], ["Yes"], ['yellow' if self.confirm_idx == 0 else 'white'], (center_x - 34, self.confirm_box_y + 28))
            render_text(surf, ['text'], ["No"], ['yellow' if self.confirm_idx == 1 else 'white'], (center_x + 24, self.confirm_box_y + 28))

            cursor_x = (center_x - 50) if self.confirm_idx == 0 else (center_x + 8)
            self.confirm_cursor.draw(surf, cursor_x, self.confirm_box_y + 28)

        return surf