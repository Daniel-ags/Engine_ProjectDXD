from __future__ import annotations

import random
from typing import Optional

from app.engine.sprites import SPRITES
from app.engine import engine, image_mods

import logging

# For bg surfs that don't have `_bg` in their name
HARDCODED_BG_SURFS = [
    'name_tag'
]

SLICE_9_WIDTH = 8
SLICE_9_HEIGHT = 8

def create_base_surf(width: int, height: int, base: Optional[str] = 'menu_bg_base') -> engine.Surface:
    """
    Given the width and height of a desired surface along with a base surface (usually 24x24),
    uses slice 9 pattern to create a surface of the desired size.

    If the base surface is larger than 24x24, each of it's additional slice 9 sprites are randomized
    during the drawing of the desired surface
    """

    sprite = SPRITES.get(base, 'menu_bg_base')
    if base and '_bg' not in base and base not in HARDCODED_BG_SURFS:
        new_base_surf = engine.create_surface((width, height), transparent=True)
        new_base_surf.blit(sprite, (0, 0))
        return new_base_surf

    base_width = sprite.get_width()
    base_height = sprite.get_height()

    assert (base_width % SLICE_9_WIDTH) == 0
    assert (base_height % SLICE_9_HEIGHT) == 0

    desired_width = width - (width % SLICE_9_WIDTH)
    desired_height = height - (height % SLICE_9_HEIGHT)
    surf = engine.create_surface((desired_width, desired_height), transparent=True)

    # Gather up the pieces of the base surface
    # Corners
    topleft = engine.subsurface(sprite, (0, 0, SLICE_9_WIDTH, SLICE_9_HEIGHT))
    topright = engine.subsurface(sprite, (base_width - SLICE_9_WIDTH, 0, SLICE_9_WIDTH, SLICE_9_HEIGHT))
    botleft = engine.subsurface(sprite, (0, base_height - SLICE_9_HEIGHT, SLICE_9_WIDTH, SLICE_9_HEIGHT))
    botright = engine.subsurface(sprite, (base_width - SLICE_9_WIDTH, base_height - SLICE_9_HEIGHT, SLICE_9_WIDTH, SLICE_9_HEIGHT))

    top, left, right, bot, center = [], [], [], [], []
    # Sides
    for x in range(SLICE_9_WIDTH, base_width - SLICE_9_WIDTH, SLICE_9_WIDTH):
        top.append(engine.subsurface(sprite, (x, 0, SLICE_9_WIDTH, SLICE_9_HEIGHT)))
        bot.append(engine.subsurface(sprite, (x, base_height - SLICE_9_HEIGHT, SLICE_9_WIDTH, SLICE_9_HEIGHT)))
    for y in range(SLICE_9_HEIGHT, base_height - SLICE_9_HEIGHT, SLICE_9_HEIGHT):
        left.append(engine.subsurface(sprite, (0, y, SLICE_9_WIDTH, SLICE_9_HEIGHT)))
        right.append(engine.subsurface(sprite, (base_width - SLICE_9_WIDTH, y, SLICE_9_WIDTH, SLICE_9_HEIGHT)))

    # Center
    for x in range(SLICE_9_WIDTH, base_width - SLICE_9_WIDTH, SLICE_9_WIDTH):
        for y in range(SLICE_9_HEIGHT, base_height - SLICE_9_HEIGHT, SLICE_9_HEIGHT):
            center.append(engine.subsurface(sprite, (x, y, SLICE_9_WIDTH, SLICE_9_HEIGHT)))

    # Now draw on the desired sprite
    for x in range(SLICE_9_WIDTH, desired_width - SLICE_9_WIDTH, SLICE_9_WIDTH):
        for y in range(SLICE_9_HEIGHT, desired_height - SLICE_9_HEIGHT, SLICE_9_HEIGHT):
            surf.blit(random.choice(center), (x, y))

    # Edges
    for x in range(SLICE_9_WIDTH, desired_width - SLICE_9_WIDTH, SLICE_9_WIDTH):
        surf.blit(random.choice(top), (x, 0))
        surf.blit(random.choice(bot), (x, desired_height - SLICE_9_HEIGHT))

    for y in range(SLICE_9_HEIGHT, desired_height - SLICE_9_HEIGHT, SLICE_9_HEIGHT):
        surf.blit(random.choice(left), (0, y))
        surf.blit(random.choice(right), (desired_width - SLICE_9_WIDTH, y))

    # Corners
    surf.blit(topleft, (0, 0))
    surf.blit(topright, (desired_width - SLICE_9_WIDTH, 0))
    surf.blit(botleft, (0, desired_height - SLICE_9_HEIGHT))
    surf.blit(botright, (desired_width - SLICE_9_WIDTH, desired_height - SLICE_9_HEIGHT))

    return surf

def create_highlight_surf(width) -> engine.Surface:
    if width < 5:
        raise ValueError("Highlight surf too short - why are you even calling this?")
    sprite: engine.Surface = SPRITES.get('equipment_highlight')

    base_width = sprite.get_width()
    base_height = sprite.get_height()

    left_endcap = engine.subsurface(sprite, (0, 0, 2, base_height))
    middle_segment = engine.subsurface(sprite, (3, 0, 1, base_height))
    right_endcap = engine.subsurface(sprite, (base_width - 2, 0, 2, base_height))

    surf = engine.create_surface((width, base_height), transparent=True)
    surf.blit(left_endcap, (0, 0))
    for middle_x in range(2, width - 2):
        surf.blit(middle_segment, (middle_x, 0))
    surf.blit(right_endcap, (width - 2, 0))

    return surf

def create_ornate_base_surf(width: int, height: int, background: str = 'menu_bg_base',
                            gems: str = 'top_left', gem_type: str = 'small',
                            translucency: float = 0.1):
    """
    Cria uma superfície de base 9-slice ornamentada com gemas/diamantes projetados.
    
    :param width: Largura útil da moldura interna (em múltiplos de 8px).
    :param height: Altura útil da moldura interna.
    :param background: ID do sprite 9-slice base (ex: 'menu_bg_base').
    :param gems: 'top_left', 'diagonal', 'all' ou None.
    :param gem_type: 'small' (gema azul padrão) ou 'brown'.
    :param translucency: Nível de transparência (0.1 por padrão).
    :return: Superfície pronta (pygame.Surface).
    """
    # 1. Gera a moldura 9-slice tradicional
    raw_bg = create_base_surf(width, height, background)

    # 2. Se nenhuma gema for solicitada, retorna a base comum
    if not gems:
        if translucency:
            raw_bg = image_mods.make_translucent(raw_bg, translucency)
        return raw_bg

    # 3. Cria o envelope transparente (+8px largura, +12px altura para acomodar as saliências)
    surf = engine.create_surface((width + 8, height + 12), transparent=True)
    # A moldura interna fica ancorada em (2, 4)
    surf.blit(raw_bg, (2, 4))

    # 4. Seleção e renderização das gemas
    gem_key = 'menu_gem_brown' if gem_type == 'brown' else 'menu_gem_small'
    gem_sprite = SPRITES.get(gem_key)

    if gem_sprite:
        gem_w = gem_sprite.get_width()
        gem_h = gem_sprite.get_height()

        # Coordenadas calibradas das quinas
        tl_pos = (0, 0)
        br_pos = ((2 + width) - gem_w + 2, (4 + height) - gem_h + 3)
        tr_pos = ((2 + width) - gem_w + 2, 0)
        bl_pos = (0, (4 + height) - gem_h + 3)

        # Topo Esquerdo (padrão em quase todos os modos)
        if gems in ('top_left', 'diagonal', 'all'):
            surf.blit(gem_sprite, tl_pos)

        # Inferior Direito (espelhado horizontal e verticalmente)
        if gems in ('diagonal', 'all'):
            try:
                br_gem = engine.flip_vert(engine.flip_horiz(gem_sprite))
            except AttributeError:
                import pygame
                br_gem = pygame.transform.flip(gem_sprite, True, True)
            surf.blit(br_gem, br_pos)

        # Demais cantos caso 'all' seja solicitado
        if gems == 'all':
            try:
                tr_gem = engine.flip_horiz(gem_sprite)
                bl_gem = engine.flip_vert(gem_sprite)
            except AttributeError:
                import pygame
                tr_gem = pygame.transform.flip(gem_sprite, True, False)
                bl_gem = pygame.transform.flip(gem_sprite, False, True)
            surf.blit(tr_gem, tr_pos)
            surf.blit(bl_gem, bl_pos)

    # 5. Aplica a translucidez uniforme no conjunto inteiro
    if translucency:
        surf = image_mods.make_translucent(surf, translucency)

    return surf