# Conversor de Fontes TTF para Lex Talionis Engine (`ttf to lt font`)

Ferramenta personalizada para converter qualquer arquivo de fonte TrueType (`.ttf`) ou OpenType (`.otf`) no formato nativo de fonte bitmap (`.png` e `.idx`) utilizado pela engine **Lex Talionis**, com suporte completo a paletas de cores, acentuação em português/espanhol e ligaduras especiais de combate e interface.

---

## 📁 Arquivos da Ferramenta

- **`ttf_to_lt_font.py`**: Script principal em Python com interface CLI e modo interativo.
- **`ttf_to_lt_font.bat`**: Atalho executável para Windows (suporta duplo-clique, arrastar e soltar um `.ttf` sobre ele ou execução direta pelo terminal).
- **`README_FONT_CONVERTER.md`**: Esta documentação.

---

## 🚀 Como Usar

### Modo 1: Execução Interativa (Mais Fácil)
Basta dar **duplo-clique** em `ttf_to_lt_font.bat` ou executar no terminal sem parâmetros:
```bash
python "custom tools/ttf_to_lt_font.py"
```
O assistente detectará automaticamente fontes `.ttf` na pasta e guiará você com perguntas simples sobre o nome da fonte (NID), tamanho e estilo visual.

### Modo 2: Linha de Comando (CLI)
Para converter rapidamente com opções personalizadas:
```bash
python "custom tools/ttf_to_lt_font.py" "custom tools/ProFontIIxNerdFontMono-Regular.ttf" --nid profont --size 10 --style 3color_outline
```

### Modo 3: Instalação Direta no Projeto
Você pode converter e instalar a fonte diretamente em um projeto Lex Talionis usando a opção `--project` (ou `-p`):
```bash
python "custom tools/ttf_to_lt_font.py" "custom tools/ProFontIIxNerdFontMono-Regular.ttf" --nid profont --project default.ltproj
```
Isso fará:
1. Geração do sprite sheet `.png` em `default.ltproj/resources/fonts/<nid>.png`.
2. Geração do arquivo de coordenadas `.idx` em `default.ltproj/resources/fonts/<nid>.idx`.
3. Registro ou atualização da fonte em `default.ltproj/resources/fonts/fonts.json` com todas as paletas de cores do jogo (`white`, `blue`, `green`, `red`, `orange`, `grey`, `yellow`, `brown`, `purple`, `navy`, etc.).

---

## ⚙️ Opções de Linha de Comando

| Argumento | Padrão | Descrição |
| :--- | :---: | :--- |
| `ttf_path` | - | Caminho para o arquivo `.ttf` ou `.otf`. |
| `--nid`, `-n` | *Nome do arquivo* | Identificador único (NID) da fonte na engine (ex: `profont`, `m5x7`). |
| `--size`, `-s` | `10` | Tamanho do texto para renderização TrueType (ex: `10`, `12`, `14`). |
| `--width`, `-W` | `10` | Largura da célula na grade em pixels (padrão de interface: `10`). |
| `--height`, `-H` | `16` | Altura da célula na grade em pixels (padrão de interface: `16`). |
| `--cols` | `28` | Quantidade de colunas na grade do sprite sheet (padrão: `28`). |
| `--rows` | `7` | Quantidade de linhas na grade do sprite sheet (padrão: `7`). |
| `--style` | `3color_outline` | Estilo gráfico: `3color_outline` (UI GBA), `2color_shadow` (Diálogo) ou `monochrome`. |
| `--threshold` | `128` | Limiar de luminância para binarização de píxeis (0 a 255). |
| `--space-width` | `4` | Largura de avanço em pixels do caractere de espaço. |
| `--space-offset`| `0` | Espaçamento extra (kerning global) entre caracteres. |
| `--output-dir`, `-o` | `.` | Diretório onde os arquivos `.png` e `.idx` serão gerados. |
| `--project`, `-p` | `None` | Caminho da pasta `.ltproj` para registrar no `fonts.json` e instalar nos recursos. |
| `--interactive`, `-i` | `False` | Força a inicialização do assistente interativo no terminal. |

---

## 🎨 Como Funciona a Compatibilidade de Cores (Paletas)

Na engine Lex Talionis, o texto não é renderizado em RGBA anti-aliased arbitrário; ele utiliza um **sistema de substituição de paleta por píxel** (`image_mods.color_convert_alpha`):
- **Perfil 3-Color com Contorno (`3color_outline`)**:
  - **Corpo do Glifo (`#f8f8f8`)**: Píxeis centrais do caractere.
  - **Sombra (`#545454`)**: Píxeis imediatamente abaixo do corpo para dar profundidade.
  - **Contorno (`#000000`)**: Contorno de 1px em 8 direções ao redor do glifo e da sombra.
  - **Transparência (`#00000000`)**: Fundo sem cor.
- Essa estrutura garante que, ao usar `<green>texto</green>` ou `<red>alerta</red>` nos diálogos e menus, a engine substitui exatamente os 3 tons correspondentes para cada variante de cor sem deixar bordas cinzas ou artefatos visuais.

---

## 🔤 Tabela de Caracteres e Ligaduras Suportadas

O gerador cria uma grade completa de **28 colunas × 7 linhas** (196 células / 197 mapeamentos):

- **Linhas 0 e 1**: Alfabeto latino completo minúsculo (`a-z`) e maiúsculo (`A-Z`), mais `@`, `•`, etc.
- **Linha 2**: Dígitos numéricos (`0-9`), moedas (`$`), operadores (`+`, `-`, `=`, `%`, `~`, `*`, `#`) e símbolos nórdicos/antigos (`ŋ`, `þ`, `ø`, `ß`, `ƿ`, `æ`, `œ`).
- **Linha 3**: Pontuação e delimitadores (`(`, `)`, `[`, `]`, `{`, `}`, `<`, `>`, `/`, `\`, `.`, `,`, `:`, `;`, `'`, `"`, `_`, `&`, `¿`, `¡`, `º`, `°`).
- **Linhas 4 e 5**: Acentuação completa em português e espanhol (`á`, `à`, `ã`, `â`, `é`, `ê`, `í`, `ó`, `õ`, `ô`, `ú`, `ç`, `ñ` e maiúsculas).
- **Linha 6 (Ligaduras e Ícones de UI)**:
  - **Colunas 0 a 13 (Novas Ligaduras)**:
    - Setas duplas e lógicas: `⇒` (`=>`), `⇐` (`<==`), `⇔` (`<=>`)
    - Comparadores matemáticos: `≤` (`<=`), `≥` (`>=`), `≠` (`!=`), `≡` (`==`), `≈` (`~=`)
    - Sinais e pontuação especial: `…` (`...`), `—` (`--`), `±` (`+-`), `×` (`**`)
    - Ícones gráficos: `★` (`[*]`), `♥` (`<3`)
  - **Colunas 14 a 27 (Símbolos Nativos da Engine)**:
    - Notas musicais: `♪` (`[m1]`), `♫` (`[m2]`)
    - Aspas angulares: `«` (`<<`), `»` (`>>`)
    - Triângulos e setas direcionais: `▲` (`[A]`), `▼` (`[V]`), `►` (`[>]`), `◄` (`[<]`), `↑` (`[^]`), `↓` (`[v]`), `→` (`->`), `←` (`<-`), `↕` (`[^v]`), `↔` (`<->`)

> [!NOTE]
> Se o arquivo TTF de entrada não possuir desenho para essas ligaduras ou setas, o script injeta automaticamente **matrizes pixel-art pré-calibradas**, garantindo que nenhum símbolo fique faltando ou gere caixas pretas na engine.

---

## 🎮 Atribuindo a Nova Fonte no Editor

Depois de gerar e instalar a fonte em seu projeto:
1. Abra o editor de Lex Talionis (`python main.py` ou seu executável).
2. Acesse a aba **Fonts** (Editor de Fontes).
3. Na primeira aba (**Font Catalog**), verifique sua nova fonte listada (com pré-visualização de ícone).
4. Na segunda aba (**UI Assignments**), você pode definir qual sistema do jogo usará sua nova fonte:
   - *Core & Fallbacks*: Fonte padrão de UI, textos compactos, números de dano.
   - *Narrative & Dialogue*: Diálogos normais, pensamentos em itálico ou falas enfatizadas.
   - *Menus & Navigation*: Menus de ação (Attack, Item, Wait), menus de preparação, slots de save.
   - *Unit Status & Stats*: Ficha de unidade, ranks de arma, caixas de ajuda/tooltips.
   - *Combat Experience*: HUD de combate, barras de HP, multiplicadores (x2, x3).
   - *Progression & Alerts*: Tela de Level Up, avisos de banner, promoção de classe.
   - *Records & Post-Game*: Hall da fama, vitórias de capítulo e créditos.
5. As alterações são salvas automaticamente no arquivo `font_assignments.json` do seu projeto.
