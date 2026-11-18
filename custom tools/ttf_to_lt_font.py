import os
import sys
import json
import copy
import pygame

FONT_NID = "profont"
DEFAULT_TTF_SIZE = 10
CELL_W, CELL_H = 10, 16
COLS, ROWS = 28, 7

# Paleta "new-white" (Corpo, Contorno, Sombra)
COLOR_TRANSPARENT = (0, 0, 0, 0)
COLOR_BODY = (248, 248, 248, 255)
COLOR_OUTLINE = (0, 0, 0, 255)
COLOR_SHADE = (84, 84, 84, 255)

NATIVE_IDX_LAYOUT = [
    ("space", 0, 1, 4), ("﹘", 0, 1, 1), ("¶", 0, 1, 20), ("•", 1, 0, 6), ("@", 1, 1, 10),
    ("a", 2, 0, 6), ("b", 3, 0, 5), ("c", 4, 0, 5), ("d", 5, 0, 6), ("e", 6, 0, 5),
    ("f", 7, 0, 4), ("g", 8, 0, 5), ("h", 9, 0, 5), ("i", 10, 0, 2), ("j", 11, 0, 4),
    ("k", 12, 0, 5), ("l", 13, 0, 2), ("m", 14, 0, 6), ("n", 15, 0, 5), ("o", 16, 0, 5),
    ("p", 17, 0, 5), ("q", 18, 0, 5), ("r", 19, 0, 4), ("s", 20, 0, 5), ("t", 21, 0, 4),
    ("u", 22, 0, 5), ("v", 23, 0, 6), ("w", 24, 0, 6), ("x", 25, 0, 6), ("y", 26, 0, 5), ("z", 27, 0, 5),
    ("A", 2, 1, 5), ("B", 3, 1, 5), ("C", 4, 1, 5), ("D", 5, 1, 5), ("E", 6, 1, 5),
    ("F", 7, 1, 5), ("G", 8, 1, 5), ("H", 9, 1, 5), ("I", 10, 1, 4), ("J", 11, 1, 5),
    ("K", 12, 1, 5), ("L", 13, 1, 4), ("M", 14, 1, 6), ("N", 15, 1, 5), ("O", 16, 1, 5),
    ("P", 17, 1, 5), ("Q", 18, 1, 6), ("R", 19, 1, 5), ("S", 20, 1, 5), ("T", 21, 1, 6),
    ("U", 22, 1, 5), ("V", 23, 1, 6), ("W", 24, 1, 6), ("X", 25, 1, 6), ("Y", 26, 1, 6), ("Z", 27, 1, 5),
    ("$", 0, 2, 8), ("0", 1, 2, 7), ("1", 2, 2, 7), ("2", 3, 2, 7), ("3", 4, 2, 7),
    ("4", 5, 2, 7), ("5", 6, 2, 7), ("6", 7, 2, 7), ("7", 8, 2, 7), ("8", 9, 2, 7),
    ("9", 10, 2, 7), ("-", 11, 2, 6), ("+", 12, 2, 6), ("=", 13, 2, 6), ("%", 14, 2, 6),
    ("~", 15, 2, 7), ("*", 16, 2, 6), ("#", 17, 2, 7), ("?", 18, 2, 7), ("!", 19, 2, 4),
    ("ª", 20, 2, 6), ("ŋ", 21, 2, 5), ("þ", 22, 2, 5), ("ø", 23, 2, 7), ("ß", 24, 2, 7),
    ("ƿ", 25, 2, 5), ("æ", 26, 2, 8), ("œ", 27, 2, 8),
    ("(", 0, 3, 4), (")", 1, 3, 4), ("[", 2, 3, 4), ("]", 3, 3, 4), ("{", 4, 3, 5),
    ("}", 5, 3, 5), ("<", 6, 3, 5), (">", 7, 3, 5), ("/", 8, 3, 5), ("\\", 9, 3, 5),
    (".", 10, 3, 3), (",", 11, 3, 3), (":", 12, 3, 3), (";", 13, 3, 3), ("'", 14, 3, 2),
    ("\"", 15, 3, 4), ("_", 16, 3, 7), ("&", 17, 3, 6), ("¿", 18, 3, 7), ("¡", 19, 3, 4),
    ("º", 20, 3, 5), ("°", 21, 3, 6), ("Þ", 22, 3, 5), ("Ø", 23, 3, 7), ("⁊", 24, 3, 6),
    ("Ƿ", 25, 3, 5), ("Æ", 26, 3, 8), ("Œ", 27, 3, 8),
    ("á", 0, 4, 6), ("à", 1, 4, 6), ("ã", 2, 4, 6), ("â", 3, 4, 6), ("å", 4, 4, 6),
    ("ä", 5, 4, 6), ("é", 6, 4, 5), ("è", 7, 4, 5), ("ê", 8, 4, 5), ("ë", 9, 4, 5),
    ("í", 10, 4, 2), ("ì", 11, 4, 3), ("î", 12, 4, 4), ("ï", 13, 4, 4), ("ó", 14, 4, 5),
    ("ò", 15, 4, 5), ("õ", 16, 4, 5), ("ô", 17, 4, 5), ("ö", 18, 4, 5), ("ú", 19, 4, 5),
    ("ù", 20, 4, 5), ("û", 21, 4, 5), ("ü", 22, 4, 5), ("ý", 23, 4, 5), ("ÿ", 24, 4, 5),
    ("ç", 25, 4, 5), ("ð", 26, 4, 6), ("ñ", 27, 4, 5),
    ("Á", 0, 5, 5), ("À", 1, 5, 5), ("Ã", 2, 5, 5), ("Â", 3, 5, 5), ("Ä", 4, 5, 5),
    ("Å", 5, 5, 5), ("É", 6, 5, 5), ("È", 7, 5, 5), ("Ê", 8, 5, 5), ("Ë", 9, 5, 5),
    ("Í", 10, 5, 4), ("Ì", 11, 5, 4), ("Î", 12, 5, 4), ("Ï", 13, 5, 4), ("Ó", 14, 5, 5),
    ("Ò", 15, 5, 5), ("Õ", 16, 5, 5), ("Ô", 17, 5, 5), ("Ö", 18, 5, 5), ("Ú", 19, 5, 5),
    ("Ù", 20, 5, 5), ("Û", 21, 5, 5), ("Ü", 22, 5, 5), ("Ý", 23, 5, 6), ("Ÿ", 24, 5, 6),
    ("Ç", 25, 5, 5), ("Ð", 26, 5, 6), ("Ñ", 27, 5, 5),
    # Linha 6 (Colunas 0..13: Ligaduras e Ícones; Colunas 14..27: Símbolos nativos)
    ("⇒", 0, 6, 8), ("⇐", 1, 6, 8), ("⇔", 2, 6, 8), ("≤", 3, 6, 6), ("≥", 4, 6, 6),
    ("≠", 5, 6, 6), ("≡", 6, 6, 6), ("≈", 7, 6, 6), ("…", 8, 6, 6), ("—", 9, 6, 8),
    ("±", 10, 6, 6), ("×", 11, 6, 6), ("★", 12, 6, 8), ("♥", 13, 6, 8),
    ("♪", 14, 6, 7), ("♫", 15, 6, 7), ("«", 16, 6, 9), ("»", 17, 6, 9), ("▲", 18, 6, 8),
    ("▼", 19, 6, 8), ("►", 20, 6, 7), ("◄", 21, 6, 7), ("↑", 22, 6, 6), ("↓", 23, 6, 6),
    ("→", 24, 6, 11), ("←", 25, 6, 11), ("↕", 26, 6, 6), ("↔", 27, 6, 11),
]

CUSTOM_GLYPHS = {
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

NEIGHBORS = [(-1, -1), (0, -1), (1, -1), (-1, 0), (1, 0), (-1, 1), (0, 1), (1, 1)]


def compute_metrics(font: pygame.font.Font) -> tuple[int, int]:
    ref_surf = font.render("Ágjpqy()", False, (255, 255, 255))
    w, h = ref_surf.get_size()
    ys = [y for y in range(h) for x in range(w) if ref_surf.get_at((x, y))[3] > 0]
    min_y, max_y = (min(ys), max(ys)) if ys else (2, 12)
    y_shift = min(1 - min_y, (CELL_H - 3) - max_y)

    num_surf = font.render("0", False, (255, 255, 255))
    nw, nh = num_surf.get_size()
    num_ys = [y for y in range(nh) for x in range(nw) if num_surf.get_at((x, y))[3] > 0]
    baseline_y = max(num_ys) if num_ys else 9
    return y_shift, baseline_y


def render_custom_glyph(matrix: list[str], baseline_y: int) -> pygame.Surface:
    h, w = len(matrix), len(matrix[0])
    surf = pygame.Surface((w, baseline_y + 4), pygame.SRCALPHA)
    start_y = max(0, baseline_y - h + 1)
    for r, row in enumerate(matrix):
        for c, ch in enumerate(row):
            if ch == '#':
                surf.set_at((c, start_y + r), (255, 255, 255, 255))
    return surf


def build_cell(raw_surf: pygame.Surface, y_shift: int) -> tuple[pygame.Surface, int]:
    out_surf = pygame.Surface((CELL_W, CELL_H), pygame.SRCALPHA)
    rw, rh = raw_surf.get_size()

    pts = [
        (x, y) for y in range(rh) for x in range(rw)
        if raw_surf.get_at((x, y))[3] > 0 and raw_surf.get_at((x, y))[0] > 128
    ]
    if not pts:
        return out_surf, 4

    min_x, max_x = min(x for x, _ in pts), max(x for x, _ in pts)
    min_y, max_y = min(y for _, y in pts), max(y for _, y in pts)

    local_shift = y_shift
    if max_y + local_shift > CELL_H - 3:
        local_shift = (CELL_H - 3) - max_y
    if min_y + local_shift < 1:
        local_shift = 1 - min_y

    core = [[False] * CELL_W for _ in range(CELL_H)]
    shade = [[False] * CELL_W for _ in range(CELL_H)]

    for x, y in pts:
        dx = (x - min_x) + 1
        dy = y + local_shift
        if 0 <= dx < CELL_W - 1 and 1 <= dy <= CELL_H - 3:
            core[dy][dx] = True

    for y in range(CELL_H - 2):
        for x in range(CELL_W):
            if core[y][x] and not core[y + 1][x]:
                shade[y + 1][x] = True

    for y in range(CELL_H):
        for x in range(CELL_W):
            if core[y][x] or shade[y][x]:
                for ox, oy in NEIGHBORS:
                    nx, ny = x + ox, y + oy
                    if 0 <= nx < CELL_W and 0 <= ny < CELL_H and not core[ny][nx] and not shade[ny][nx]:
                        out_surf.set_at((nx, ny), COLOR_OUTLINE)

    for y in range(CELL_H):
        for x in range(CELL_W):
            if shade[y][x]:
                out_surf.set_at((x, y), COLOR_SHADE)
            if core[y][x]:
                out_surf.set_at((x, y), COLOR_BODY)

    advance_w = min(CELL_W, (max_x - min_x + 1) + 1)
    return out_surf, advance_w


def update_fonts_json(out_dir: str):
    json_path = os.path.join(out_dir, "fonts.json")
    if not os.path.isfile(json_path):
        return

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    text_entry = next((item for item in data if item.get("nid") == "text"), None)
    if not text_entry:
        return

    palettes = copy.deepcopy(text_entry.get("palettes", {}))
    palettes["new-white"] = [list(COLOR_BODY), list(COLOR_OUTLINE), list(COLOR_SHADE)]

    new_entry = {
        "nid": FONT_NID,
        "fallback_ttf": None,
        "fallback_size": 16,
        "default_color": "new-white",
        "outline_font": True,
        "headless": True,
        "base_color": "new-white",
        "palettes": palettes,
    }

    idx = next((i for i, item in enumerate(data) if item.get("nid") == FONT_NID), None)
    if idx is not None:
        data[idx] = new_entry
    else:
        data.append(new_entry)

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)
    print(f"[OK] '{FONT_NID}' atualizada em {json_path} (base/default: 'new-white')")


def build_lt_font(ttf_path: str, ttf_size: int = DEFAULT_TTF_SIZE, out_dir: str = "."):
    pygame.init()
    font = pygame.font.Font(ttf_path, ttf_size)
    y_shift, baseline_y = compute_metrics(font)

    sheet = pygame.Surface((COLS * CELL_W, ROWS * CELL_H), pygame.SRCALPHA)
    idx_lines = [f"width       {CELL_W}", f"height      {CELL_H}"]
    drawn_cells = set()

    for key, col, row, fallback_w in NATIVE_IDX_LAYOUT:
        if key in ("space", "﹘", "¶"):
            idx_lines.append(f"{key}   {col}   {row}   {fallback_w}")
            continue

        if (col, row) not in drawn_cells:
            raw = (
                render_custom_glyph(CUSTOM_GLYPHS[key], baseline_y)
                if key in CUSTOM_GLYPHS
                else font.render(key, False, (255, 255, 255))
            )
            cell_surf, kern_w = build_cell(raw, y_shift)
            sheet.blit(cell_surf, (col * CELL_W, row * CELL_H))
            drawn_cells.add((col, row))
        else:
            kern_w = fallback_w

        idx_lines.append(f"{key}   {col}   {row}   {kern_w}")

    os.makedirs(out_dir, exist_ok=True)
    png_path = os.path.join(out_dir, f"{FONT_NID}.png")
    idx_path = os.path.join(out_dir, f"{FONT_NID}.idx")

    pygame.image.save(sheet, png_path)
    with open(idx_path, "w", encoding="utf-8") as f:
        f.write("\n".join(idx_lines) + "\n")

    print(f"[OK] Gerados: {png_path} e {idx_path} ({len(NATIVE_IDX_LAYOUT)} entradas)")
    update_fonts_json(out_dir)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python ttf_to_lt_font.py ProFontIIxNerdFontMono-Regular.ttf [tamanho] [pasta_saida]")
        sys.exit(1)
    size = int(sys.argv[2]) if len(sys.argv) >= 3 else DEFAULT_TTF_SIZE
    out = sys.argv[3] if len(sys.argv) >= 4 else "."
    build_lt_font(sys.argv[1], size, out)