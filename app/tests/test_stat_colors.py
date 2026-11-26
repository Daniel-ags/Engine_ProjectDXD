import unittest
from unittest.mock import MagicMock, patch

from app.data.database.stats import StatPrefab
from app.engine.info_menu.info_menu_state import InfoMenuState


class TestStatColors(unittest.TestCase):
    def setUp(self):
        self.state = InfoMenuState.__new__(InfoMenuState)
        self.state.font_name = 'ui_info'
        self.state.unit = MagicMock()
        self.state.unit.team = 'player'

    def test_growth_colors_boundaries(self):
        """Test that growth rates map to the correct red-to-green gradient palettes."""
        self.assertEqual(self.state.growth_colors(0), 'red-orange')
        self.assertEqual(self.state.growth_colors(20), 'red-orange')
        self.assertEqual(self.state.growth_colors(21), 'light-red')
        self.assertEqual(self.state.growth_colors(30), 'light-red')
        self.assertEqual(self.state.growth_colors(35), 'pink-orange')
        self.assertEqual(self.state.growth_colors(40), 'pink-orange')
        self.assertEqual(self.state.growth_colors(45), 'light-orange')
        self.assertEqual(self.state.growth_colors(50), 'light-orange')
        self.assertEqual(self.state.growth_colors(55), 'corn-yellow')
        self.assertEqual(self.state.growth_colors(60), 'corn-yellow')
        self.assertEqual(self.state.growth_colors(65), 'light-green')
        self.assertEqual(self.state.growth_colors(70), 'light-green')
        self.assertEqual(self.state.growth_colors(75), 'olive-green')
        self.assertEqual(self.state.growth_colors(80), 'olive-green')
        self.assertEqual(self.state.growth_colors(85), 'soft-green')
        self.assertEqual(self.state.growth_colors(90), 'soft-green')
        self.assertEqual(self.state.growth_colors(95), 'yellow-green')
        self.assertEqual(self.state.growth_colors(150), 'yellow-green')

    @patch('app.engine.info_menu.info_menu_state.unit_funcs')
    @patch('app.engine.info_menu.info_menu_state.DB')
    def test_truth_table_all_combinations(self, mock_db, mock_unit_funcs):
        """Test all 4 combinations of growth_colors and colored_stat in both views."""
        # 1. Pure Default (growth_colors=False, colored_stat=False)
        stat_default = StatPrefab(nid='DEF', name='Def', growth_colors=False, colored_stat=False, stat_color='new-white')
        # 2. Vanilla Colored Growths only (growth_colors=True, colored_stat=False)
        stat_growth_only = StatPrefab(nid='SPD', name='Spd', growth_colors=True, colored_stat=False, stat_color='new-white')
        # 3. Colored Stat only (growth_colors=False, colored_stat=True)
        stat_color_only = StatPrefab(nid='STR', name='Str', growth_colors=False, colored_stat=True, stat_color='red')
        # 4. Both Enabled (growth_colors=True, colored_stat=True)
        stat_both = StatPrefab(nid='MAG', name='Mag', growth_colors=True, colored_stat=True, stat_color='blue')

        mock_db.stats.get.side_effect = lambda nid: {
            'DEF': stat_default,
            'SPD': stat_growth_only,
            'STR': stat_color_only,
            'MAG': stat_both
        }.get(nid)

        mock_unit_funcs.growth_rate.side_effect = lambda unit, nid: {
            'SPD': 75,  # olive-green
            'MAG': 45   # light-orange
        }.get(nid, 50)

        # Case 1: Pure Default -> default color in both views
        self.assertEqual(self.state.get_stat_label_color('DEF', growths=False, default_color='new-white'), 'new-white')
        self.assertEqual(self.state.get_stat_label_color('DEF', growths=True, default_color='white'), 'white')

        # Case 2: Vanilla Colored Growths -> growth rate gradient in both views
        self.assertEqual(self.state.get_stat_label_color('SPD', growths=False), 'olive-green')
        self.assertEqual(self.state.get_stat_label_color('SPD', growths=True), 'olive-green')

        # Case 3: Colored Stat only -> custom stat color in both views
        self.assertEqual(self.state.get_stat_label_color('STR', growths=False), 'red')
        self.assertEqual(self.state.get_stat_label_color('STR', growths=True), 'red')

        # Case 4: Both Enabled -> custom stat color in standard view, growth gradient in growths view
        self.assertEqual(self.state.get_stat_label_color('MAG', growths=False), 'blue')
        self.assertEqual(self.state.get_stat_label_color('MAG', growths=True), 'light-orange')

    @patch('app.engine.info_menu.info_menu_state.unit_funcs')
    @patch('app.engine.info_menu.info_menu_state.DB')
    def test_enemy_team_fallback(self, mock_db, mock_unit_funcs):
        """When inspecting an enemy unit, dynamic growth colors are not shown."""
        stat_spd = StatPrefab(nid='SPD', name='Speed', growth_colors=True, colored_stat=False, stat_color='new-white')
        mock_db.stats.get.side_effect = lambda nid: {'SPD': stat_spd}.get(nid)
        mock_unit_funcs.growth_rate.return_value = 75

        self.state.unit.team = 'enemy'
        self.assertEqual(self.state.get_stat_label_color('SPD', growths=False, default_color='new-white'), 'new-white')
        self.assertEqual(self.state.get_stat_label_color('SPD', growths=True, default_color='white'), 'white')

    @patch('app.engine.info_menu.info_menu_state.DB')
    def test_missing_stat_fallback(self, mock_db):
        """When stat_nid is unknown, fallback to default_color."""
        mock_db.stats.get.return_value = None
        self.assertEqual(self.state.get_stat_label_color('UNKNOWN', growths=False, default_color='new-white'), 'new-white')
        self.assertEqual(self.state.get_stat_label_color('UNKNOWN', growths=True, default_color='white'), 'white')


if __name__ == '__main__':
    unittest.main()
