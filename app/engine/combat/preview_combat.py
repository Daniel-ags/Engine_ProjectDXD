from app.constants import WINWIDTH, WINHEIGHT
from app.data.database.database import DB
from app.data.resources.resources import RESOURCES
from app.engine.sound import get_sound_thread
from app.engine import engine, item_system, item_funcs, battle_animation, image_mods

class _CombatSponge:
    """Objeto curinga que absorve chamadas e atributos desconhecidos sem quebrar."""
    def __init__(self):
        self.lr_offset = []
        self.child_effects = []
        self.under_child_effects = []

    def __call__(self, *args, **kwargs):
        return 0

    def __getattr__(self, name):
        if name in ('child_effects', 'under_child_effects', 'lr_offset'):
            return []
        if any(w in name.lower() for w in ('dual', 'weapon', 'frame', 'item')):
            return True
        return _CombatSponge()

    def __getitem__(self, item):
        return 0

    def __int__(self):
        return 0

    def __float__(self):
        return 0.0

    def __bool__(self):
        return False

    def __iter__(self):
        return iter([])

    def __gt__(self, other):
        return False

    def __lt__(self, other):
        return False

    def __ge__(self, other):
        return False

    def __le__(self, other):
        return True

    def __eq__(self, other):
        return False

    def append(self, *args, **kwargs):
        pass

    def extend(self, *args, **kwargs):
        pass

    def clear(self):
        pass

class _DummyPartner(_CombatSponge):
    """Parceiro fictício para absorver eventos de impacto do oponente."""
    def damaged(self, *args, **kwargs):
        pass

    def dodge(self, *args, **kwargs):
        pass

    def flash(self, *args, **kwargs):
        pass

    def screen_dodge(self, *args, **kwargs):
        pass

class _CombatDummy:
    """Controlador mock que atua como arena de combate para a BattleAnimation."""
    def __init__(self):
        self.damage = 0
        self.heal = 0
        self.hit = True
        self.miss = False
        self.crit = False
        self.show_dual_frame = True
        self.dual_frame = True
        self.damage_numbers = []
        self.hp_bars = []
        self.actions = []
        self.hp_change_until = 0
        self.current_anim = None

    def get_damage(self):
        return 0

    def get_heal(self):
        return 0

    def is_no_damage_hit(self):
        return False

    def start_hit(self, sound=True, miss=False):
        # Hit-Stop autêntico (~380ms)
        self.hp_change_until = engine.get_time() + 380
        # Restaura a flag para permitir que múltiplos golpes na mesma animação também pausem
        if self.current_anim:
            self.current_anim.wait_for_hit = True

    def spell_hit(self):
        self.hp_change_until = engine.get_time() + 380
        if self.current_anim:
            self.current_anim.wait_for_hit = True

    def miss(self, *args, **kwargs):
        self.hp_change_until = engine.get_time() + 200

    def hit_spark(self, *args, **kwargs):
        pass

    def screen_flash(self, *args, **kwargs):
        pass

    def shake(self, *args, **kwargs):
        pass

    def _shake(self, *args, **kwargs):
        pass

    def pan(self, *args, **kwargs):
        pass

    def pan_away(self, *args, **kwargs):
        pass

    def pan_back(self, *args, **kwargs):
        pass

    def hit_modifiers(self, *args, **kwargs):
        pass

    def hit(self, *args, **kwargs):
        pass

    def __getattr__(self, name):
        return _CombatSponge()

class PreviewCombat:
    """Gerenciador completo da prévia visual de combate para menus."""
    def __init__(self, unit, class_options):
        self.unit = unit
        self.class_options = class_options

        self.dummy_combat = _CombatDummy()
        self.dummy_partner = _DummyPartner()

        self.animations = []
        for option in self.class_options:
            weapon_item = self._find_preview_weapon(option)
            anim = battle_animation.get_battle_anim(self.unit, weapon_item, klass=option)
            if anim:
                anim.pair(self.dummy_combat, self.dummy_partner, True, 0)
                if hasattr(anim, 'show_dual_frame'):
                    anim.show_dual_frame = True
                # Suprime o surgimento de efeitos visuais de magia externa (foco na coreografia do mago)
                anim.get_effect = lambda *args, **kwargs: None
            self.animations.append(anim)

        self.displayed_idx = 0
        self.target_idx = 0
        self.anim_state = 'SLIDE_IN'
        self.slide_offset = 80
        self.fade_alpha = 255
        self.wait_start_time = 0
        self.last_attack_time = engine.get_time()
        self.loop_timeout = 0

        initial_anim = self._get_current_anim()
        if initial_anim:
            self._reset_anim_to_stand(initial_anim)
            self.dummy_combat.current_anim = initial_anim

    def _find_preview_weapon(self, klass_nid):
        klass = DB.classes.get(klass_nid)
        if not klass:
            return None

        # 1. Itens equipados na unidade
        for item in self.unit.items:
            if item_system.is_weapon(self.unit, item):
                wtype = item_system.weapon_type(self.unit, item)
                if wtype in klass.wexp_gain and klass.wexp_gain[wtype].usable:
                    return item

        # 2. Starting items da unidade no DB
        unit_prefab = DB.units.get(self.unit.nid)
        if unit_prefab and hasattr(unit_prefab, 'starting_items'):
            for entry in unit_prefab.starting_items:
                if isinstance(entry, (list, tuple)) and len(entry) > 0:
                    item_nid = entry[0]
                elif isinstance(entry, str):
                    item_nid = entry
                elif hasattr(entry, 'nid'):
                    item_nid = entry.nid
                else:
                    continue

                if isinstance(item_nid, str):
                    item_obj = DB.items.get(item_nid)
                    if item_obj:
                        temp_item = item_funcs.create_item(self.unit, item_nid)
                        if temp_item and item_system.is_weapon(self.unit, temp_item):
                            wtype = item_system.weapon_type(self.unit, temp_item)
                            if wtype in klass.wexp_gain and klass.wexp_gain[wtype].usable:
                                return temp_item

        # 3. Fallback geral de armas
        for wtype, wexp in klass.wexp_gain.items():
            if wexp.usable:
                for item_obj in DB.items.values():
                    temp_item = item_funcs.create_item(self.unit, item_obj.nid)
                    if temp_item and item_system.is_weapon(self.unit, temp_item):
                        if item_system.weapon_type(self.unit, temp_item) == wtype:
                            return temp_item
        return None

    def _get_current_anim(self):
        if self.displayed_idx < len(self.animations):
            return self.animations[self.displayed_idx]
        return None

    def _reset_anim_to_stand(self, anim):
        if not anim:
            return
        anim.clear_all_effects()
        anim.end_current_pose()
        anim.current_frame = None
        anim.under_frame = None
        anim.over_frame = None
        anim.reset_frames()
        if hasattr(anim, 'show_dual_frame'):
            anim.show_dual_frame = True

    def _play_attack(self, anim):
        if not anim:
            return
        anim.clear_all_effects()
        if hasattr(anim, 'show_dual_frame'):
            anim.show_dual_frame = True
        anim.start_anim('Attack')
        self.dummy_combat.current_anim = anim
        self.loop_timeout = 0

    def change_class(self, new_idx):
        if new_idx == self.displayed_idx and self.anim_state != 'FADE_OUT':
            return
        self.target_idx = new_idx
        if self.anim_state == 'FADE_OUT':
            return

        self.anim_state = 'FADE_OUT'
        self.fade_alpha = 255
        curr_anim = self._get_current_anim()
        if curr_anim:
            curr_anim.clear_all_effects()

    def stabilize(self, current_idx):
        self.displayed_idx = current_idx
        self.target_idx = current_idx
        self.slide_offset = 0
        self.fade_alpha = 255
        self.anim_state = 'WAIT_BEFORE_ATTACK'
        self.wait_start_time = engine.get_time()
        anim = self._get_current_anim()
        if anim:
            self.dummy_combat.current_anim = anim

    def update(self):
        now = engine.get_time()

        if self.anim_state == 'FADE_OUT':
            self.fade_alpha -= 20
            if self.fade_alpha <= 0:
                self.fade_alpha = 0
                old_anim = self._get_current_anim()
                self._reset_anim_to_stand(old_anim)

                self.displayed_idx = self.target_idx
                new_anim = self._get_current_anim()
                self._reset_anim_to_stand(new_anim)
                self.dummy_combat.current_anim = new_anim

                self.slide_offset = 80
                self.fade_alpha = 255
                self.anim_state = 'SLIDE_IN'

        elif self.anim_state == 'SLIDE_IN':
            self.slide_offset -= 8
            if self.slide_offset <= 0:
                self.slide_offset = 0
                self.anim_state = 'WAIT_BEFORE_ATTACK'
                self.wait_start_time = now
            self._update_anim()

        elif self.anim_state == 'WAIT_BEFORE_ATTACK':
            self._update_anim()
            # Aguarda exatamente 1 segundo (1000ms) após o slide antes de desferir o golpe
            if now - self.wait_start_time >= 1000:
                anim = self._get_current_anim()
                if anim:
                    self._play_attack(anim)
                self.anim_state = 'DISPLAY'
                self.last_attack_time = now

        elif self.anim_state == 'DISPLAY':
            self._update_anim()
            # Repete o golpe a cada 5 segundos
            if now - self.last_attack_time >= 5000:
                anim = self._get_current_anim()
                if anim:
                    self._play_attack(anim)
                self.last_attack_time = now

    def _update_anim(self):
        anim = self._get_current_anim()
        if not anim:
            return

        now = engine.get_time()

        # 1. Gerenciamento do Hit-Stop (pausa e retomada no tempo certo)
        if self.dummy_combat.hp_change_until > 0:
            if now >= self.dummy_combat.hp_change_until:
                self.dummy_combat.hp_change_until = 0
                anim.resume()
                anim.wait_for_hit = True
        elif anim.state == 'wait':
            self.dummy_combat.hp_change_until = now + 380

        # 2. Destravamento de loop de classes ranged/mágicas
        if anim.loop:
            if self.loop_timeout == 0:
                self.loop_timeout = now + 350
            elif now >= self.loop_timeout:
                anim.end_loop()
                self.loop_timeout = 0
        else:
            self.loop_timeout = 0

        # 3. Mantém dual frames permanentemente ativos
        if hasattr(anim, 'show_dual_frame'):
            anim.show_dual_frame = True

        # 4. Avança frames silenciando SFX de batalha
        orig_sfx = get_sound_thread().play_sfx
        get_sound_thread().play_sfx = lambda *args, **kwargs: None
        try:
            anim.update()
        finally:
            get_sound_thread().play_sfx = orig_sfx

    def draw(self, surf, base_pos):
        anim = self._get_current_anim()
        if not anim:
            return

        pos_x = base_pos[0] + self.slide_offset
        pos_y = base_pos[1]
        shake_coord = (pos_x, pos_y)

        # Desenha corpo, armas atrás e armas na frente no mesmo plano
        def _render_all_layers(target_surf):
            anim.draw_under(target_surf, shake_coord)
            anim.draw(target_surf, shake_coord)
            anim.draw_over(target_surf, shake_coord)

        if self.fade_alpha < 255:
            temp_surf = engine.create_surface((WINWIDTH, WINHEIGHT), transparent=True)
            _render_all_layers(temp_surf)
            transparency = 1.0 - (self.fade_alpha / 255.0)
            temp_surf = image_mods.make_translucent(temp_surf, transparency)
            surf.blit(temp_surf, (0, 0))
        else:
            _render_all_layers(surf)