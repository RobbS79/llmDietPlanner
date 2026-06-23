"""
EstimatePricer — static price-book, whole-pack estimate, pantry-toggle aware.
See [[pricing-pivot-static-book]].
"""
from django.test import TestCase
from django.contrib.auth.models import User

from diet_planner.models import DietaryGoal
from diet_planner.services.canonical_lookup import clear_cache
from diet_planner.services.estimate_pricer import EstimatePricer
from diet_planner.tests.factories import make_canonical


CHICKEN = {'pack': 650, 'price_per_unit': 0.3499, 'unit': 'g', 'name_cs': 'kuřecí prsa'}
SALT = {'pack': 250, 'price_per_unit': 0.74, 'unit': 'g', 'name_cs': 'sůl'}


class EstimatePricerTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('est', password='t')
        self.goal = DietaryGoal.objects.create(
            user=self.user, prompt='t', country='CZ', city='Prague',
            shop='ROHLIK', num_days=7, currency='CZK',
        )
        make_canonical('kuřecí prsa', is_pantry_staple=False, default_unit='g')
        make_canonical('sůl', is_pantry_staple=True, default_unit='g')
        clear_cache()

    def _pricer(self, book):
        p = EstimatePricer(self.goal)
        p.book = book
        return p

    def test_consumed_cost_is_prorated(self):
        # Pro-rated: charge only the consumed grams, not a whole pack.
        p = self._pricer({})
        cost = p._consumed_cost(CHICKEN, 680, 'g')
        self.assertAlmostEqual(cost, 680 * 0.3499, places=2)

    def test_consumed_cost_converts_kg_to_g(self):
        p = self._pricer({})
        # 0.4 kg consumed → 400 g × price/g
        cost = p._consumed_cost(CHICKEN, 0.4, 'kg')
        self.assertAlmostEqual(cost, 400 * 0.3499, places=2)

    def test_mixed_dimension_falls_back_to_one_pack(self):
        p = self._pricer({})
        # book priced per gram, recipe asks pieces → can't convert → 1 pack
        cost = p._consumed_cost(CHICKEN, 2, 'ks')
        self.assertAlmostEqual(cost, 650 * 0.3499, places=2)

    def test_pantry_excluded_from_total_when_basics_on(self):
        p = self._pricer({'kureci-prsa': CHICKEN, 'sul': SALT})
        items = [
            {'ingredient': 'kuřecí prsa', 'quantity': 680, 'unit': 'g'},
            {'ingredient': 'sůl', 'quantity': 10, 'unit': 'g'},
        ]
        resolved, est = p.price(items, basics_on=True, fridge_on=False)
        self.assertEqual(est['total_items'], 1)            # salt dropped
        self.assertEqual(est['priced_items'], 1)
        self.assertAlmostEqual(est['total'], 680 * 0.3499, places=1)  # pro-rated
        salt = next(r for r in resolved if r['ingredient'] == 'sůl')
        self.assertTrue(salt['pantry_excluded'])
        self.assertEqual(salt['price_source'], 'pantry_estimate')

    def test_pantry_included_when_basics_off(self):
        p = self._pricer({'kureci-prsa': CHICKEN, 'sul': SALT})
        items = [
            {'ingredient': 'kuřecí prsa', 'quantity': 680, 'unit': 'g'},
            {'ingredient': 'sůl', 'quantity': 10, 'unit': 'g'},
        ]
        resolved, est = p.price(items, basics_on=False, fridge_on=False)
        self.assertEqual(est['total_items'], 2)
        # chicken (pro-rated) + salt (pro-rated), both counted
        self.assertAlmostEqual(est['total'], 680 * 0.3499 + 10 * 0.74, places=1)

    def test_unknown_ingredient_is_not_available(self):
        p = self._pricer({'kureci-prsa': CHICKEN})
        resolved, est = p.price(
            [{'ingredient': 'jednorožčí steak', 'quantity': 200, 'unit': 'g'}],
            basics_on=True,
        )
        self.assertEqual(resolved[0]['price_source'], 'not_available')
        self.assertIsNone(resolved[0]['price_total'])
        self.assertEqual(est['priced_items'], 0)

    def test_uses_carried_canonical_slug_when_name_unresolvable(self):
        # A curated recipe pre-maps each ingredient to a canonical slug. For
        # type-adjective variants ("červené zelí") the free-text name has no
        # canonical/alias of its own, so name re-resolution returns None. The
        # slug the item carries must still price it (see
        # [[pricing-catalog-id-resolution]]: price via canonical, not name).
        from diet_planner.services.canonical_lookup import resolve_canonical
        self.assertIsNone(resolve_canonical('červené zelí'))  # precondition
        p = self._pricer({'red-cabbage': {
            'pack': 500, 'price_per_unit': 0.04, 'unit': 'g', 'name_cs': 'zelí červené',
        }})
        resolved, est = p.price(
            [{'ingredient': 'červené zelí', 'quantity': 300, 'unit': 'g',
              'canonical': 'red-cabbage'}],
            basics_on=True,
        )
        self.assertNotEqual(resolved[0]['price_source'], 'not_available')
        self.assertAlmostEqual(resolved[0]['price_total'], 300 * 0.04, places=2)
        self.assertEqual(est['priced_items'], 1)

    def test_aggregated_carried_canonical_prices_end_to_end(self):
        # The whole bug in one test: a curated meal carries the canonical slug;
        # aggregation must keep it and the pricer must use it, so a variant whose
        # free-text name won't re-resolve ("červené zelí") still gets priced.
        from diet_planner.tasks import aggregate_ingredients_from_meals
        from diet_planner.services.canonical_lookup import resolve_canonical
        self.assertIsNone(resolve_canonical('červené zelí'))  # precondition
        days = [{'day_number': 1, 'lunch': {'ingredients': [
            {'name': 'červené zelí', 'quantity': 300, 'unit': 'g',
             'canonical': 'red-cabbage'},
        ]}}]
        items = aggregate_ingredients_from_meals(days)
        p = self._pricer({'red-cabbage': {
            'pack': 500, 'price_per_unit': 0.04, 'unit': 'g', 'name_cs': 'zelí červené',
        }})
        resolved, est = p.price(items, basics_on=True)
        self.assertEqual(est['priced_items'], 1)
        self.assertNotEqual(resolved[0]['price_source'], 'not_available')
        self.assertAlmostEqual(resolved[0]['price_total'], 300 * 0.04, places=2)

    def test_prices_count_book_entry_against_gram_recipe_via_piece_weight(self):
        # The book has onion as a per-piece (ks) entry, but the recipe asks for
        # 220 g of onion. Without the piece<->weight bridge the pricer falls back
        # to one whole pack (~9 onions); with it, 220 g ≈ 2 onions.
        from unittest.mock import patch
        ONION_KS = {'pack': 9.09, 'price_per_unit': 2.189, 'unit': 'ks',
                    'name_cs': 'cibule'}
        make_canonical('cibule', is_pantry_staple=False, default_unit='ks')
        clear_cache()
        p = self._pricer({'cibule': ONION_KS})
        with patch('diet_planner.services.estimate_pricer.load_piece_weights',
                   return_value={'cibule': 110.0}):
            resolved, _ = p.price(
                [{'ingredient': 'cibule', 'quantity': 220, 'unit': 'g',
                  'canonical': 'cibule'}],
                basics_on=True,
            )
        # 220 g / 110 g-per-piece = 2 onions × 2.189 ≈ 4.38 (NOT a whole pack).
        self.assertAlmostEqual(resolved[0]['price_total'], 2 * 2.189, places=2)

    def test_no_shop_or_brand_fields_leak(self):
        p = self._pricer({'kureci-prsa': CHICKEN})
        resolved, _ = p.price(
            [{'ingredient': 'kuřecí prsa', 'quantity': 680, 'unit': 'g',
              'matched_product_name': 'Farma rodiny Němcovy Kuřecí prsa',
              'shop': 'ROHLIK'}],
            basics_on=True,
        )
        self.assertNotIn('matched_product_name', resolved[0])
        self.assertNotIn('shop', resolved[0])

    def test_per_day_divides_by_num_days(self):
        p = self._pricer({'kureci-prsa': CHICKEN})
        _, est = p.price([{'ingredient': 'kuřecí prsa', 'quantity': 680, 'unit': 'g'}],
                         basics_on=True)
        self.assertAlmostEqual(est['per_day'], round(est['total'] / 7, 2), places=2)


class PriceBookFileTest(TestCase):
    """The committed book loads and is shaped as the estimator expects."""

    def test_book_loads_and_has_entries(self):
        from diet_planner.services.estimate_pricer import _load_book, reload_book
        reload_book()
        book = _load_book()
        self.assertEqual(book['currency'], 'CZK')
        self.assertGreater(len(book['prices']), 50)
        # every entry has the fields the pricer reads
        for slug, e in book['prices'].items():
            self.assertIn('pack', e)
            self.assertIn('price_per_unit', e)
            self.assertIn('unit', e)
