import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.tests import qt_headless  # noqa: F401 -- before any QApplication


class HighlightBlockNeverRaisesTests(unittest.TestCase):
    '''
    highlightBlock() is a reimplemented Qt virtual. PyQt aborts the whole
    process (SIGABRT -- no dialog, no chance to save the event) when an
    exception escapes one, so a bad line must degrade to unhighlighted text
    rather than take the editor down with it.
    '''

    def setUp(self) -> None:
        import sys
        from PyQt5.QtWidgets import QApplication
        self.app = QApplication.instance() or QApplication(sys.argv)

        from app.editor.event_editor.event_highlighter import EventSyntaxRuleHighlighter, EventHighlighter
        self.EventSyntaxRuleHighlighter = EventSyntaxRuleHighlighter
        self.EventHighlighter = EventHighlighter

    def _build(self):
        from PyQt5.QtWidgets import QPlainTextEdit
        self.edit = QPlainTextEdit()
        # Validation looks up the level the window is editing; no event is open
        return self.EventHighlighter(self.edit.document(), SimpleNamespace(current=None))

    def test_exception_in_match_line_does_not_escape(self):
        highlighter = self._build()
        with patch.object(self.EventSyntaxRuleHighlighter, 'match_line',
                          side_effect=ValueError('boom')), \
                self.assertLogs(level='ERROR') as logs:
            highlighter.highlightBlock('speak;Eirika;Hello, world')
        self.assertIn('Failed to syntax highlight line', logs.output[0])

    def test_normal_line_still_formats(self):
        highlighter = self._build()
        formatted = []
        with patch.object(self.EventHighlighter, 'setFormat',
                          side_effect=lambda *args: formatted.append(args)), \
                self.assertNoLogs(level='ERROR'):
            highlighter.highlightBlock('speak;Eirika;Hello, world')
        self.assertTrue(formatted)



class HighlightColorsTestCase(unittest.TestCase):
    def setUp(self) -> None:
        import sys
        from PyQt5.QtWidgets import QApplication
        self.app = QApplication.instance() or QApplication(sys.argv)

    def colors(self, highlighter_type, script, line_no):
        """Map each character of the given line to its highlighted foreground color"""
        from PyQt5.QtWidgets import QPlainTextEdit
        self.edit = QPlainTextEdit()
        self.edit.setPlainText(script)
        self.highlighter = highlighter_type(self.edit.document())
        self.highlighter.rehighlight()
        block = self.edit.document().findBlockByNumber(line_no)
        colors = {}
        for fmt_range in block.layout().formats():
            for i in range(fmt_range.start, fmt_range.start + fmt_range.length):
                colors[i] = fmt_range.format.foreground().color()
        return block.text(), colors


class PythonStringHighlightTests(HighlightColorsTestCase):
    '''
    Strings and comments are found left to right, so a quote or # inside one
    of them starts nothing
    '''

    def setUp(self) -> None:
        super().setUp()
        from app import dark_theme
        style = dark_theme.get_theme().python_syntax_highlighting()
        self.string_color = style.string
        self.triple_color = style.string2
        self.comment_color = style.comment
        self.brace_color = style.brace

    def assert_spans(self, script, spans, line_no=0):
        """Each (text, color) names the first place text appears on the line
        and the color all of it has; a color of None means no color of its own"""
        from app.editor.event_editor.py_syntax import PythonHighlighter
        line, colors = self.colors(PythonHighlighter, script, line_no)
        for text, color in spans:
            start = line.index(text)
            for i in range(start, start + len(text)):
                self.assertEqual(color, colors.get(i), (line, text, line[i]))

    def test_apostrophe_in_double_quoted_string(self):
        self.assert_spans('''check_default("O'Neill",['Eirika'])''', [
            ('''"O'Neill"''', self.string_color),
            (',', None),
            ('[', self.brace_color),
            ("'Eirika'", self.string_color),
            ('])', self.brace_color),
        ])

    def test_double_quote_in_single_quoted_string(self):
        self.assert_spans("""f('a"b', x, 'c"d')""", [
            ("""'a"b'""", self.string_color),
            (', x, ', None),
            ("""'c"d'""", self.string_color),
        ])

    def test_hash_in_string_is_not_a_comment(self):
        self.assert_spans('''x = "a # b" + 'c' # d''', [
            ('"a # b"', self.string_color),
            (' + ', None),
            ("'c'", self.string_color),
            ('# d', self.comment_color),
        ])

    def test_quotes_in_comment_are_not_strings(self):
        self.assert_spans('''# don't "stop''', [('''# don't "stop''', self.comment_color)])

    def test_escaped_quote_stays_in_string(self):
        self.assert_spans(r'''x = 'it\'s' + y''', [
            (r"""'it\'s'""", self.string_color),
            (' + y', None),
        ])

    def test_unterminated_quote_colors_nothing(self):
        self.assert_spans("x = don't + y", [("don't + y", None)])

    def test_triple_quotes_in_string_start_nothing(self):
        script = """x = "'''"\ny = 1 + z"""
        self.assert_spans(script, [('''"\'\'\'"''', self.string_color)])
        self.assert_spans(script, [('y', None), (' + z', None)], line_no=1)

    def test_triple_quotes_in_comment_start_nothing(self):
        script = "# '''\ny"
        self.assert_spans(script, [('y', None)], line_no=1)

    def test_triple_quoted_string_spans_lines(self):
        script = """x = '''don't\n# "not" a comment\nend''' + "it's" # done\ny"""
        self.assert_spans(script, [("'''don't", self.triple_color)])
        self.assert_spans(script, [('# "not" a comment', self.triple_color)], line_no=1)
        self.assert_spans(script, [
            ("end'''", self.triple_color),
            (' + ', None),
            ('''"it's"''', self.string_color),
            ('# done', self.comment_color),
        ], line_no=2)
        self.assert_spans(script, [('y', None)], line_no=3)

    def test_emoji_counts_as_two_positions(self):
        from app.editor.event_editor.py_syntax import PythonHighlighter
        _, colors = self.colors(PythonHighlighter, 'x = \U0001F600 + "abc" + y', 0)
        string_positions = [i for i, color in colors.items() if color == self.string_color]
        self.assertEqual(list(range(9, 14)), string_positions)

    def test_other_triple_quote_does_not_close_string(self):
        script = '''"""a\n\'\'\'b\nc"""d'''
        self.assert_spans(script, [("\'\'\'b", self.triple_color)], line_no=1)
        self.assert_spans(script, [('c"""', self.triple_color), ('d', None)], line_no=2)


class DialogCommandHighlightTests(HighlightColorsTestCase):
    '''
    In dialog text, dialog commands like {w} and line breaks (|) stand out in the
    special text color. Python events used to color the whole line of dialog
    the plain text color
    '''

    def setUp(self) -> None:
        super().setUp()
        from app import dark_theme
        style = dark_theme.get_theme().event_syntax_highlighting()
        self.text_color = style.text_color
        self.special_color = style.special_text_color

    def assert_dialog_colors(self, line, colors, dialog):
        start = line.index(dialog)
        for i, char in enumerate(dialog):
            in_command = dialog.index('{') <= i <= dialog.index('}')
            expected = self.special_color if in_command or char == '|' else self.text_color
            self.assertEqual(expected, colors.get(start + i), (dialog, i, char))

    def test_python_event_speak(self):
        from app.editor.event_editor.py_syntax import PythonHighlighter
        line, colors = self.colors(PythonHighlighter, '#pyev1\n$speak Eirika "Hi {w}there|friend"', 1)
        self.assert_dialog_colors(line, colors, '"Hi {w}there|friend"')

    def test_python_event_say(self):
        from app.editor.event_editor.py_syntax import PythonHighlighter
        line, colors = self.colors(PythonHighlighter, '#pyev1\n$say Eirika "Hi {w}there|friend"', 1)
        self.assert_dialog_colors(line, colors, '"Hi {w}there|friend"')

    def test_python_braces_outside_dialog_keep_python_colors(self):
        from app.editor.event_editor.py_syntax import PythonHighlighter
        line, colors = self.colors(PythonHighlighter, '#pyev1\nx = {1: 2}', 1)
        self.assertNotEqual(self.special_color, colors.get(line.index('{')))

    def test_event_speak(self):
        from app.editor.event_editor.event_highlighter import EventHighlighter
        line, colors = self.colors(lambda doc: EventHighlighter(doc, SimpleNamespace(current=None)), 'speak;Eirika;Hi {w}there|friend', 0)
        self.assert_dialog_colors(line, colors, 'Hi {w}there|friend')


class BraceSpansTests(unittest.TestCase):
    def test_spans(self):
        from app.editor.event_editor.event_highlighter import brace_spans
        self.assertEqual([(3, 3)], brace_spans('Hi {w}'))
        # Nested: the outermost group is covered in full
        self.assertEqual([(0, 5), (0, 10), (0, 11)], brace_spans('{a{b}c {d}}'))
        self.assertEqual([], brace_spans('no {close'))
        self.assertEqual([(4, 3)], brace_spans('} x {w}'))

if __name__ == '__main__':
    unittest.main()
