"""
Tests for shopping-list pricing: the honest price range + factual deals logic.

Mirrors `test_leaflet_validity.py`: the pure decision functions
(`classify_pantry_level`, `item_is_excluded`, `store_basket_total`,
`qualify_deal`) are exercised as SimpleTestCase (no DB, always runnable), and
the DB-touching `compute_pricing()` end-to-end is a TestCase that seeds a few
GroceryStore/StoreProduct/PriceRecord rows.

Behaviors asserted come from SHOPPING_LIST_PRICING_PLAN.md Section 6:
- #1 range = cheapest vs priciest single-store basket (non-pantry items only)
- #2 basics ON / fridge OFF default semantics (the exclusion truth table)
- #3 a leaflet deal qualifies only if it's the cheapest source across stores
- #7 upcoming leaflets are surfaced (bucketed separately from current)
"""
import datetime as dt
from decimal import Decimal
from types import SimpleNamespace

from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from diet_planner.services.shopping_list_pricing import (
    classify_pantry_level,
    item_is_excluded,
    qualify_deal,
    store_basket_total,
)


def _canonical(name='', name_cs='', name_sk='', is_pantry_staple=False):
    """Stand-in for a CanonicalIngredient — classify_pantry_level only reads
    .name, .name_cs, .name_sk, .is_pantry_staple, so a stub object suffices."""
    return SimpleNamespace(
        name=name,
        name_cs=name_cs,
        name_sk=name_sk,
        is_pantry_staple=is_pantry_staple,
    )


# --------------------------------------------------------------------------- #
# Pure functions — SimpleTestCase, no DB.
# --------------------------------------------------------------------------- #

class ClassifyPantryLevelTest(SimpleTestCase):
    def test_direct_name_hit_fridge(self):
        # English fridge basics by the passed-in ingredient name.
        self.assertEqual(classify_pantry_level('milk', None), 'fridge')
        self.assertEqual(classify_pantry_level('butter', None), 'fridge')
        self.assertEqual(classify_pantry_level('egg', None), 'fridge')
        self.assertEqual(classify_pantry_level('eggs', None), 'fridge')

    def test_direct_name_hit_czech_slovak(self):
        # Czech / Slovak names also live in FRIDGE_BASIC_NAMES.
        for name in ('mléko', 'máslo', 'vejce', 'mlieko', 'vajcia'):
            self.assertEqual(classify_pantry_level(name, None), 'fridge', name)

    def test_name_normalized_case_and_whitespace(self):
        self.assertEqual(classify_pantry_level('  MLÉKO  ', None), 'fridge')

    def test_canonical_name_hit_fridge(self):
        # Ingredient text doesn't match, but the canonical .name does.
        c = _canonical(name='butter')
        self.assertEqual(classify_pantry_level('plain unsalted spread', c), 'fridge')

    def test_canonical_name_cs_hit_fridge(self):
        c = _canonical(name='something-else', name_cs='mléko')
        self.assertEqual(classify_pantry_level('whole fat product', c), 'fridge')

    def test_canonical_name_sk_hit_fridge(self):
        c = _canonical(name='something-else', name_sk='vajcia')
        self.assertEqual(classify_pantry_level('farm fresh', c), 'fridge')

    def test_canonical_pantry_staple_dry(self):
        c = _canonical(name='olive oil', is_pantry_staple=True)
        self.assertEqual(classify_pantry_level('olivový olej', c), 'dry')

    def test_fridge_wins_over_dry(self):
        # A canonical that is BOTH a fridge basic name and pantry staple should
        # classify as 'fridge' (fridge check runs first).
        c = _canonical(name='milk', is_pantry_staple=True)
        self.assertEqual(classify_pantry_level('milk', c), 'fridge')

    def test_plain_ingredient_none(self):
        c = _canonical(name='chicken breast', is_pantry_staple=False)
        self.assertIsNone(classify_pantry_level('chicken breast', c))

    def test_no_canonical_plain_ingredient_none(self):
        self.assertIsNone(classify_pantry_level('banana', None))

    def test_empty_and_none_input(self):
        self.assertIsNone(classify_pantry_level('', None))
        self.assertIsNone(classify_pantry_level(None, None))
        self.assertIsNone(classify_pantry_level('   ', None))

    def test_canonical_with_empty_alias_fields(self):
        # Empty name_cs/name_sk must not match the empty string in the set.
        c = _canonical(name='rice', name_cs='', name_sk='', is_pantry_staple=False)
        self.assertIsNone(classify_pantry_level('rice', c))


class ItemIsExcludedTest(SimpleTestCase):
    """Truth table (decision #2): dry excluded iff basics_on, fridge excluded
    iff fridge_on, None never excluded."""

    def test_dry_excluded_only_when_basics_on(self):
        self.assertTrue(item_is_excluded('dry', basics_on=True, fridge_on=False))
        self.assertTrue(item_is_excluded('dry', basics_on=True, fridge_on=True))
        self.assertFalse(item_is_excluded('dry', basics_on=False, fridge_on=False))
        self.assertFalse(item_is_excluded('dry', basics_on=False, fridge_on=True))

    def test_fridge_excluded_only_when_fridge_on(self):
        self.assertTrue(item_is_excluded('fridge', basics_on=False, fridge_on=True))
        self.assertTrue(item_is_excluded('fridge', basics_on=True, fridge_on=True))
        self.assertFalse(item_is_excluded('fridge', basics_on=False, fridge_on=False))
        self.assertFalse(item_is_excluded('fridge', basics_on=True, fridge_on=False))

    def test_none_level_never_excluded(self):
        for basics_on in (True, False):
            for fridge_on in (True, False):
                self.assertFalse(
                    item_is_excluded(None, basics_on=basics_on, fridge_on=fridge_on),
                    (basics_on, fridge_on),
                )

    def test_default_toggle_semantics(self):
        # Decision #2 defaults: basics ON, fridge OFF.
        self.assertTrue(item_is_excluded('dry', basics_on=True, fridge_on=False))
        self.assertFalse(item_is_excluded('fridge', basics_on=True, fridge_on=False))


class StoreBasketTotalTest(SimpleTestCase):
    def _entries(self):
        # Two items. LIDL carries both; ROHLIK carries only the first.
        return [
            {'avg': Decimal('20'), 'by_store': {'LIDL_CZ': Decimal('18'), 'ROHLIK': Decimal('22')}},
            {'avg': Decimal('50'), 'by_store': {'LIDL_CZ': Decimal('50')}},
        ]

    def test_store_carries_all_items(self):
        result = store_basket_total('LIDL_CZ', self._entries())
        self.assertEqual(result['total'], Decimal('68'))   # 18 + 50
        self.assertEqual(result['covered'], 2)
        self.assertEqual(result['imputed'], 0)
        self.assertEqual(result['n'], 2)

    def test_store_carries_some_imputes_the_rest(self):
        # ROHLIK carries item 1 at 22; item 2 imputed at its cross-store avg 50.
        result = store_basket_total('ROHLIK', self._entries())
        self.assertEqual(result['total'], Decimal('72'))   # 22 + 50 (imputed)
        self.assertEqual(result['covered'], 1)
        self.assertEqual(result['imputed'], 1)
        self.assertEqual(result['n'], 2)

    def test_store_carries_none_returns_none(self):
        self.assertIsNone(store_basket_total('TESCO_CZ', self._entries()))

    def test_missing_item_with_none_avg_is_skipped(self):
        # Store lacks the item and its avg is None -> contributes nothing,
        # neither to total nor to imputed count.
        entries = [
            {'avg': Decimal('30'), 'by_store': {'LIDL_CZ': Decimal('30')}},
            {'avg': None, 'by_store': {'ROHLIK': Decimal('99')}},
        ]
        result = store_basket_total('LIDL_CZ', entries)
        self.assertEqual(result['total'], Decimal('30'))
        self.assertEqual(result['covered'], 1)
        self.assertEqual(result['imputed'], 0)
        self.assertEqual(result['n'], 2)

    def test_total_is_decimal(self):
        result = store_basket_total('LIDL_CZ', self._entries())
        self.assertIsInstance(result['total'], Decimal)

    def test_empty_basket_returns_none(self):
        self.assertIsNone(store_basket_total('LIDL_CZ', []))


class QualifyDealTest(SimpleTestCase):
    def test_qualifies_when_nothing_cheaper_exists(self):
        # No other source -> any leaflet price is the cheapest source.
        self.assertTrue(qualify_deal(Decimal('18.90'), None))

    def test_qualifies_when_strictly_cheaper(self):
        self.assertTrue(qualify_deal(Decimal('18.90'), Decimal('24.90')))

    def test_qualifies_at_boundary_equal_prices(self):
        # Decision #3 cheapest-source: equal price still qualifies (<=).
        self.assertTrue(qualify_deal(Decimal('20.00'), Decimal('20.00')))

    def test_does_not_qualify_when_pricier(self):
        # A "sale" that's still pricier than another store's regular price.
        self.assertFalse(qualify_deal(Decimal('24.90'), Decimal('18.90')))


# --------------------------------------------------------------------------- #
# DB layer — compute_pricing() end-to-end.
#
# Like PriceRecordBucketingTest in test_leaflet_validity.py, this is a plain
# TestCase that needs a real DB. See the module docstring / the agent report:
# the project's catalog migration uses Postgres-only `pg_indexes`, so this
# class cannot run on the default SQLite test backend in this sandbox. It is
# written to run against the project's Postgres test DB.
# --------------------------------------------------------------------------- #

class ComputePricingTest(TestCase):
    CZ_SHOPS = ['LIDL_CZ', 'ROHLIK', 'ALBERT_CZ', 'KAUFLAND_CZ', 'PENNY_CZ', 'TESCO_CZ', 'KOSIK_CZ']

    def _store(self, code, name):
        from diet_planner.models import GroceryStore
        # get_or_create: migration 0017 seeds these stores into the test DB, so
        # a plain create() would collide on the unique `code`.
        store, _ = GroceryStore.objects.get_or_create(
            code=code,
            defaults=dict(
                name=name, chain=code.split('_')[0],
                country='CZ', currency='CZK', is_active=True,
            ),
        )
        return store

    def _product(self, store, name, normalized):
        from diet_planner.models import StoreProduct
        return StoreProduct.objects.create(
            store=store, name=name, normalized_name=normalized, is_active=True,
        )

    def _record(self, sp, price, source_type, valid_from, valid_until,
                original_price=None):
        from diet_planner.models import PriceRecord
        return PriceRecord.objects.create(
            store_product=sp,
            price=Decimal(price),
            currency='CZK',
            source_type=source_type,
            original_price=Decimal(original_price) if original_price else None,
            valid_from=valid_from,
            valid_until=valid_until,
            scraped_at=timezone.now(),
        )

    def setUp(self):
        from diet_planner.models import PriceSourceType
        self.PriceSourceType = PriceSourceType
        now = timezone.now()
        self.now = now

        lidl = self._store('LIDL_CZ', 'Lidl')
        rohlik = self._store('ROHLIK', 'Rohlík')
        albert = self._store('ALBERT_CZ', 'Albert')

        # --- chicken: regular prices at all three stores (range item) ---
        for store, price in ((lidl, '110'), (rohlik, '95'), (albert, '130')):
            sp = self._product(store, 'Kuřecí prsa', 'chicken')
            self._record(sp, price, PriceSourceType.STORE_REGULAR,
                         now - dt.timedelta(days=1), now + dt.timedelta(days=7))

        # --- milk: CURRENT leaflet deal at Lidl that IS the cheapest source ---
        # Lidl 18.90 (sale) vs Rohlik regular 22.00 -> qualifies (decision #3).
        lidl_milk = self._product(lidl, 'Mléko 1L', 'milk')
        self._record(lidl_milk, '18.90', PriceSourceType.LEAFLET_DISCOUNT,
                     now - dt.timedelta(days=1), now + dt.timedelta(days=2),
                     original_price='24.90')
        rohlik_milk = self._product(rohlik, 'Mléko polotučné', 'milk')
        self._record(rohlik_milk, '22.00', PriceSourceType.STORE_REGULAR,
                     now - dt.timedelta(days=1), now + dt.timedelta(days=7))

        # --- salmon: UPCOMING leaflet deal at Albert (cheapest source) ---
        albert_salmon = self._product(albert, 'Losos filet', 'salmon')
        self._record(albert_salmon, '99', PriceSourceType.LEAFLET_DISCOUNT,
                     now + dt.timedelta(days=3), now + dt.timedelta(days=10),
                     original_price='139')

        # --- cheese: NON-qualifying "deal" — Tesco sale pricier than a
        #     competitor's regular price, so it must be dropped (decision #3) ---
        kaufland = self._store('KAUFLAND_CZ', 'Kaufland')
        kauf_cheese = self._product(kaufland, 'Eidam sleva', 'cheese')
        self._record(kauf_cheese, '90', PriceSourceType.LEAFLET_DISCOUNT,
                     now - dt.timedelta(days=1), now + dt.timedelta(days=2),
                     original_price='110')
        rohlik_cheese = self._product(rohlik, 'Eidam', 'cheese')
        self._record(rohlik_cheese, '70', PriceSourceType.STORE_REGULAR,
                     now - dt.timedelta(days=1), now + dt.timedelta(days=7))

        self.items = [
            {'ingredient': 'chicken'},
            {'ingredient': 'milk'},
            {'ingredient': 'salmon'},
            {'ingredient': 'cheese'},
        ]

    def _compute(self, **kwargs):
        from diet_planner.services.shopping_list_pricing import compute_pricing
        return compute_pricing(self.items, country='CZ', currency='CZK', **kwargs)

    def test_price_range_low_high_and_stores(self):
        result = self._compute(basics_on=True, fridge_on=False)
        pr = result['price_range']
        self.assertIsNotNone(pr)
        self.assertEqual(pr['currency'], 'CZK')
        self.assertLessEqual(pr['low'], pr['high'])
        # Rohlik is cheapest carrier of chicken (95) and milk (22); Albert is
        # the priciest on chicken (130).
        self.assertEqual(pr['store_low'], 'ROHLIK')

    def test_deals_bucketing_current_and_upcoming(self):
        result = self._compute()
        deals = result['deals']
        statuses = {(d['store'], d['status']) for d in deals}
        # Current Lidl milk deal present.
        self.assertIn(('LIDL_CZ', 'current'), statuses)
        # Upcoming Albert salmon deal present (decision #7).
        self.assertIn(('ALBERT_CZ', 'upcoming'), statuses)
        # Non-qualifying Kaufland cheese "deal" dropped (decision #3).
        self.assertNotIn(('KAUFLAND_CZ', 'current'), statuses)

    def test_qualifying_deal_carries_savings(self):
        result = self._compute()
        lidl_current = next(
            d for d in result['deals']
            if d['store'] == 'LIDL_CZ' and d['status'] == 'current'
        )
        milk_item = lidl_current['items'][0]
        self.assertEqual(milk_item['sale'], 18.90)
        self.assertEqual(milk_item['original'], 24.90)
        self.assertEqual(milk_item['savings'], 6.00)

    def test_pantry_toggles_echoed(self):
        result = self._compute(basics_on=False, fridge_on=True)
        self.assertEqual(
            result['pantry_toggles'], {'basics_on': False, 'fridge_on': True}
        )

    def test_current_first_then_upcoming_ordering(self):
        result = self._compute()
        statuses = [d['status'] for d in result['deals']]
        # All 'current' entries sort before any 'upcoming' entry.
        if 'current' in statuses and 'upcoming' in statuses:
            self.assertLess(statuses.index('current'), statuses.index('upcoming'))


class ResolveStoreProductsTest(TestCase):
    """The catalog-identity resolution that powers a real cross-store range.

    Regression guard for the bug where compute_pricing matched only by free-text
    ingredient name and so found nothing for catalog-constrained plans (whose
    item names — e.g. "lesní plody" — are not substrings of the scraped product
    name). Items carry a `catalog_id` (= StoreProduct.id); resolution must reach
    every store's product for that item's canonical ingredient.
    """

    def setUp(self):
        from diet_planner.models import (
            CanonicalIngredient, GroceryStore, StoreProduct, PriceRecord,
            PriceSourceType,
        )
        self.StoreProduct = StoreProduct
        now = timezone.now()

        self.canon = CanonicalIngredient.objects.create(name='banana')
        # get_or_create: these stores are seeded by migration 0017.
        lidl, _ = GroceryStore.objects.get_or_create(
            code='LIDL_CZ',
            defaults=dict(name='Lidl', chain='LIDL', country='CZ',
                          currency='CZK', is_active=True))
        rohlik, _ = GroceryStore.objects.get_or_create(
            code='ROHLIK',
            defaults=dict(name='Rohlík', chain='ROHLIK', country='CZ',
                          currency='CZK', is_active=True))

        # Two stores stock the same canonical under DIFFERENT product names that
        # do NOT contain the shopping-list term "banán" — so name matching alone
        # would miss both. Only canonical resolution finds them.
        self.lidl_prod = StoreProduct.objects.create(
            store=lidl, name='Banány Chiquita 1kg', normalized_name='banány chiquita 1kg',
            canonical_ingredient=self.canon, is_active=True)
        self.rohlik_prod = StoreProduct.objects.create(
            store=rohlik, name='Banán volně', normalized_name='banán volně',
            canonical_ingredient=self.canon, is_active=True)
        for sp, price in ((self.lidl_prod, '29.90'), (self.rohlik_prod, '24.90')):
            PriceRecord.objects.create(
                store_product=sp, price=Decimal(price), currency='CZK',
                source_type=PriceSourceType.STORE_REGULAR,
                valid_from=now - dt.timedelta(days=1),
                valid_until=now + dt.timedelta(days=7), scraped_at=now)

    def test_catalog_id_resolves_canonical_across_stores(self):
        from diet_planner.services.shopping_list_pricing import resolve_store_products
        shops = ['LIDL_CZ', 'ROHLIK']
        # The LLM picked the Lidl product (catalog_id); resolution should also
        # pull in the Rohlík product via the shared canonical ingredient.
        ids = resolve_store_products(
            self.lidl_prod.id, None, 'banán', shops, 'CZ')
        self.assertCountEqual(ids, [self.lidl_prod.id, self.rohlik_prod.id])

    def test_range_built_for_catalog_constrained_item(self):
        from diet_planner.services.shopping_list_pricing import compute_pricing
        # Single catalog-constrained item -> a real (cheapest..priciest) range
        # spanning both stores, which the old name-only matching produced as null.
        result = compute_pricing(
            [{'ingredient': 'banán', 'catalog_id': self.lidl_prod.id}],
            country='CZ', currency='CZK')
        pr = result['price_range']
        self.assertIsNotNone(pr)
        self.assertEqual(pr['low'], 24.90)
        self.assertEqual(pr['high'], 29.90)
        self.assertEqual(pr['store_low'], 'ROHLIK')
