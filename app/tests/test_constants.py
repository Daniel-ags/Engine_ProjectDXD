import unittest

from app.data.database.constants import ConstantType, constants


class ConstantDefaultTests(unittest.TestCase):
    def test_bool_constants_default_to_bool(self):
        """A BOOL constant whose tag is passed in the default's place gets a
        truthy ConstantTag as its default, switching it on in any project that
        never saved it."""
        wrong = [(c.nid, c.value) for c in constants if c.attr == ConstantType.BOOL and not isinstance(c.value, bool)]
        self.assertEqual(wrong, [])


if __name__ == '__main__':
    unittest.main()
