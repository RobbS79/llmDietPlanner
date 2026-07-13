"""Unit tests for the price-book audit classification logic.

Pure functions only (no DB, no YAML) — SimpleTestCase.
"""
from django.test import SimpleTestCase

from diet_planner.management.commands.audit_price_book import (
    band_flag, infer_category, per_display_price, ratio_flags,
)


class PerDisplayPriceTest(SimpleTestCase):
    def test_mass_gram_to_per_kg(self):
        # 0.3499 Kč/g -> 349.9 Kč/kg
        v, u = per_display_price({'unit': 'g', 'price_per_unit': 0.3499})
        self.assertAlmostEqual(v, 349.9, places=3)
        self.assertEqual(u, 'Kč/kg')

    def test_volume_ml_to_per_l(self):
        v, u = per_display_price({'unit': 'ml', 'price_per_unit': 0.0246})
        self.assertAlmostEqual(v, 24.6, places=3)
        self.assertEqual(u, 'Kč/l')

    def test_piece_with_weight_becomes_per_kg(self):
        # 14.34 Kč/ks at 150 g/piece -> 95.6 Kč/kg
        v, u = per_display_price({'unit': 'ks', 'price_per_unit': 14.34},
                                 piece_grams=150)
        self.assertAlmostEqual(v, 95.6, places=1)
        self.assertEqual(u, 'Kč/kg')

    def test_piece_without_weight_stays_per_piece(self):
        v, u = per_display_price({'unit': 'ks', 'price_per_unit': 5.30})
        self.assertAlmostEqual(v, 5.30, places=2)
        self.assertEqual(u, 'Kč/ks')


class InferCategoryTest(SimpleTestCase):
    def test_meat_and_poultry(self):
        self.assertEqual(infer_category('beef'), 'red_meat')
        self.assertEqual(infer_category('chicken-breast'), 'poultry')
        self.assertEqual(infer_category('ham'), 'cured_meat')

    def test_spice_hints(self):
        self.assertEqual(infer_category('black-pepper'), 'spice')
        self.assertEqual(infer_category('vanilla'), 'spice')
        self.assertEqual(infer_category('smoked-paprika'), 'spice')

    def test_override_beats_keyword(self):
        # override wins over keyword/spice-hint heuristics
        self.assertEqual(infer_category('basil'), 'herb_fresh')  # not 'other'
        self.assertEqual(infer_category('buttermilk'), 'dairy')  # not fat_butter
        self.assertEqual(infer_category('bell-pepper'), 'vegetable')  # not spice


class BandFlagTest(SimpleTestCase):
    def test_within_band_ok(self):
        # potatoes ~13.5 Kč/kg is fine for a vegetable
        self.assertIsNone(band_flag('vegetable', 13.5, 'Kč/kg'))

    def test_above_band_flagged(self):
        # 900 Kč/kg is above the fruit ceiling (berries stretch it, not this far)
        reason = band_flag('fruit', 900.0, 'Kč/kg')
        self.assertIsNotNone(reason)
        self.assertIn('above', reason)

    def test_below_band_flagged(self):
        # plain flour at 9.9 Kč/kg is below the grain floor
        reason = band_flag('flour_grain', 5.0, 'Kč/kg')
        self.assertIsNotNone(reason)
        self.assertIn('below', reason)

    def test_spice_thousands_ok(self):
        # vanilla pods ~19000 Kč/kg is legitimate for a spice
        self.assertIsNone(band_flag('spice', 19000.0, 'Kč/kg'))

    def test_egg_piece_band(self):
        self.assertIsNone(band_flag(None, 5.3, 'Kč/ks', slug='eggs'))
        self.assertIsNotNone(band_flag(None, 20.0, 'Kč/ks', slug='eggs'))


class RatioFlagsTest(SimpleTestCase):
    def test_breast_thigh_overpriced_flagged(self):
        # 349.9 / 109.9 = 3.18x -> outside [1.2, 2.0]
        prices = {
            'chicken-breast': {'unit': 'g', 'price_per_unit': 0.3499},
            'chicken-thigh': {'unit': 'g', 'price_per_unit': 0.1099},
        }
        flagged = dict(ratio_flags(prices))
        self.assertIn('chicken-breast', flagged)

    def test_breast_thigh_in_band_ok(self):
        # 169.9 / 109.9 = 1.55x -> within [1.2, 2.0]
        prices = {
            'chicken-breast': {'unit': 'g', 'price_per_unit': 0.1699},
            'chicken-thigh': {'unit': 'g', 'price_per_unit': 0.1099},
        }
        self.assertEqual(dict(ratio_flags(prices)), {})

    def test_missing_family_member_no_crash(self):
        self.assertEqual(dict(ratio_flags({'beef': {'unit': 'g',
                                                    'price_per_unit': 0.34}})), {})
