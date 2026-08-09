from unittest import mock

from django.test import SimpleTestCase

from diet_planner.services.recipe_pricing import price_recipe, price_recipe_lines, PACK_OVERHEAD

# Injected fake book — tests never touch the real book file or the DB.
BOOK = {
    'chicken': {'unit': 'g', 'price_per_unit': 0.30, 'pack': 500.0, 'verified': True},
    'rice': {'unit': 'g', 'price_per_unit': 0.05, 'pack': 1000.0, 'verified': False},
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


class PriceRecipeLinesTest(SimpleTestCase):
    """Per-line breakdown backing the priced shopping-list UI (Component 2)."""

    def test_line_shape_for_priced_ingredient(self):
        r = price_recipe_lines([ing('chicken', 400, 'g')], 2, book=BOOK)
        self.assertEqual(len(r.lines), 1)
        line = r.lines[0]
        self.assertEqual(line.canonical, 'chicken')
        self.assertEqual(line.consumed_cost, 120.0)
        self.assertTrue(line.priced)
        self.assertTrue(line.verified)  # BOOK['chicken']['verified'] is True

    def test_estimate_line_is_priced_but_not_verified(self):
        r = price_recipe_lines([ing('rice', 200, 'g')], 2, book=BOOK)
        line = r.lines[0]
        self.assertTrue(line.priced)
        self.assertFalse(line.verified)  # BOOK['rice']['verified'] is False

    def test_unpriced_ingredient_never_gets_a_fabricated_cost(self):
        r = price_recipe_lines([ing('mystery', 100, 'g')], 2, book=BOOK)
        line = r.lines[0]
        self.assertFalse(line.priced)
        self.assertIsNone(line.consumed_cost)
        self.assertFalse(line.verified)

    def test_totals_reflect_priced_lines_only(self):
        r = price_recipe_lines(
            [ing('chicken', 400, 'g'), ing('rice', 200, 'g'), ing('mystery', 100, 'g')],
            2, book=BOOK)
        self.assertEqual(r.priced_count, 2)
        self.assertEqual(r.total_count, 3)
        self.assertEqual(r.verified_count, 1)  # only chicken is verified
        self.assertEqual(r.low, 130.0)  # chicken 120 + rice 10; mystery contributes 0
        self.assertEqual(r.high, 130.0 * PACK_OVERHEAD)

    def test_optional_ingredient_excluded_from_lines(self):
        r = price_recipe_lines(
            [ing('chicken', 400, 'g'), ing('rice', 200, 'g', optional=True)], 2, book=BOOK)
        self.assertEqual(len(r.lines), 1)
        self.assertEqual(r.total_count, 1)

    def test_confident_true_at_coverage_boundary(self):
        # 3 of 5 priced = 0.6 == COVERAGE_MIN -> confident
        ingredients = [ing('chicken', 100, 'g'), ing('chicken', 100, 'g'),
                       ing('chicken', 100, 'g'), ing('mystery', 100, 'g'),
                       ing('mystery2', 100, 'g')]
        r = price_recipe_lines(ingredients, 2, book=BOOK)
        self.assertEqual(r.priced_count, 3)
        self.assertEqual(r.total_count, 5)
        self.assertTrue(r.confident)

    def test_confident_false_just_below_coverage_boundary(self):
        # 2 of 5 priced = 0.4 < COVERAGE_MIN -> not confident
        ingredients = [ing('chicken', 100, 'g'), ing('chicken', 100, 'g'),
                       ing('mystery', 100, 'g'), ing('mystery2', 100, 'g'),
                       ing('mystery3', 100, 'g')]
        r = price_recipe_lines(ingredients, 2, book=BOOK)
        self.assertEqual(r.priced_count, 2)
        self.assertEqual(r.total_count, 5)
        self.assertFalse(r.confident)

    def test_returns_result_with_all_unpriced_lines_when_nothing_prices(self):
        # Unlike price_recipe (which returns None), price_recipe_lines still
        # returns a result so the UI can render "bez ceny" per row.
        r = price_recipe_lines([ing('mystery', 100, 'g')], 2, book=BOOK)
        self.assertIsNotNone(r)
        self.assertEqual(r.priced_count, 0)
        self.assertEqual(r.low, 0.0)
        self.assertFalse(r.confident)

    def test_empty_ingredients_returns_none(self):
        self.assertIsNone(price_recipe_lines([], 4, book=BOOK))

    def test_eur_currency_scales_line_costs(self):
        r = price_recipe_lines([ing('chicken', 400, 'g')], 2, currency='EUR', book=BOOK)
        self.assertAlmostEqual(r.lines[0].consumed_cost, 120.0 / 25.0, places=4)
        self.assertAlmostEqual(r.low, 120.0 / 25.0, places=4)


class StringIngredientEntriesTest(SimpleTestCase):
    """Curated recipes store ingredients as dicts; LLM-generated meals store
    them as plain strings ("pappudia tofu (#2153)"). Prod 2026-08-09: every
    recipe endpoint of plan 140 returned a raw 500 —
    `AttributeError: 'str' object has no attribute 'get'` from
    `price_recipe`, surfaced through RecipeSerializer.get_price_range. Pricing
    must tolerate both shapes; an unresolvable string is simply unpriced."""

    def test_string_ingredients_do_not_crash_price_recipe(self):
        with mock.patch('diet_planner.services.recipe_pricing.resolve_canonical',
                        return_value=None):
            r = price_recipe(['pappudia tofu (#2153)', 'cuketa zelená (#2169)'],
                             1, book=BOOK)
        self.assertIsNone(r)   # nothing resolved, so nothing prices

    def test_string_ingredient_prices_when_its_name_resolves(self):
        canonical = mock.Mock(slug='chicken')
        with mock.patch('diet_planner.services.recipe_pricing.resolve_canonical',
                        return_value=canonical):
            # No quantity in a bare string -> no consumable cost, but the entry
            # still counts toward coverage rather than exploding.
            r = price_recipe(['kuřecí prsa', ing('rice', 200, 'g')], 2, book=BOOK)
        self.assertIsNotNone(r)
        self.assertEqual(r.total_count, 2)

    def test_mixed_string_and_dict_entries_are_both_counted(self):
        with mock.patch('diet_planner.services.recipe_pricing.resolve_canonical',
                        return_value=None):
            r = price_recipe_lines(['tofu', ing('chicken', 400, 'g')], 2, book=BOOK)
        self.assertEqual(len(r.lines), 2)
        self.assertEqual(r.lines[0].name, 'tofu')
        self.assertEqual(r.low, 120.0)          # only the dict entry priced

    def test_blank_and_none_entries_are_skipped_not_counted(self):
        with mock.patch('diet_planner.services.recipe_pricing.resolve_canonical',
                        return_value=None):
            r = price_recipe_lines([None, '   ', ing('chicken', 400, 'g')], 2, book=BOOK)
        self.assertEqual(len(r.lines), 1)
        self.assertEqual(r.total_count, 1)
