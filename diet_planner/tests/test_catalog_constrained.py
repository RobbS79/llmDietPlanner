"""
Smoke tests for the catalog-constrained meal generation flow (Phase 4).

Tests the full chain: catalog preparation → price resolution → source labeling.
LLM call is mocked — everything else is real.
"""
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch, MagicMock

from django.test import TestCase
from django.utils import timezone
from django.contrib.auth.models import User

from diet_planner.models import DietaryGoal, DietaryPlan, GroceryStore, PriceSourceType
from diet_planner.services.catalog import CatalogService, PANTRY_STAPLES
from diet_planner.services.price_resolver import PriceResolver, PriceSource
from diet_planner.tests.factories import make_price


class CatalogServiceTest(TestCase):
    """Test catalog building from LeafletOffer data."""

    def setUp(self):
        self.user = User.objects.create_user('testuser', password='test')
        self.store = GroceryStore.objects.get(code='LIDL_CZ')
        self.goal = DietaryGoal.objects.create(
            user=self.user,
            prompt='Test meal plan',
            country='CZ',
            city='Prague',
            shop='LIDL_CZ',
            num_days=3,
        )
        for name, price in [
            ('kuřecí prsa', 139.90),
            ('rýže basmati', 45.90),
            ('rajčata', 29.90),
            ('jogurt bílý', 18.90),
            ('vejce 10ks M', 64.90),
            ('špenát mražený', 29.90),
            ('olivový olej extra virgin', 89.90),
            ('mléko polotučné', 22.90),
        ]:
            make_price(
                store_code='LIDL_CZ',
                normalized_name=name,
                display_name=name.title(),
                price=price,
                source_type=PriceSourceType.STORE_REGULAR,
            )
        make_price(
            store_code='LIDL_CZ',
            normalized_name='banány',
            display_name='Banány',
            price=19.90,
            source_type=PriceSourceType.LEAFLET_DISCOUNT,
            original_price=29.90,
            discount_percentage=33,
            valid_for_days=3,
        )

    def test_catalog_loads_products(self):
        service = CatalogService()
        catalog = service.build_catalog_for_prompt(self.goal)
        self.assertGreaterEqual(catalog['total_products'], 8)
        self.assertGreater(len(catalog['pantry_staples']), 20)

    def test_catalog_compact_text(self):
        service = CatalogService()
        catalog = service.build_catalog_for_prompt(self.goal)
        text = service.build_compact_prompt_text(catalog, self.goal)
        self.assertIn('#', text)  # catalog IDs
        self.assertIn('PANTRY STAPLES', text)
        self.assertIn('CZK', text)

    def test_dietary_filter_vegetarian(self):
        self.goal.dietary_restrictions = 'vegetarian'
        self.goal.save()
        # build_catalog_for_prompt filters by the resolved restriction set the
        # caller passes in (it no longer reads goal.dietary_restrictions itself).
        from diet_planner.services.restrictions import RestrictionResolver
        exclusions = RestrictionResolver().resolve(self.goal)
        service = CatalogService()
        catalog = service.build_catalog_for_prompt(self.goal, exclusions=exclusions)
        all_names = []
        for products in catalog['products_by_category'].values():
            all_names.extend(p['name'] for p in products)
        self.assertNotIn('kuřecí prsa', all_names)
        self.assertIn('rýže basmati', all_names)

    def test_discounted_items_flagged(self):
        service = CatalogService()
        catalog = service.build_catalog_for_prompt(self.goal)
        all_products = []
        for products in catalog['products_by_category'].values():
            all_products.extend(products)
        discounted = [p for p in all_products if p.get('discounted')]
        self.assertGreater(len(discounted), 0)


class PriceResolverTest(TestCase):
    """Test DB-only price resolution."""

    def setUp(self):
        self.user = User.objects.create_user('testuser2', password='test')
        self.goal = DietaryGoal.objects.create(
            user=self.user,
            prompt='Test',
            country='CZ',
            city='Prague',
            shop='LIDL_CZ',
            num_days=3,
        )
        self.record = make_price(
            store_code='LIDL_CZ',
            normalized_name='kuřecí prsa',
            display_name='Kuřecí prsa bez kosti 1kg',
            price=139.90,
            source_type=PriceSourceType.LEAFLET_DISCOUNT,
            original_price=169.90,
            discount_percentage=18,
            valid_for_days=5,
        )
        # `catalog_id` now refers to StoreProduct.id (see CatalogService._load_products)
        self.catalog_id = self.record.store_product_id
        # Albert offer for cross-store test
        make_price(
            store_code='ALBERT_CZ',
            normalized_name='losos filety',
            display_name='Losos filety 200g',
            price=99.90,
            source_type=PriceSourceType.STORE_REGULAR,
            valid_for_days=5,
        )

    def test_direct_id_match(self):
        resolver = PriceResolver(self.goal)
        items = [{'ingredient': 'kuřecí prsa', 'catalog_id': self.catalog_id, 'quantity': 500, 'unit': 'g'}]
        resolved = resolver.resolve_shopping_list(items)
        self.assertEqual(len(resolved), 1)
        self.assertEqual(resolved[0]['price_source'], PriceSource.LEAFLET_DISCOUNT.value)
        self.assertFalse(resolved[0]['estimated'])
        self.assertIsNotNone(resolved[0]['price_total'])

    def test_name_match(self):
        resolver = PriceResolver(self.goal)
        items = [{'ingredient': 'kuřecí prsa', 'quantity': 300, 'unit': 'g'}]
        resolved = resolver.resolve_shopping_list(items)
        self.assertEqual(resolved[0]['price_source'], PriceSource.LEAFLET_DISCOUNT.value)

    def test_pantry_staple(self):
        resolver = PriceResolver(self.goal)
        items = [{'ingredient': 'sůl', 'quantity': 10, 'unit': 'g', 'pantry': True}]
        resolved = resolver.resolve_shopping_list(items)
        self.assertEqual(resolved[0]['price_source'], PriceSource.PANTRY_ESTIMATE.value)
        self.assertTrue(resolved[0]['estimated'])

    def test_cross_store_fallback(self):
        resolver = PriceResolver(self.goal)
        items = [{'ingredient': 'losos filety', 'quantity': 200, 'unit': 'g'}]
        resolved = resolver.resolve_shopping_list(items)
        self.assertEqual(resolved[0]['price_source'], PriceSource.CROSS_STORE_MATCH.value)
        self.assertEqual(resolved[0]['cross_store'], 'ALBERT_CZ')

    def test_not_available(self):
        resolver = PriceResolver(self.goal)
        items = [{'ingredient': 'unicorn steak', 'quantity': 500, 'unit': 'g'}]
        resolved = resolver.resolve_shopping_list(items)
        self.assertEqual(resolved[0]['price_source'], PriceSource.NOT_AVAILABLE.value)
        self.assertIsNone(resolved[0]['price_total'])

    def test_no_llm_prices(self):
        """The core guarantee: no price comes from LLM estimation."""
        resolver = PriceResolver(self.goal)
        items = [
            {'ingredient': 'kuřecí prsa', 'catalog_id': self.catalog_id, 'quantity': 500, 'unit': 'g'},
            {'ingredient': 'sůl', 'pantry': True, 'quantity': 10, 'unit': 'g'},
            {'ingredient': 'neexistuje', 'quantity': 100, 'unit': 'g'},
        ]
        resolved = resolver.resolve_shopping_list(items)
        for item in resolved:
            self.assertNotEqual(item['price_source'], 'LLM_ESTIMATED')
            self.assertNotIn('llm', item.get('price_source', '').lower())


class PriceResolverUnitConversionTest(TestCase):
    """Regression for prod plan #86: a kg/l-packaged product priced against a
    gram/ml recipe requirement inflated the package count ~1000x (chicken
    breast showed 238,129 CZK). `_calc_packages_needed` must convert the
    requirement and the package size to a common base unit before dividing,
    and must never produce a runaway package count across mismatched units.
    """

    def setUp(self):
        self.user = User.objects.create_user('uconv', password='test')
        self.goal = DietaryGoal.objects.create(
            user=self.user, prompt='t', country='CZ', city='Prague',
            shop='LIDL_CZ', num_days=7,
        )

    def test_kg_product_gram_requirement_no_inflation(self):
        rec = make_price(
            store_code='LIDL_CZ', normalized_name='kuřecí prsa',
            display_name='Farma rodiny Němcovy Kuřecí prsa', price=227.44,
            source_type=PriceSourceType.STORE_REGULAR,
            package_size=0.65, package_unit='kg',
        )
        r = PriceResolver(self.goal).resolve_shopping_list(
            [{'ingredient': 'kuřecí prsa', 'catalog_id': rec.store_product_id,
              'quantity': 680, 'unit': 'g'}]
        )[0]
        # 680 g needs ceil(680 / 650) = 2 packs of 0.65 kg, not 1047.
        self.assertEqual(r['packages_needed'], 2)
        self.assertAlmostEqual(r['price_total'], 454.88, places=2)

    def test_litre_product_millilitre_requirement(self):
        rec = make_price(
            store_code='LIDL_CZ', normalized_name='mléko',
            display_name='Mléko 1 l', price=23.90,
            source_type=PriceSourceType.STORE_REGULAR,
            package_size=1.0, package_unit='l',
        )
        r = PriceResolver(self.goal).resolve_shopping_list(
            [{'ingredient': 'mléko', 'catalog_id': rec.store_product_id,
              'quantity': 500, 'unit': 'ml'}]
        )[0]
        self.assertEqual(r['packages_needed'], 1)
        self.assertAlmostEqual(r['price_total'], 23.90, places=2)

    def test_same_unit_grams_unchanged(self):
        rec = make_price(
            store_code='LIDL_CZ', normalized_name='rýže',
            display_name='Rýže 500 g', price=30.0,
            source_type=PriceSourceType.STORE_REGULAR,
            package_size=500, package_unit='g',
        )
        r = PriceResolver(self.goal).resolve_shopping_list(
            [{'ingredient': 'rýže', 'catalog_id': rec.store_product_id,
              'quantity': 800, 'unit': 'g'}]
        )[0]
        self.assertEqual(r['packages_needed'], 2)  # ceil(800 / 500)
        self.assertAlmostEqual(r['price_total'], 60.0, places=2)

    def test_mixed_dimension_falls_back_to_one_package(self):
        # Recipe asks grams; product sold per piece. Without per-piece weights
        # we can't convert, so assume one package rather than fabricate a count.
        rec = make_price(
            store_code='LIDL_CZ', normalized_name='avokádo',
            display_name='Avokádo', price=29.90,
            source_type=PriceSourceType.STORE_REGULAR,
            package_size=1, package_unit='ks',
        )
        r = PriceResolver(self.goal).resolve_shopping_list(
            [{'ingredient': 'avokádo', 'catalog_id': rec.store_product_id,
              'quantity': 200, 'unit': 'g'}]
        )[0]
        self.assertEqual(r['packages_needed'], 1)
        self.assertAlmostEqual(r['price_total'], 29.90, places=2)


class RecomputePlanPricesCommandTest(TestCase):
    """The recompute_plan_prices command re-prices a stored plan in place
    (no LLM, same meals) from the static price book, so plans stored with old
    (inflated) numbers get healed instead of requiring full regeneration."""

    def setUp(self):
        from diet_planner.services.canonical_lookup import clear_cache
        from diet_planner.tests.factories import make_canonical

        self.user = User.objects.create_user('recompute', password='test')
        self.goal = DietaryGoal.objects.create(
            user=self.user, prompt='t', country='CZ', city='Prague',
            shop='ROHLIK', num_days=7, currency='CZK',
        )
        # Canonical with the book's slug ('chicken-breast') and a Czech name so
        # resolve_canonical('kuřecí prsa') maps to the book entry.
        make_canonical('chicken breast', name_cs='kuřecí prsa',
                       is_pantry_staple=False, default_unit='g')
        clear_cache()
        # Pro-rated cost from the real book: 680 g consumed × price per g.
        from diet_planner.services.estimate_pricer import _load_book
        e = _load_book()['prices']['chicken-breast']
        self.expected = round(680 * e['price_per_unit'], 2)

    def _make_plan(self):
        return DietaryPlan.objects.create(
            dietary_goal=self.goal,
            days=[],
            shopping_list=[{
                'ingredient': 'kuřecí prsa', 'quantity': 680, 'unit': 'g',
                'price_total': 238129.68, 'price': 227.44,
            }],
            total_price=Decimal('238129.68'),
            currency='CZK',
        )

    def test_command_reprices_plan_in_place(self):
        from django.core.management import call_command
        from io import StringIO

        plan = self._make_plan()
        call_command('recompute_plan_prices', stdout=StringIO())

        plan.refresh_from_db()
        self.assertAlmostEqual(float(plan.total_price), self.expected, places=2)
        item = plan.shopping_list[0]
        self.assertAlmostEqual(item['price_total'], self.expected, places=2)
        self.assertEqual(item['price_source'], 'estimate')
        self.assertEqual(item['ingredient'], 'kuřecí prsa')  # meals untouched

    def test_dry_run_leaves_plan_unchanged(self):
        from django.core.management import call_command
        from io import StringIO

        plan = self._make_plan()
        call_command('recompute_plan_prices', '--dry-run', stdout=StringIO())

        plan.refresh_from_db()
        self.assertEqual(plan.total_price, Decimal('238129.68'))
