from django.test import SimpleTestCase

from diet_planner.services.pricing_core import consumed_line_cost


class ConsumedLineCostTest(SimpleTestCase):
    G_ENTRY = {'unit': 'g', 'price_per_unit': 0.30, 'pack': 500.0}
    KS_ENTRY = {'unit': 'ks', 'price_per_unit': 2.0, 'pack': 10.0}

    def test_same_dimension_is_prorated(self):
        # 400 g * 0.30 = 120.0 (charge only what's consumed, not a pack)
        self.assertEqual(consumed_line_cost(self.G_ENTRY, 400, 'g'), 120.0)

    def test_zero_or_missing_quantity_unpriceable(self):
        self.assertIsNone(consumed_line_cost(self.G_ENTRY, 0, 'g'))
        self.assertIsNone(consumed_line_cost(self.G_ENTRY, None, 'g'))

    def test_dimension_mismatch_no_grams_falls_back_to_one_pack(self):
        # recipe in grams, book per-piece, no bridge -> one typical pack: 10 * 2.0
        self.assertEqual(consumed_line_cost(self.KS_ENTRY, 100, 'g'), 20.0)

    def test_piece_weight_bridge(self):
        # 220 g / 110 g-per-piece = 2 pieces * 2.0 = 4.0
        self.assertEqual(consumed_line_cost(self.KS_ENTRY, 220, 'g', grams=110), 4.0)

    def test_no_price_unpriceable(self):
        self.assertIsNone(consumed_line_cost({'unit': 'g', 'price_per_unit': 0, 'pack': 5}, 10, 'g'))
