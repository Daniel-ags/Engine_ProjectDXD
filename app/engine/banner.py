from __future__ import annotations

from app.constants import WINWIDTH, WINHEIGHT
from app.engine.sprites import SPRITES
from app.engine import engine, base_surf, image_mods, icons, text_funcs, item_system
from app.engine.graphics.text.text_renderer import text_width, render_text
from app.data.database import skills, items
from app.data.database.database import DB

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.engine.objects.item import ItemObject
    from app.engine.objects.skill import SkillObject
    from app.engine.objects.unit import UnitObject

class Banner():
    update_flag = False
    time_to_pause = 300
    time_to_wait = 3000
    time_to_start = None
    remove_flag = False
    surf = None

    def __init__(self):
        self.text = ""
        self.item = None
        self.sound = None

    def figure_out_size(self):
        self.length = text_width('text', self.text)
        self.length += 16
        self.length -= self.length%8
        self.length += (16 if self.item else 0)
        self.font_height = 16
        self.size = self.length, 24

    def update(self):
        if not self.update_flag:
            self.update_flag = True
            self.time_to_start = engine.get_time()
            # play sound
            if self.sound:
                from app.engine.sound import get_sound_thread
                get_sound_thread().play_sfx(self.sound)
        if engine.get_time() - self.time_to_start > self.time_to_wait:
            self.remove_flag = True

    def draw_icon(self, surf):
        if self.item:
            icons.draw_item(surf, self.item, (self.size[0] - 20, 8), cooldown=False)

    def draw(self, surf):
        if not self.surf:
            w, h = self.size
            bg_surf = base_surf.create_base_surf(w, h, 'menu_bg_base')
            self.surf = engine.create_surface((w + 2, h + 4), transparent=True)
            self.surf.blit(bg_surf, (2, 4))
            self.surf.blit(SPRITES.get('menu_gem_small'), (0, 0))
            self.surf = image_mods.make_translucent(self.surf, .1)

        bg_surf = self.surf.copy()

        render_text(bg_surf, ['text'], [self.text], ['white'], topleft=(6, self.size[1]//2 - self.font_height//2 + 3))

        self.draw_icon(bg_surf)

        engine.blit_center(surf, bg_surf)
        return surf

class AcquiredItem(Banner):
    def __init__(self, unit: UnitObject, item: ItemObject):
        super().__init__()
        self.unit = unit
        self.item = item
        if item.special_article:
            if item.special_article.value is not None:
                article = item.special_article.value
            else:
                article = ''
        else:    
            article = 'an' if self.item.name.lower()[0] in ('a', 'e', 'i', 'o', 'u') else 'a'
        item_color = item_system.text_color(None, item) if item_system.text_color(None, item) else 'blue'
        if "'" in self.item.name or article == '':
            # No article for things like Prim's Charm, Ophie's Blade, etc.
            self.text = '<blue>{name}</> got <{item_color}>{item_name}</>.'.format(name=unit.name, item_color=item_color, item_name=item.name)
        else:
            self.text = '<blue>{name}</> got {article} <{item_color}>{item_name}</>.'.format(name=unit.name, article=article, item_color=item_color, item_name=item.name)
        self.figure_out_size()
        self.sound = 'Item'

class StoleItem(Banner):
    def __init__(self, unit, item):
        super().__init__()
        self.unit = unit
        self.item = item
        if item.special_article:
            if item.special_article.value is not None:
                article = item.special_article.value
            else:
                article = ''
        else:    
            article = 'an' if self.item.name.lower()[0] in ('a', 'e', 'i', 'o', 'u') else 'a'
        item_color = item_system.text_color(None, item) if item_system.text_color(None, item) else 'blue'
        if "'" in self.item.name or article == '':
            # No article for things like Prim's Charm, Ophie's Blade, etc.
            self.text = '<blue>{name}</> stole <{item_color}>{item_name}</>.'.format(name=unit.name, item_color=item_color, item_name=item.name)
        else:
            self.text = '<blue>{name}</> stole {article} <{item_color}>{item_name}</>.'.format(name=unit.name, article=article, item_color=item_color, item_name=item.name)
        self.figure_out_size()
        if self.unit.team in DB.teams.allies:
            self.sound = 'Item'
        else:
            self.sound = 'ItemBreak'

class SentToConvoy(Banner):
    def __init__(self, item: ItemObject):
        super().__init__()
        self.item = item
        item_color = item_system.text_color(None, item) if item_system.text_color(None, item) else 'blue'
        self.text = '<{item_color}>{item_name}</> sent to convoy.'.format(item_color=item_color, item_name=item.name)
        self.figure_out_size()
        self.sound = 'Item'

class LostItem(Banner):
    def __init__(self, item: ItemObject):
        super().__init__()
        self.item = item
        item_color = item_system.text_color(None, item) if item_system.text_color(None, item) else 'blue'
        self.text = '<{item_color}>{item_name}</> was discarded.'.format(item_color=item_color, item_name=item.name)
        self.figure_out_size()
        self.sound = 'ItemBreak'

class BrokenItem(Banner):
    def __init__(self, unit: UnitObject, item: ItemObject):
        super().__init__()
        self.unit = unit
        self.item = item
        item_color = item_system.text_color(None, item) if item_system.text_color(None, item) else 'blue'
        self.text = '<{item_color}>{item_name}</> broke.'.format(item_color=item_color, item_name=item.name)
        self.figure_out_size()
        self.sound = 'ItemBreak'

class TakeItem(BrokenItem):
    def __init__(self, unit: UnitObject, item: ItemObject):
        super().__init__(unit, item)
        item_color = item_system.text_color(None, item) if item_system.text_color(None, item) else 'blue'
        self.text = '<blue>{name}</> lost <{item_color}>{item_name}</>.'.format(name=unit.name, item_color=item_color, item_name=item.name)
        self.figure_out_size()

class GainWexp(Banner):
    def __init__(self, unit, weapon_rank, weapon_type):
        super().__init__()
        self.unit = unit
        self.weapon_type = self.item = weapon_type
        self.weapon_rank = weapon_rank
        self.text = '<blue>{name}</> reached rank <blue>{rank_name}</>.'.format(name=unit.name, rank_name=self.weapon_rank)
        self.figure_out_size()
        self.sound = 'Item'

    def draw_icon(self, surf):
        if self.weapon_type:
            icons.draw_weapon(surf, self.item, (self.size[0] - 20, 7))

class GiveSkill(Banner):
    def __init__(self, unit: UnitObject, skill: SkillObject, draw_icon: bool = True):
        super().__init__()
        self.unit = unit
        self.item = skill if draw_icon else None
        self.text = '<blue>{name}</> got <blue>{skill_name}</>'.format(name=unit.name, skill_name=skill.name)
        self.figure_out_size()
        self.sound = 'Item'

    def draw_icon(self, surf):
        if self.item:
            icons.draw_skill(surf, self.item, (self.size[0] - 20, 7), simple=True)

class TakeSkill(GiveSkill):
    def __init__(self, unit: UnitObject, skill: SkillObject):
        super().__init__(unit, skill)
        self.text = '<blue>{name}</> lost <blue>{skill_name}</>.'.format(name=unit.name, skill_name=skill.name)
        self.figure_out_size()

class Custom(Banner):
    def __init__(self, text, sound=None):
        self.text = text_funcs.translate(text)
        self.item = None
        self.figure_out_size()
        self.sound = sound

class CustomIcon(Banner):
    def __init__(self, text, icon, sound=None):
        self.text = text
        self.item = icon
        self.figure_out_size()
        self.sound = sound

    def figure_out_size(self):
        self.length = text_width('text', self.text)
        self.length += 16
        self.length -= self.length%8
        self.length += (16 if self.item else 0)
        self.font_height = 16
        self.size = self.length, 24

    def draw_icon(self, surf):
        if self.item:
            if isinstance(self.item, skills.SkillPrefab):
                icons.draw_skill(surf, self.item, (4, 7), simple=True)
            elif isinstance(self.item, items.ItemPrefab):
                icons.draw_item(surf, self.item, (4, 7), cooldown=False)
            elif isinstance(self.item, str):
                icons.draw_icon_by_alias(surf, self.item, (4, 7))

    def draw(self, surf):
        if not self.surf:
            w, h = self.size
            bg_surf = base_surf.create_base_surf(w, h, 'menu_bg_base')
            self.surf = engine.create_surface((w + 2, h + 4), transparent=True)
            self.surf.blit(bg_surf, (2, 4))
            self.surf.blit(SPRITES.get('menu_gem_small'), (0, 0))
            self.surf = image_mods.make_translucent(self.surf, .1)

        bg_surf = self.surf.copy()

        render_text(bg_surf, ['text'], [self.text], ['white'], topleft=(22, self.size[1]//2 - self.font_height//2 + 3))

        self.draw_icon(bg_surf)

        engine.blit_center(surf, bg_surf)
        return surf

class Advanced(Banner):
    def __init__(self, text: list, sound=None):
        self.text = text
        self.item = None
        self.figure_out_size()
        self.sound = sound

class Pennant():
    """
    Lower banner that scrolls across bottom of screen
    """

    font = 'convo'

    def __init__(self, text):
        self.change_text(text)

        self.sprite_offset = 32

        self.width = WINWIDTH
        self.height = 16

        self.last_update = engine.get_time()

    def change_text(self, text):
        self.text = text_funcs.translate(text)
        self.text_width = text_width(self.font, self.text)
        self.text_counter = 0

    def draw(self, surf, draw_on_top=False):
        self.sprite_offset -= 4
        self.sprite_offset = max(0, self.sprite_offset)

        counter = int(-self.text_counter)

        # If cursor is all the way on the bottom of the map
        if draw_on_top:
            surf.blit(engine.flip_vert(SPRITES.get('pennant_bg')), (0, -self.sprite_offset))
            while counter < self.width:
                render_text(surf, [self.font], [self.text], ['white'], (counter, -self.sprite_offset))
                counter += self.text_width + 24
        else:
            surf.blit(SPRITES.get('pennant_bg'), (0, WINHEIGHT - self.height + self.sprite_offset))
            while counter < self.width:
                render_text(surf, [self.font], [self.text], ['white'], (counter, WINHEIGHT - self.height + self.sprite_offset))
                counter += self.text_width + 24

        self.text_counter += (engine.get_time() - self.last_update)/24
        if self.text_counter >= self.text_width + 24:
            self.text_counter = 0
        self.last_update = engine.get_time()
class CustomSkillBanner(GiveSkill):
    """
    Banner customizado para notificações de habilidades:
    - Suporta quebras manuais de linha (\n) sem separar o ícone do nome da skill.
    - Dimensões modulares na grade de 8px e centralização automática na tela.
    - Oculta o ícone avulso nativo (draw_icon=False), preservando os glifos do texto.
    """
    def __init__(self, unit: UnitObject, skill: SkillObject, text: str):
        super().__init__(unit, skill, draw_icon=False)
        self.sound = 'Item'

        # Divide estritamente por quebras explícitas de linha (\n)
        self.lines = [line.strip() for line in text.split('\n') if line.strip()]

        # text_width mede a largura real computando o glifo do ícone embutido
        max_text_width = max(text_width('text', line) for line in self.lines) if self.lines else 64

        # Largura adaptativa na grade de 8px (com 24px de respiro lateral)
        width = max(96, min(WINWIDTH - 16, ((max_text_width + 24 + 7) // 8) * 8))

        # Altura: 18px por linha + 16px de margem vertical simétrica
        raw_height = len(self.lines) * 18 + 16
        height = max(32, ((raw_height + 7) // 8) * 8)
        self.size = (width, height)

        self.bg_surf = image_mods.make_translucent(
            base_surf.create_base_surf(width, height, 'menu_bg_base'), 0.1
        )

    def draw(self, surf):
        bg_surf = self.bg_surf.copy()

        # Centralização vertical do bloco de texto
        total_text_h = len(self.lines) * 18
        start_y = (self.size[1] - total_text_h) // 2

        for idx, line in enumerate(self.lines):
            line_w = text_width('text', line)
            line_x = (self.size[0] - line_w) // 2
            line_y = start_y + idx * 18
            render_text(bg_surf, ['text'], [line], ['white'], topleft=(line_x, line_y))

        # Centralização do banner inteiro na tela (240x160)
        x = (WINWIDTH - self.size[0]) // 2
        y = (WINHEIGHT - self.size[1]) // 2
        surf.blit(bg_surf, (x, y))
        return surf