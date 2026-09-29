"""
PriceResolver tests: DB-only price resolution, source labeling and unit
conversion.
"""
from django.test import TestCase
from django.contrib.auth.models import User

from diet_planner.models import DietaryGoal, PriceSourceType
from diet_planner.services.price_resolver import PriceResolver, PriceSource
from diet_planner.tests.factories import make_price


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
        # `catalog_id` refers to StoreProduct.id
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
