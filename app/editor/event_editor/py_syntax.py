from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from PyQt5 import QtCore, QtGui
from app import dark_theme
from app.editor.event_editor.event_highlighter import brace_spans
from app.events.event_prefab import get_event_version
from app.events.python_eventing.compiler import VERSION_MAP

# from https://wiki.python.org/moin/PyQt/Python%20syntax%20highlighting
# with some modification

def format(color: QtGui.QColor, style: str=''):
    """Return a QTextCharFormat with the given attributes.
    """
    _format = QtGui.QTextCharFormat()
    _format.setForeground(color)
    if 'bold' in style:
        _format.setFontWeight(QtGui.QFont.Bold)
    if 'italic' in style:
        _format.setFontItalic(True)
    return _format

# A block's state says which triple quote is still open at its end
NORMAL_STATE = 0
STATE_OF_TRIPLE_QUOTE = {"'''": 1, '"""': 2}
TRIPLE_QUOTE_OF_STATE = {state: quote for quote, state in STATE_OF_TRIPLE_QUOTE.items()}

# Whatever starts a string or comment. A quote with no partner on its line matches nothing
STRING_OR_COMMENT = re.compile('|'.join([
    r"'''",
    r'"""',
    r'"[^"\\]*(?:\\.[^"\\]*)*"',
    r"'[^'\\]*(?:\\.[^'\\]*)*'",
    r'#.*',
]))

OUTSIDE_BMP = re.compile('[\U00010000-\U0010ffff]')

@dataclass
class ScannedLine:
    """Where the strings and comments of a line are, each as (start, length)"""
    strings: list[tuple[int, int]] = field(default_factory=list)
    triple_quoted: list[tuple[int, int]] = field(default_factory=list)
    comments: list[tuple[int, int]] = field(default_factory=list)
    end_state: int = NORMAL_STATE

def scan_line(text: str, previous_state: int) -> ScannedLine:
    """Finds a line's strings and comments from left to right, each one searched
    for from the end of the last, so quotes and #s inside them start nothing"""
    line = ScannedLine()
    start = pos = 0
    open_quote = TRIPLE_QUOTE_OF_STATE.get(previous_state)
    while True:
        if open_quote:
            end = text.find(open_quote, pos)
            if end < 0:
                line.triple_quoted.append((start, len(text) - start))
                line.end_state = STATE_OF_TRIPLE_QUOTE[open_quote]
                return line
            pos = end + len(open_quote)
            line.triple_quoted.append((start, pos - start))
            open_quote = None

        match = STRING_OR_COMMENT.search(text, pos)
        if not match:
            return line
        start, pos = match.span()
        token = match.group()
        if token in STATE_OF_TRIPLE_QUOTE:
            open_quote = token
        elif token.startswith('#'):
            line.comments.append((start, pos - start))
        else:
            line.strings.append((start, pos - start))

class PythonHighlighter(QtGui.QSyntaxHighlighter):
    """Syntax highlighter for the Python language.
    """
    # keywords
    keywords = ['and', 'def', 'class', 'is', 'lambda', 'not', 'or',
                'None', 'True', 'False', 'self']
    # alt keywords
    alt_keywords = ['assert', 'break', 'continue', 'del',
                    'if', 'elif', 'else', 'except', 'raise',
                    'return', 'try', 'while', 'yield', 'finally',
                    'for', 'from', 'global', 'import', 'pass', 'in']

    # Python braces
    braces = [
        r'\{', r'\}', r'\(', r'\)', r'\[', r'\]',
    ]

    def __init__(self, parent: QtGui.QTextDocument) -> None:
        super().__init__(parent)
        theme = dark_theme.get_theme()
        style = theme.python_syntax_highlighting()
        self.style = style
        self.event_style = theme.event_syntax_highlighting()
        self.string_format = format(style.string)
        self.triple_quoted_format = format(style.string2)
        self.comment_format = format(style.comment)

        rules = []

        # Keyword, operator, and brace rules
        rules += [(r'\b%s\b' % w, 0, format(style.keyword))
            for w in PythonHighlighter.keywords]
        rules += [(r'\b%s\b' % w, 0, format(style.alt_keyword))
            for w in PythonHighlighter.alt_keywords]
        rules += [(r'%s' % b, 0, format(style.brace))
            for b in PythonHighlighter.braces]

        # All other rules
        rules += [
            # 'def' followed by an identifier
            (r'\bdef\b\s*(\w+)', 1, format(style.deffunc)),
            # 'class' followed by an identifier
            (r'\bclass\b\s*(\w+)', 1, format(style.defclass)),

            # Numeric literals
            (r'\b[+-]?[0-9]+[lL]?\b', 0, format(style.numbers)),
            (r'\b[+-]?0[xX][0-9A-Fa-f]+[lL]?\b', 0, format(style.numbers)),
            (r'\b[+-]?[0-9]+(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?\b', 0, format(style.numbers)),
        ]

        # Build a QRegExp for each pattern.
        self.rules = [(QtCore.QRegExp(pat), index, fmt)
            for (pat, index, fmt) in rules]

    def applyRule(self, text, expression, nth, format):
        index = expression.indexIn(text, 0)
        while index >= 0:
            # We actually want the index of the nth match
            index = expression.pos(nth)
            length = len(expression.cap(nth))
            self.setFormat(index, length, format)
            index = expression.indexIn(text, index + length)

    def highlightPyEvent(self, text: str):
        version = get_event_version(self.document().toPlainText())
        compiler = VERSION_MAP.get(version)
        if not compiler:
            return None
        as_tokens = compiler.parse_line(text)
        if not as_tokens:
            return None
        tokens, idxs = as_tokens.tokens, as_tokens.token_idx
        command = as_tokens.command()
        # TODO(mag): make this highlighting *completely* event-contextual, with colors
        # based on field?
        for i in range(len(as_tokens.tokens)):
            tok = tokens[i]
            idx = idxs[i]
            if tok in as_tokens.flags():
                self.setFormat(idx, len(tok), format(self.style.flag, 'italic'))
            elif tok == as_tokens.command():
                self.setFormat(as_tokens.start_idx, len(tok) + idx - as_tokens.start_idx, format(self.style.command, 'bold'))

            # special formatting for speak
            if command == 'speak':
                if i == 2:
                    self.format_dialog(idx, tok)
            # special formatting for say, same as speak
            elif command == 'say':
                arg = tok.strip()
                if i > 1 and arg:
                    quote = arg[0]
                    if quote in ('"', "'") and arg.endswith(quote):
                        self.format_dialog(idx, tok)

    def format_dialog(self, idx: int, text: str):
        """Dialog text, with its dialog commands ({w}, {eval:...}) and line breaks (|)
        picked out the same way as in a regular event"""
        self.setFormat(idx, len(text), format(self.event_style.text_color))
        special_format = format(self.event_style.special_text_color)
        for start, length in brace_spans(text):
            self.setFormat(idx + start, length, special_format)
        for char_idx, char in enumerate(text):
            if char == '|':
                self.setFormat(idx + char_idx, 1, special_format)

    def highlightBlock(self, text):
        """Apply syntax highlighting to the given block of text.
        """
        # See EventHighlighter.highlightBlock -- an exception escaping a
        # reimplemented Qt virtual aborts the whole editor.
        try:
            self._highlight_block(text)
        except Exception:
            logging.exception("Failed to syntax highlight line %s", text)

    def _highlight_block(self, text):
        for expression, nth, rule_format in self.rules:
            self.applyRule(text, expression, nth, rule_format)

        # Qt's positions count a character outside the BMP as two
        line = scan_line(OUTSIDE_BMP.sub('__', text), self.previousBlockState())
        for start, length in line.strings:
            self.setFormat(start, length, self.string_format)

        self.highlightPyEvent(text)

        # Comments and triple quoted strings take precedence over custom lt highlighting
        for start, length in line.comments:
            self.setFormat(start, length, self.comment_format)
        for start, length in line.triple_quoted:
            self.setFormat(start, length, self.triple_quoted_format)
        self.setCurrentBlockState(line.end_state)