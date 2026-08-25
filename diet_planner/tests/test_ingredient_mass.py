"""Estimating a recipe's total ingredient mass from mixed Czech units."""
from django.test import SimpleTestCase

from diet_planner.services.ingredient_mass import estimate_mass_g


class EstimateMassTest(SimpleTestCase):
    def test_sums_direct_weight_and_volume_units(self):
        result = estimate_mass_g([
            {'name': 'brambory', 'quantity': 500, 'unit': 'g'},
            {'name': 'mléko', 'quantity': 2, 'unit': 'dl'},
            {'name': 'voda', 'quantity': 1, 'unit': 'l'},
        ])

        self.assertEqual(result.grams, 1700.0)
        self.assertEqual(result.known_lines, 3)
        self.assertEqual(result.coverage, 1.0)

    def test_converts_count_units_via_piece_weights(self):
        result = estimate_mass_g(
            [{'name': 'vejce', 'quantity': 3, 'unit': 'ks', 'canonical': 'eggs'}],
            piece_weights={'eggs': 60.0},
        )

        self.assertEqual(result.grams, 180.0)

    def test_count_unit_without_a_known_piece_weight_is_unknown(self):
        result = estimate_mass_g(
            [{'name': 'záhadný plod', 'quantity': 2, 'unit': 'ks', 'canonical': 'mystery'}],
            piece_weights={},
        )

        self.assertEqual(result.grams, 0.0)
        self.assertEqual(result.unknown_lines, 1)
        self.assertEqual(result.coverage, 0.0)

    def test_spoon_units_count_including_inflected_czech_forms(self):
        result = estimate_mass_g([
            {'name': 'olej', 'quantity': 2, 'unit': 'lžíce'},
            {'name': 'sůl', 'quantity': 1, 'unit': 'lžička'},
            {'name': 'česnek', 'quantity': 3, 'unit': 'stroužky'},
        ])

        self.assertEqual(result.grams, 50.0)
        self.assertEqual(result.known_lines, 3)

    def test_tolerates_czech_decimal_commas_and_junk_rows(self):
        result = estimate_mass_g([
            {'name': 'smetana', 'quantity': '1,5', 'unit': 'dl'},
            'a plain string ingredient',
            {'name': 'sůl', 'quantity': 'dle chuti', 'unit': ''},
            None,
        ])

        self.assertEqual(result.grams, 150.0)
        self.assertEqual(result.known_lines, 1)
        self.assertEqual(result.unknown_lines, 3)

    def test_empty_input_reports_zero_coverage_without_dividing_by_zero(self):
        result = estimate_mass_g([])

        self.assertEqual(result.grams, 0.0)
        self.assertEqual(result.coverage, 0.0)
