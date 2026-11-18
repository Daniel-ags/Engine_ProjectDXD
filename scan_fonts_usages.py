import os
import re
from collections import defaultdict

ENGINE_DIR = os.path.join("app", "engine")

# Padrões de uso de fontes e renderização de texto na engine
PATTERNS = [
    ("FONT_DICT", re.compile(r"FONT(?:\.get)?\(\s*['\"]([^'\"]+)['\"]\s*\)|FONT\[\s*['\"]([^'\"]+)['\"]\s*\]")),
    ("RENDER_TEXT", re.compile(r"render_text\s*\([^)]*\)")),
    ("TEXT_WIDTH", re.compile(r"text_width\s*\(\s*['\"]([^'\"]+)['\"]")),
    ("FONT_TYPE_ATTR", re.compile(r"font_type\s*=\s*['\"]([^'\"]+)['\"]")),
]

# Sugestão automática de alias semântico por arquivo/pasta
FILE_TO_ROLE = {
    "promotion.py": "ui_promo",
    "info_menu": "ui_info",
    "menus.py": "ui_choice",
    "banner.py": "ui_banner",
    "combat": "ui_combat",
    "battle": "ui_combat",
    "dialog.py": "convo",
}


def suggest_role(rel_path: str) -> str:
    for key, role in FILE_TO_ROLE.items():
        if key in rel_path.replace("\\", "/"):
            return role
    return "text"


def scan_engine():
    summary = defaultdict(list)
    total_hits = 0

    for root, _, files in os.walk(ENGINE_DIR):
        for fname in sorted(files):
            if not fname.endswith(".py"):
                continue
            fpath = os.path.join(root, fname)
            rel_path = os.path.relpath(fpath, ENGINE_DIR)

            with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()

            for line_no, line in enumerate(lines, start=1):
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                for pat_name, regex in PATTERNS:
                    if regex.search(stripped):
                        summary[rel_path].append((line_no, pat_name, stripped))
                        total_hits += 1
                        break

    out_report = "font_usage_report.txt"
    with open(out_report, "w", encoding="utf-8") as out:
        out.write(f"=== RELATÓRIO DE USO DE FONTES NA ENGINE ({total_hits} ocorrências em {len(summary)} arquivos) ===\n\n")
        for rel_path, hits in sorted(summary.items()):
            role = suggest_role(rel_path)
            out.write(f"📄 {rel_path}  [Role sugerido: '{role}'] ({len(hits)} ocorrências)\n")
            for line_no, pat_name, code in hits:
                out.write(f"   L{line_no:04d} [{pat_name}]: {code}\n")
            out.write("\n")

    print(f"[OK] Varredura concluída! {total_hits} ocorrências encontradas em {len(summary)} arquivos.")
    print(f"[OK] Relatório salvo em: {out_report}")


if __name__ == "__main__":
    scan_engine()