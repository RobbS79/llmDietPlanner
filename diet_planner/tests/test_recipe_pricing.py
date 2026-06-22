from django.test import SimpleTestCase

from diet_planner.services.recipe_pricing import price_recipe, PACK_OVERHEAD

# Injected fake book — tests never touch the real book file or the DB.
BOOK = {
    'chicken': {'unit': 'g', 'price_per_unit': 0.30, 'pack': 500.0},
    'rice': {'unit': 'g', 'price_per_unit': 0.05, 'pack': 1000.0},
}


def ing(canonical, qty, unit, **kw):
    # `name` mirrors `canonical` so the canonical-first path is exercised
    # without hitting resolve_canonical (which needs the DB).
    return {'name': canonical, 'canonical': canonical,
            'quantity': qty, 'unit': unit, **kw}


class PriceRecipeTotalsTest(SimpleTestCase):
    def test_low_is_sum_of_consumed_costs(self):
        # chicken 400 g * 0.30 = 120 ; rice 200 g * 0.05 = 10 ; low = 130
        r = price_recipe([ing('chicken', 400, 'g'), ing('rice', 200, 'g')], 4, book=BOOK)
        self.assertEqual(r.low, 130.0)

    def test_high_is_low_times_overhead(self):
        r = price_recipe([ing('chicken', 400, 'g'), ing('rice', 200, 'g')], 4, book=BOOK)
        self.assertEqual(r.high, 130.0 * PACK_OVERHEAD)  # 162.5

    def test_per_portion_divides_by_servings(self):
        r = price_recipe([ing('chicken', 400, 'g'), ing('rice', 200, 'g')], 4, book=BOOK)
        self.assertEqual(r.per_portion_low, 130.0 / 4)
        self.assertEqual(r.per_portion_high, (130.0 * PACK_OVERHEAD) / 4)

    def test_missing_servings_yields_no_per_portion(self):
        r = price_recipe([ing('chicken', 400, 'g')], None, book=BOOK)
        self.assertIsNone(r.per_portion_low)
        self.assertIsNone(r.per_portion_high)
        self.assertEqual(r.low, 120.0)


class PriceRecipeCoverageTest(SimpleTestCase):
    def test_unknown_ingredient_counts_toward_total_not_priced(self):
        r = price_recipe([ing('chicken', 400, 'g'), ing('mystery', 100, 'g')], 2, book=BOOK)
        self.assertEqual(r.priced_count, 1)
        self.assertEqual(r.total_count, 2)
        self.assertEqual(r.low, 120.0)

    def test_low_coverage_marks_not_confident(self):
        # 1 of 2 priced = 0.5 < COVERAGE_MIN (0.6)
        r = price_recipe([ing('chicken', 400, 'g'), ing('mystery', 100, 'g')], 2, book=BOOK)
        self.assertFalse(r.confident)

    def test_full_coverage_is_confident(self):
        r = price_recipe([ing('chicken', 400, 'g'), ing('rice', 200, 'g')], 2, book=BOOK)
        self.assertTrue(r.confident)

    def test_optional_ingredient_excluded_from_totals_and_counts(self):
        r = price_recipe(
            [ing('chicken', 400, 'g'), ing('rice', 200, 'g', optional=True)], 2, book=BOOK)
        self.assertEqual(r.low, 120.0)
        self.assertEqual(r.total_count, 1)
        self.assertEqual(r.priced_count, 1)

    def test_nothing_prices_returns_none(self):
        self.assertIsNone(price_recipe([ing('mystery', 100, 'g')], 2, book=BOOK))


class PriceRecipeEdgeTest(SimpleTestCase):
    def test_eur_currency_scales_the_czk_book(self):
        # low 130 CZK / 25 = 5.2 EUR
        r = price_recipe([ing('chicken', 400, 'g'), ing('rice', 200, 'g')],
                         4, currency='EUR', book=BOOK)
        self.assertEqual(r.currency, 'EUR')
        self.assertAlmostEqual(r.low, 5.2, places=2)

    def test_empty_ingredients_returns_none(self):
        self.assertIsNone(price_recipe([], 4, book=BOOK))

    def test_zero_quantity_line_is_unpriced(self):
        r = price_recipe([ing('chicken', 0, 'g'), ing('rice', 200, 'g')], 2, book=BOOK)
        self.assertEqual(r.priced_count, 1)
        self.assertEqual(r.low, 10.0)

    def test_zero_servings_yields_no_per_portion(self):
        r = price_recipe([ing('chicken', 400, 'g')], 0, book=BOOK)
        self.assertIsNone(r.per_portion_low)
        self.assertEqual(r.low, 120.0)
