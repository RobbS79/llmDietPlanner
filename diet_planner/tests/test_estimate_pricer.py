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

    def test_whole_pack_cost_converts_units(self):
        # 680 g of a 650 g pack → 2 packs; price/g applied to pack size.
        p = self._pricer({})
        cost = p._whole_pack_cost(CHICKEN, 680, 'g')
        self.assertAlmostEqual(cost, 2 * 650 * 0.3499, places=2)

    def test_mixed_dimension_assumes_one_pack(self):
        p = self._pricer({})
        # book priced per gram, recipe asks pieces → can't convert → 1 pack
        cost = p._whole_pack_cost(CHICKEN, 2, 'ks')
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
        self.assertAlmostEqual(est['total'], 2 * 650 * 0.3499, places=1)
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
        self.assertGreater(est['total'], 2 * 650 * 0.3499)

    def test_unknown_ingredient_is_not_available(self):
        p = self._pricer({'kureci-prsa': CHICKEN})
        resolved, est = p.price(
            [{'ingredient': 'jednorožčí steak', 'quantity': 200, 'unit': 'g'}],
            basics_on=True,
        )
        self.assertEqual(resolved[0]['price_source'], 'not_available')
        self.assertIsNone(resolved[0]['price_total'])
        self.assertEqual(est['priced_items'], 0)

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
