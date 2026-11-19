"""
TTF to Lex Talionis Font Converter (ttf_to_lt_font.py)
-----------------------------------------------------
Converte qualquer arquivo de fonte TrueType (.ttf) ou OpenType (.otf) em uma
fonte bitmap (.png e .idx) 100% compatível com a engine Lex Talionis.

Recursos:
- Grade customizável de células (padrão: 28 colunas x 7 linhas, 10x16 px).
- Suporte completo ao alfabeto latino, acentuação (pt-BR/es/en), números e pontuação.
- Inclusão automática das 28 ligaturas e símbolos de UI nativos da engine (Linha 6):
  setas duplas/triângulos (▲, ▼, ►, ◄, ↑, ↓, →, ←, ↔, ↕), comparadores (≤, ≥, ≠, ≡, ≈),
  setas lógicas (⇒, ⇐, ⇔), reticências (…), travessão (—), mais-ou-menos (±), vezes (×),
  ícones (★, ♥), notas musicais (♪, ♫) e aspas angulares («, »).
- Matrizes de fallback pixel-art para símbolos não cobertos pelo arquivo TTF.
- Quantização de cores estrita (3-Color com contorno, 2-Color com sombra ou monocromático)
  garantindo recolorização perfeita via `image_mods.color_convert_alpha` sem artefatos.
- Instalação e sincronização automática opcional com projetos (.ltproj) e `fonts.json`.
"""

import os
import sys
import json
import copy
import argparse
from typing import Dict, List, Tuple, Optional, Set

try:
    import pygame
except ImportError:
    print("[ERRO] Pygame não encontrado. Instale com: pip install pygame-ce ou pip install pygame")
    sys.exit(1)

# Dimensões e padrões da engine
DEFAULT_CELL_W = 10
DEFAULT_CELL_H = 16
DEFAULT_COLS = 28
DEFAULT_ROWS = 7
DEFAULT_TTF_SIZE = 10
DEFAULT_SPACE_WIDTH = 4

# Definições de paletas base
COLOR_TRANSPARENT = (0, 0, 0, 0)

# Perfil 3-Color UI (Face branca, Contorno preto, Meio-tom/Sombra cinza)
PALETTE_3COLOR_BODY = (248, 248, 248, 255)
PALETTE_3COLOR_OUTLINE = (0, 0, 0, 255)
PALETTE_3COLOR_SHADE = (84, 84, 84, 255)

# Perfil 2-Color Diálogo (Face escura, Sombra clara)
PALETTE_2COLOR_BODY = (40, 40, 40, 255)
PALETTE_2COLOR_SHADE = (184, 184, 184, 255)

# Matrizes de Fallback Pixel-Art para Símbolos de UI e Ligaturas
# Desenhadas especificamente para células de 10x16 da engine
FALLBACK_MATRICES: Dict[str, List[str]] = {
    '%': [
        "##..#",
        "##..#",
        "...#.",
        "..#..",
        "..#..",
        ".#...",
        "#..##",
        "#..##",
    ],
    '⇒': [
        "....#..",
        ".....#.",
        "######.",
        "......#",
        "######.",
        ".....#.",
        "....#..",
        ".......",
    ],
    '⇐': [
        "..#....",
        ".#.....",
        ".######",
        "#......",
        ".######",
        ".#.....",
        "..#....",
        ".......",
    ],
    '⇔': [
        "..#.#..",
        ".#...#.",
        "#######",
        "#.....#",
        "#######",
        ".#...#.",
        "..#.#..",
        ".......",
    ],
    '≤': [
        "...##",
        "..#..",
        ".#...",
        "..#..",
        "...##",
        ".....",
        "#####",
        ".....",
    ],
    '≥': [
        "##...",
        "..#..",
        "...#.",
        "..#..",
        "##...",
        ".....",
        "#####",
        ".....",
    ],
    '≠': [
        "....#",
        "...#.",
        "#####",
        "..#..",
        "#####",
        ".#...",
        "#....",
        ".....",
    ],
    '≡': [
        ".....",
        "#####",
        ".....",
        "#####",
        ".....",
        "#####",
        ".....",
        ".....",
    ],
    '≈': [
        ".....",
        ".##.#",
        "#..#.",
        ".....",
        ".##.#",
        "#..#.",
        ".....",
        ".....",
    ],
    '…': [
        ".....",
        ".....",
        ".....",
        ".....",
        ".....",
        ".....",
        "#.#.#",
        ".....",
    ],
    '—': [
        ".......",
        ".......",
        ".......",
        "#######",
        ".......",
        ".......",
        ".......",
        ".......",
    ],
    '±': [
        "..#..",
        "..#..",
        "#####",
        "..#..",
        "..#..",
        ".....",
        "#####",
        ".....",
    ],
    '×': [
        ".....",
        "#...#",
        ".#.#.",
        "..#..",
        ".#.#.",
        "#...#",
        ".....",
        ".....",
    ],
    '★': [
        "...#...",
        "...#...",
        "#######",
        ".#####.",
        "..###..",
        ".##.##.",
        "#.....#",
        ".......",
    ],
    '♥': [
        ".##.##.",
        "#######",
        "#######",
        ".#####.",
        "..###..",
        "...#...",
        ".......",
        ".......",
    ],
    '♪': [
        "..###",
        "..#.#",
        "..#..",
        "..#..",
        ".##..",
        "###..",
        ".##..",
        ".....",
    ],
    '♫': [
        ".#####",
        ".#...#",
        ".#...#",
        ".#..##",
        "##.###",
        "##..##",
        "......",
        "......",
    ],
    '«': [
        "..#..#",
        ".#..#.",
        "#..#..",
        ".#..#.",
        "..#..#",
        "......",
        "......",
        "......",
    ],
    '»': [
        "#..#..",
        ".#..#.",
        "..#..#",
        ".#..#.",
        "#..#..",
        "......",
        "......",
        "......",
    ],
    '▲': [
        "...#...",
        "..###..",
        ".#####.",
        "#######",
        ".......",
        ".......",
        ".......",
        ".......",
    ],
    '▼': [
        "#######",
        ".#####.",
        "..###..",
        "...#...",
        ".......",
        ".......",
        ".......",
        ".......",
    ],
    '►': [
        "#...",
        "##..",
        "###.",
        "####",
        "###.",
        "##..",
        "#...",
        "....",
    ],
    '◄': [
        "...#",
        "..##",
        ".###",
        "####",
        ".###",
        "..##",
        "...#",
        "....",
    ],
    '↑': [
        "..#..",
        ".###.",
        "#.#.#",
        "..#..",
        "..#..",
        "..#..",
        "..#..",
        ".....",
    ],
    '↓': [
        "..#..",
        "..#..",
        "..#..",
        "..#..",
        "#.#.#",
        ".###.",
        "..#..",
        ".....",
    ],
    '→': [
        "....#..",
        ".....#.",
        "#######",
        ".....#.",
        "....#..",
        ".......",
        ".......",
        ".......",
    ],
    '←': [
        "..#....",
        ".#.....",
        "#######",
        ".#.....",
        "..#....",
        ".......",
        ".......",
        ".......",
    ],
    '↕': [
        "..#..",
        ".###.",
        "#.#.#",
        "..#..",
        "#.#.#",
        ".###.",
        "..#..",
        ".....",
    ],
    '↔': [
        "..#.#..",
        ".#...#.",
        "#######",
        ".#...#.",
        "..#.#..",
        ".......",
        ".......",
        ".......",
    ],
}

# Layout canônico completo da engine (28 colunas x 7 linhas = 196 células, 197 entradas)
# (char, col, row, fallback_width)
NATIVE_IDX_LAYOUT: List[Tuple[str, int, int, int]] = [
    # Linha 0 (Minúsculas e Símbolos Iniciais)
    ("space", 0, 1, 4), ("﹘", 0, 1, 1), ("¶", 0, 1, 20), ("•", 1, 0, 6), ("@", 1, 1, 10),
    ("a", 2, 0, 6), ("b", 3, 0, 5), ("c", 4, 0, 5), ("d", 5, 0, 6), ("e", 6, 0, 5),
    ("f", 7, 0, 4), ("g", 8, 0, 5), ("h", 9, 0, 5), ("i", 10, 0, 2), ("j", 11, 0, 4),
    ("k", 12, 0, 5), ("l", 13, 0, 2), ("m", 14, 0, 6), ("n", 15, 0, 5), ("o", 16, 0, 5),
    ("p", 17, 0, 5), ("q", 18, 0, 5), ("r", 19, 0, 4), ("s", 20, 0, 5), ("t", 21, 0, 4),
    ("u", 22, 0, 5), ("v", 23, 0, 6), ("w", 24, 0, 6), ("x", 25, 0, 6), ("y", 26, 0, 5), ("z", 27, 0, 5),
    
    # Linha 1 (Maiúsculas)
    ("A", 2, 1, 5), ("B", 3, 1, 5), ("C", 4, 1, 5), ("D", 5, 1, 5), ("E", 6, 1, 5),
    ("F", 7, 1, 5), ("G", 8, 1, 5), ("H", 9, 1, 5), ("I", 10, 1, 4), ("J", 11, 1, 5),
    ("K", 12, 1, 5), ("L", 13, 1, 4), ("M", 14, 1, 6), ("N", 15, 1, 5), ("O", 16, 1, 5),
    ("P", 17, 1, 5), ("Q", 18, 1, 6), ("R", 19, 1, 5), ("S", 20, 1, 5), ("T", 21, 1, 6),
    ("U", 22, 1, 5), ("V", 23, 1, 6), ("W", 24, 1, 6), ("X", 25, 1, 6), ("Y", 26, 1, 6), ("Z", 27, 1, 5),
    
    # Linha 2 (Dígitos e Pontuação Básica)
    ("$", 0, 2, 8), ("0", 1, 2, 7), ("1", 2, 2, 7), ("2", 3, 2, 7), ("3", 4, 2, 7),
    ("4", 5, 2, 7), ("5", 6, 2, 7), ("6", 7, 2, 7), ("7", 8, 2, 7), ("8", 9, 2, 7),
    ("9", 10, 2, 7), ("-", 11, 2, 6), ("+", 12, 2, 6), ("=", 13, 2, 6), ("%", 14, 2, 6),
    ("~", 15, 2, 7), ("*", 16, 2, 6), ("#", 17, 2, 7), ("?", 18, 2, 7), ("!", 19, 2, 4),
    ("ª", 20, 2, 6), ("ŋ", 21, 2, 5), ("þ", 22, 2, 5), ("ø", 23, 2, 7), ("ß", 24, 2, 7),
    ("ƿ", 25, 2, 5), ("æ", 26, 2, 8), ("œ", 27, 2, 8),
    
    # Linha 3 (Delimitadores e Pontuação Secundária)
    ("(", 0, 3, 4), (")", 1, 3, 4), ("[", 2, 3, 4), ("]", 3, 3, 4), ("{", 4, 3, 5),
    ("}", 5, 3, 5), ("<", 6, 3, 5), (">", 7, 3, 5), ("/", 8, 3, 5), ("\\", 9, 3, 5),
    (".", 10, 3, 3), (",", 11, 3, 3), (":", 12, 3, 3), (";", 13, 3, 3), ("'", 14, 3, 2),
    ("\"", 15, 3, 4), ("_", 16, 3, 7), ("&", 17, 3, 6), ("¿", 18, 3, 7), ("¡", 19, 3, 4),
    ("º", 20, 3, 5), ("°", 21, 3, 6), ("Þ", 22, 3, 5), ("Ø", 23, 3, 7), ("⁊", 24, 3, 6),
    ("Ƿ", 25, 3, 5), ("Æ", 26, 3, 8), ("Œ", 27, 3, 8),
    
    # Linha 4 (Acentos Minúsculos)
    ("á", 0, 4, 6), ("à", 1, 4, 6), ("ã", 2, 4, 6), ("â", 3, 4, 6), ("å", 4, 4, 6),
    ("ä", 5, 4, 6), ("é", 6, 4, 5), ("è", 7, 4, 5), ("ê", 8, 4, 5), ("ë", 9, 4, 5),
    ("í", 10, 4, 2), ("ì", 11, 4, 3), ("î", 12, 4, 4), ("ï", 13, 4, 4), ("ó", 14, 4, 5),
    ("ò", 15, 4, 5), ("õ", 16, 4, 5), ("ô", 17, 4, 5), ("ö", 18, 4, 5), ("ú", 19, 4, 5),
    ("ù", 20, 4, 5), ("û", 21, 4, 5), ("ü", 22, 4, 5), ("ý", 23, 4, 5), ("ÿ", 24, 4, 5),
    ("ç", 25, 4, 5), ("ð", 26, 4, 6), ("ñ", 27, 4, 5),
    
    # Linha 5 (Acentos Maiúsculos)
    ("Á", 0, 5, 5), ("À", 1, 5, 5), ("Ã", 2, 5, 5), ("Â", 3, 5, 5), ("Ä", 4, 5, 5),
    ("Å", 5, 5, 5), ("É", 6, 5, 5), ("È", 7, 5, 5), ("Ê", 8, 5, 5), ("Ë", 9, 5, 5),
    ("Í", 10, 5, 4), ("Ì", 11, 5, 4), ("Î", 12, 5, 4), ("Ï", 13, 5, 4), ("Ó", 14, 5, 5),
    ("Ò", 15, 5, 5), ("Õ", 16, 5, 5), ("Ô", 17, 5, 5), ("Ö", 18, 5, 5), ("Ú", 19, 5, 5),
    ("Ù", 20, 5, 5), ("Û", 21, 5, 5), ("Ü", 22, 5, 5), ("Ý", 23, 5, 6), ("Ÿ", 24, 5, 6),
    ("Ç", 25, 5, 5), ("Ð", 26, 5, 6), ("Ñ", 27, 5, 5),
    
    # Linha 6 (Colunas 0..13: Ligaduras e Ícones de UI; Colunas 14..27: Símbolos Nativos)
    ("⇒", 0, 6, 8), ("⇐", 1, 6, 8), ("⇔", 2, 6, 8), ("≤", 3, 6, 6), ("≥", 4, 6, 6),
    ("≠", 5, 6, 6), ("≡", 6, 6, 6), ("≈", 7, 6, 6), ("…", 8, 6, 6), ("—", 9, 6, 8),
    ("±", 10, 6, 6), ("×", 11, 6, 6), ("★", 12, 6, 8), ("♥", 13, 6, 8),
    ("♪", 14, 6, 7), ("♫", 15, 6, 7), ("«", 16, 6, 9), ("»", 17, 6, 9), ("▲", 18, 6, 8),
    ("▼", 19, 6, 8), ("►", 20, 6, 7), ("◄", 21, 6, 7), ("↑", 22, 6, 6), ("↓", 23, 6, 6),
    ("→", 24, 6, 11), ("←", 25, 6, 11), ("↕", 26, 6, 6), ("↔", 27, 6, 11),
]

NEIGHBORS_8 = [(-1, -1), (0, -1), (1, -1), (-1, 0), (1, 0), (-1, 1), (0, 1), (1, 1)]
NEIGHBORS_4 = [(0, -1), (-1, 0), (1, 0), (0, 1)]


def compute_metrics(font: pygame.font.Font, cell_h: int) -> Tuple[int, int]:
    """Calcula o deslocamento vertical (y_shift) e a linha de base óptica (baseline_y)."""
    ref_surf = font.render("Ágjpqy()", False, (255, 255, 255))
    rw, rh = ref_surf.get_size()
    ys = [y for y in range(rh) for x in range(rw) if ref_surf.get_at((x, y))[3] > 0]
    
    if ys:
        min_y, max_y = min(ys), max(ys)
        # Tenta centralizar opticamente respeitando margem de 1px no topo e 3px na base para sombra
        y_shift = min(1 - min_y, (cell_h - 3) - max_y)
    else:
        y_shift = 0

    num_surf = font.render("0", False, (255, 255, 255))
    nw, nh = num_surf.get_size()
    num_ys = [y for y in range(nh) for x in range(nw) if num_surf.get_at((x, y))[3] > 0]
    baseline_y = max(num_ys) if num_ys else (cell_h // 2 + 2)

    return y_shift, baseline_y


def render_fallback_glyph(matrix: List[str], baseline_y: int) -> pygame.Surface:
    """Renderiza uma matriz pixel-art como uma superfície RGBA do pygame."""
    h, w = len(matrix), len(matrix[0])
    surf = pygame.Surface((w, baseline_y + 4), pygame.SRCALPHA)
    start_y = max(0, baseline_y - h + 1)
    for r, row in enumerate(matrix):
        for c, ch in enumerate(row):
            if ch == '#':
                surf.set_at((c, start_y + r), (255, 255, 255, 255))
    return surf


def is_surface_empty(surf: pygame.Surface, threshold: int = 128) -> bool:
    """Verifica se uma superfície renderizada está vazia ou sem píxeis visíveis."""
    w, h = surf.get_size()
    for y in range(h):
        for x in range(w):
            c = surf.get_at((x, y))
            if c[3] > 0 and c[0] >= threshold:
                return False
    return True


def build_cell(
    raw_surf: pygame.Surface,
    y_shift: int,
    cell_w: int,
    cell_h: int,
    style: str = "3color_outline",
    threshold: int = 128,
) -> Tuple[pygame.Surface, int]:
    """Processa uma superfície bruta de caractere e aplica sombreamento/contorno."""
    out_surf = pygame.Surface((cell_w, cell_h), pygame.SRCALPHA)
    rw, rh = raw_surf.get_size()

    pts = [
        (x, y) for y in range(rh) for x in range(rw)
        if raw_surf.get_at((x, y))[3] > 0 and raw_surf.get_at((x, y))[0] >= threshold
    ]
    if not pts:
        return out_surf, DEFAULT_SPACE_WIDTH

    min_x, max_x = min(x for x, _ in pts), max(x for x, _ in pts)
    min_y, max_y = min(y for _, y in pts), max(y for _, y in pts)

    # Ajusta o deslocamento vertical local para não estourar a célula
    local_shift = y_shift
    max_allowed_y = cell_h - 3 if style in ("3color_outline", "2color_shadow") else cell_h - 1
    min_allowed_y = 1 if style == "3color_outline" else 0

    if max_y + local_shift > max_allowed_y:
        local_shift = max_allowed_y - max_y
    if min_y + local_shift < min_allowed_y:
        local_shift = min_allowed_y - min_y

    core = [[False] * cell_w for _ in range(cell_h)]
    shade = [[False] * cell_w for _ in range(cell_h)]

    # Mapeia os pixels do corpo (core)
    for x, y in pts:
        dx = (x - min_x) + (1 if style == "3color_outline" else 0)
        dy = y + local_shift
        if 0 <= dx < cell_w and 0 <= dy < cell_h:
            core[dy][dx] = True

    if style == "3color_outline":
        # Sombra inferior (1px abaixo da base do glifo)
        for y in range(cell_h - 2):
            for x in range(cell_w):
                if core[y][x] and not core[y + 1][x]:
                    shade[y + 1][x] = True

        # Contorno em 8 direções
        for y in range(cell_h):
            for x in range(cell_w):
                if core[y][x] or shade[y][x]:
                    for ox, oy in NEIGHBORS_8:
                        nx, ny = x + ox, y + oy
                        if 0 <= nx < cell_w and 0 <= ny < cell_h and not core[ny][nx] and not shade[ny][nx]:
                            out_surf.set_at((nx, ny), PALETTE_3COLOR_OUTLINE)

        # Preenchimento de sombra e corpo
        for y in range(cell_h):
            for x in range(cell_w):
                if shade[y][x]:
                    out_surf.set_at((x, y), PALETTE_3COLOR_SHADE)
                if core[y][x]:
                    out_surf.set_at((x, y), PALETTE_3COLOR_BODY)

        glyph_w = (max_x - min_x + 1) + 2  # +2 pelo contorno
        advance_w = min(cell_w, glyph_w)

    elif style == "2color_shadow":
        # Sombra inferior e inferior-direita
        for y in range(cell_h - 1):
            for x in range(cell_w - 1):
                if core[y][x]:
                    if not core[y + 1][x]:
                        shade[y + 1][x] = True
                    if not core[y + 1][x + 1]:
                        shade[y + 1][x + 1] = True

        for y in range(cell_h):
            for x in range(cell_w):
                if shade[y][x] and not core[y][x]:
                    out_surf.set_at((x, y), PALETTE_2COLOR_SHADE)
                if core[y][x]:
                    out_surf.set_at((x, y), PALETTE_2COLOR_BODY)

        glyph_w = (max_x - min_x + 1) + 1
        advance_w = min(cell_w, glyph_w)

    else:  # monochrome
        for y in range(cell_h):
            for x in range(cell_w):
                if core[y][x]:
                    out_surf.set_at((x, y), PALETTE_3COLOR_BODY)
        glyph_w = max_x - min_x + 1
        advance_w = min(cell_w, glyph_w + 1)

    return out_surf, max(1, advance_w)


def generate_font_palettes(target_project_dir: str, font_nid: str, style: str) -> dict:
    """Gera o dicionário de paletas compatíveis baseado no fonts.json existente."""
    json_path = os.path.join(target_project_dir, "resources", "fonts", "fonts.json")
    base_palettes = {}

    if os.path.isfile(json_path):
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            # Tenta pegar paletas de uma fonte existente como 'text' ou 'profont'
            ref_font = next((item for item in data if item.get("nid") in ("profont", "text", "convo")), None)
            if ref_font and "palettes" in ref_font:
                base_palettes = copy.deepcopy(ref_font["palettes"])
        except Exception:
            pass

    # Garante paletas padrão caso não tenha encontrado
    if style == "3color_outline":
        base_palettes["new-white"] = [list(PALETTE_3COLOR_BODY), list(PALETTE_3COLOR_OUTLINE), list(PALETTE_3COLOR_SHADE)]
        base_palettes["white"] = [list(PALETTE_3COLOR_BODY), list(PALETTE_3COLOR_SHADE), list(PALETTE_3COLOR_OUTLINE)]
    else:
        base_palettes["white"] = [list(PALETTE_3COLOR_BODY), list(PALETTE_2COLOR_SHADE)]
        base_palettes["black"] = [list(PALETTE_2COLOR_BODY), list(PALETTE_2COLOR_SHADE)]

    return base_palettes


def update_fonts_json(target_project_dir: str, font_nid: str, style: str):
    """Atualiza ou insere a definição da fonte no fonts.json do projeto."""
    fonts_dir = os.path.join(target_project_dir, "resources", "fonts")
    json_path = os.path.join(fonts_dir, "fonts.json")

    if not os.path.isdir(fonts_dir):
        print(f"[AVISO] Diretório de fontes não encontrado em: {fonts_dir}")
        return

    data = []
    if os.path.isfile(json_path):
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            print(f"[ERRO] Falha ao ler {json_path}: {e}")
            return

    palettes = generate_font_palettes(target_project_dir, font_nid, style)
    default_color = "new-white" if style == "3color_outline" and "new-white" in palettes else "white"
    base_color = default_color

    new_entry = {
        "nid": font_nid,
        "fallback_ttf": None,
        "fallback_size": 16,
        "default_color": default_color,
        "outline_font": (style == "3color_outline"),
        "headless": True,
        "base_color": base_color,
        "palettes": palettes,
    }

    # Substitui se já existir, senão adiciona
    existing_idx = next((i for i, item in enumerate(data) if item.get("nid") == font_nid), None)
    if existing_idx is not None:
        data[existing_idx] = new_entry
        print(f"[OK] Entrada '{font_nid}' atualizada em {json_path}")
    else:
        data.append(new_entry)
        print(f"[OK] Nova entrada '{font_nid}' inserida em {json_path}")

    try:
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        print(f"[ERRO] Falha ao salvar {json_path}: {e}")


def convert_ttf_to_lt_font(
    ttf_path: str,
    font_nid: Optional[str] = None,
    ttf_size: int = DEFAULT_TTF_SIZE,
    cell_w: int = DEFAULT_CELL_W,
    cell_h: int = DEFAULT_CELL_H,
    cols: int = DEFAULT_COLS,
    rows: int = DEFAULT_ROWS,
    style: str = "3color_outline",
    threshold: int = 128,
    space_width: int = DEFAULT_SPACE_WIDTH,
    space_offset: int = 0,
    output_dir: str = ".",
    project_dir: Optional[str] = None,
) -> Tuple[str, str]:
    """Função principal de conversão de TTF para os ativos PNG e IDX da engine."""
    if not os.path.isfile(ttf_path):
        raise FileNotFoundError(f"Arquivo TTF não encontrado: {ttf_path}")

    if not font_nid:
        base_name = os.path.splitext(os.path.basename(ttf_path))[0]
        font_nid = base_name.lower().replace(" ", "_").replace("-", "_")

    pygame.init()
    try:
        font = pygame.font.Font(ttf_path, ttf_size)
    except Exception as e:
        raise RuntimeError(f"Erro ao carregar fonte TrueType com Pygame: {e}")

    y_shift, baseline_y = compute_metrics(font, cell_h)

    sheet_w = cols * cell_w
    sheet_h = rows * cell_h
    sheet = pygame.Surface((sheet_w, sheet_h), pygame.SRCALPHA)

    idx_lines = [f"width       {cell_w}", f"height      {cell_h}"]
    if space_offset != 0:
        idx_lines.append(f"space_offset {space_offset}")

    drawn_cells: Set[Tuple[int, int]] = set()

    for key, col, row, fallback_w in NATIVE_IDX_LAYOUT:
        if col >= cols or row >= rows:
            continue

        # Tratamento especial de caracteres de controle e espaço
        if key == "space":
            idx_lines.append(f"space   {col}   {row}   {space_width}")
            continue
        elif key in ("﹘", "¶"):
            idx_lines.append(f"{key}   {col}   {row}   {fallback_w}")
            continue

        if (col, row) not in drawn_cells:
            # 1. Tenta renderizar matriz de fallback se for ligadura ou caractere de UI
            raw = None
            if key in FALLBACK_MATRICES:
                raw = render_fallback_glyph(FALLBACK_MATRICES[key], baseline_y)
            else:
                try:
                    rendered = font.render(key, False, (255, 255, 255))
                    if not is_surface_empty(rendered, threshold):
                        raw = rendered
                except Exception:
                    raw = None

            # 2. Se o caractere não foi renderizado ou o TTF não possui, tenta fallback
            if raw is None:
                if key in FALLBACK_MATRICES:
                    raw = render_fallback_glyph(FALLBACK_MATRICES[key], baseline_y)
                else:
                    raw = pygame.Surface((1, 1), pygame.SRCALPHA)

            cell_surf, kern_w = build_cell(raw, y_shift, cell_w, cell_h, style, threshold)
            sheet.blit(cell_surf, (col * cell_w, row * cell_h))
            drawn_cells.add((col, row))
        else:
            kern_w = fallback_w

        idx_lines.append(f"{key}   {col}   {row}   {kern_w}")

    # Diretório de destino
    os.makedirs(output_dir, exist_ok=True)
    png_path = os.path.join(output_dir, f"{font_nid}.png")
    idx_path = os.path.join(output_dir, f"{font_nid}.idx")

    pygame.image.save(sheet, png_path)
    with open(idx_path, "w", encoding="utf-8") as f:
        f.write("\n".join(idx_lines) + "\n")

    print(f"[OK] Fonte gerada com sucesso:")
    print(f"     - Imagem: {png_path} ({sheet_w}x{sheet_h} px)")
    print(f"     - Índice: {idx_path} ({len(idx_lines) - 2} glifos)")

    # Sincronização opcional com projeto
    if project_dir:
        proj_fonts_dir = os.path.join(project_dir, "resources", "fonts")
        if os.path.isdir(proj_fonts_dir):
            proj_png = os.path.join(proj_fonts_dir, f"{font_nid}.png")
            proj_idx = os.path.join(proj_fonts_dir, f"{font_nid}.idx")
            pygame.image.save(sheet, proj_png)
            with open(proj_idx, "w", encoding="utf-8") as f:
                f.write("\n".join(idx_lines) + "\n")
            print(f"[OK] Ativos instalados em: {proj_fonts_dir}")
            update_fonts_json(project_dir, font_nid, style)

    return png_path, idx_path


def run_interactive():
    """Modo interativo amigável via terminal."""
    print("=" * 60)
    print("   CONVERSOR TTF PARA LEX TALIONIS ENGINE (ttf to lt font)   ")
    print("=" * 60)

    # Procura arquivos .ttf na pasta atual
    current_files = [f for f in os.listdir(".") if f.lower().endswith((".ttf", ".otf"))]
    default_ttf = current_files[0] if current_files else ""

    prompt_ttf = f"Caminho do arquivo TTF/OTF [{default_ttf}]: " if default_ttf else "Caminho do arquivo TTF/OTF: "
    ttf_input = input(prompt_ttf).strip()
    ttf_path = ttf_input if ttf_input else default_ttf

    if not ttf_path or not os.path.isfile(ttf_path):
        print(f"[ERRO] Arquivo não encontrado: '{ttf_path}'")
        return

    default_nid = os.path.splitext(os.path.basename(ttf_path))[0].lower().replace(" ", "_").replace("-", "_")
    nid_input = input(f"NID da fonte na engine [{default_nid}]: ").strip()
    font_nid = nid_input if nid_input else default_nid

    size_input = input("Tamanho de renderização TTF [10]: ").strip()
    ttf_size = int(size_input) if size_input.isdigit() else 10

    print("\nEscolha o estilo visual:")
    print("  1) 3-Color com Contorno (Padrão UI GBA: Corpo branco, Contorno preto, Sombra cinza)")
    print("  2) 2-Color com Sombra (Padrão Diálogo)")
    print("  3) Monocromático (Apenas corpo sólido)")
    style_choice = input("Opção [1]: ").strip()
    style_map = {"1": "3color_outline", "2": "2color_shadow", "3": "monochrome"}
    style = style_map.get(style_choice, "3color_outline")

    proj_input = input("\nCaminho de um projeto .ltproj para sincronizar (Enter para pular): ").strip()
    project_dir = proj_input if proj_input else None

    print("\nIniciando conversão...")
    convert_ttf_to_lt_font(
        ttf_path=ttf_path,
        font_nid=font_nid,
        ttf_size=ttf_size,
        style=style,
        output_dir=".",
        project_dir=project_dir,
    )
    print("\n[SUCESSO] Processo finalizado!")


def main():
    parser = argparse.ArgumentParser(
        description="Converte arquivos de fonte .ttf/.otf para o formato bitmap (.png/.idx) da engine Lex Talionis."
    )
    parser.add_argument("ttf_path", nargs="?", help="Caminho do arquivo .ttf ou .otf")
    parser.add_argument("--nid", "-n", help="NID da fonte (padrão: nome do arquivo em minúsculas)")
    parser.add_argument("--size", "-s", type=int, default=DEFAULT_TTF_SIZE, help="Tamanho da fonte TTF (padrão: 10)")
    parser.add_argument("--width", "-W", type=int, default=DEFAULT_CELL_W, help="Largura da célula em px (padrão: 10)")
    parser.add_argument("--height", "-H", type=int, default=DEFAULT_CELL_H, help="Altura da célula em px (padrão: 16)")
    parser.add_argument("--cols", type=int, default=DEFAULT_COLS, help="Colunas na grade (padrão: 28)")
    parser.add_argument("--rows", type=int, default=DEFAULT_ROWS, help="Linhas na grade (padrão: 7)")
    parser.add_argument(
        "--style",
        choices=["3color_outline", "2color_shadow", "monochrome"],
        default="3color_outline",
        help="Estilo visual da fonte (padrão: 3color_outline)",
    )
    parser.add_argument("--threshold", type=int, default=128, help="Limiar de luminância para binarização (0-255)")
    parser.add_argument("--space-width", type=int, default=DEFAULT_SPACE_WIDTH, help="Largura do espaço em px (padrão: 4)")
    parser.add_argument("--space-offset", type=int, default=0, help="Espaçamento extra entre caracteres (padrão: 0)")
    parser.add_argument("--output-dir", "-o", default=".", help="Diretório de saída (padrão: .)")
    parser.add_argument("--project", "-p", help="Caminho do projeto .ltproj para sincronizar diretamente")
    parser.add_argument("--interactive", "-i", action="store_true", help="Executa o assistente interativo")

    args = parser.parse_args()

    # Se chamado sem argumentos ou com -i, roda interativo
    if args.interactive or not args.ttf_path:
        run_interactive()
    else:
        convert_ttf_to_lt_font(
            ttf_path=args.ttf_path,
            font_nid=args.nid,
            ttf_size=args.size,
            cell_w=args.width,
            cell_h=args.height,
            cols=args.cols,
            rows=args.rows,
            style=args.style,
            threshold=args.threshold,
            space_width=args.space_width,
            space_offset=args.space_offset,
            output_dir=args.output_dir,
            project_dir=args.project,
        )


if __name__ == "__main__":
    main()
