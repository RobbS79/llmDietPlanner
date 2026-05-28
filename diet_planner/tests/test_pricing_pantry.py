"""
Tests for pantry-staple pro-rated pricing and canonical ingredient lookup.

Covers:
- calculate_package_aware_price(is_staple=True) returns raw fraction × price
- calculate_package_aware_price(is_staple=False) keeps the ceil-to-whole-package behavior
- resolve_canonical matches by EN/CS/SK name and IngredientAlias, case-insensitive
"""
from decimal import Decimal

from django.test import TestCase

from diet_planner.tasks import calculate_package_aware_price
from diet_planner.services.canonical_lookup import resolve_canonical


class CalculatePackageAwarePriceTest(TestCase):
    """Unit tests for the pricing function — no DB, no LLM, just math."""

    def _item(self, **overrides):
        base = {
            'ingredient': 'olive oil',
            'quantity': 10,
            'unit': 'ml',
            'price': 150,
            'product_unit': 'ml',
            'package_size': 500,
            'currency': 'CZK',
        }
        base.update(overrides)
        return base

    def test_grocery_rounds_up_to_whole_packages(self):
        # Need 400g, package is 500g at 39 CZK → 1 package × 39 = 39 CZK
        item = self._item(ingredient='chicken', quantity=400, unit='g', price=39, product_unit='g', package_size=500)
        price = calculate_package_aware_price(item)
        self.assertEqual(price, Decimal('39'))

    def test_grocery_buys_multiple_packages(self):
        # Need 800g, package is 500g at 39 CZK → 2 packages × 39 = 78 CZK
        item = self._item(ingredient='chicken', quantity=800, unit='g', price=39, product_unit='g', package_size=500)
        price = calculate_package_aware_price(item)
        self.assertEqual(price, Decimal('78'))

    def test_staple_prorates_by_fraction(self):
        # Need 10ml of a 500ml bottle at 150 CZK → 10/500 × 150 = 3 CZK
        item = self._item()
        price = calculate_package_aware_price(item, is_staple=True)
        self.assertEqual(price, Decimal('3'))

    def test_staple_populates_pantry_display_fields(self):
        item = self._item(quantity=25, unit='ml', price=150, package_size=500)
        calculate_package_aware_price(item, is_staple=True)
        self.assertEqual(item['fraction_used'], 0.05)
        self.assertEqual(item['pantry_pack_price'], 150.0)
        self.assertEqual(item['pantry_package_size'], 500.0)
        self.assertEqual(item['pantry_package_unit'], 'ml')

    def test_staple_handles_tiny_fraction(self):
        # 1g salt of a 500g bag at 10 CZK → 1/500 × 10 = 0.02 CZK
        item = self._item(ingredient='salt', quantity=1, unit='g', price=10, product_unit='g', package_size=500)
        price = calculate_package_aware_price(item, is_staple=True)
        self.assertEqual(price, Decimal('0.02'))

    def test_staple_default_is_false(self):
        # Without is_staple=True, behavior matches grocery (rounds up)
        item = self._item()
        price = calculate_package_aware_price(item)  # default is_staple=False
        # 10ml of 500ml bottle → ceil(10/500) = 1 package × 150 = 150
        self.assertEqual(price, Decimal('150'))

    def test_unit_conversion_kg_to_g(self):
        # Need 1.2kg, product is 1kg pack at 89.90 → 2 packages × 89.90 = 179.80
        item = self._item(ingredient='flour', quantity=1.2, unit='kg', price=89.90, product_unit='kg', package_size=1)
        price = calculate_package_aware_price(item)
        self.assertEqual(price, Decimal('179.80'))


class ResolveCanonicalTest(TestCase):
    """Tests that name matching finds the seeded pantry staples."""

    def test_match_by_english_name(self):
        ci = resolve_canonical('Olive oil')
        self.assertIsNotNone(ci)
        self.assertTrue(ci.is_pantry_staple)
        self.assertEqual(ci.slug, 'olive-oil')

    def test_match_by_czech_name(self):
        ci = resolve_canonical('Sójová omáčka')
        self.assertIsNotNone(ci)
        self.assertTrue(ci.is_pantry_staple)

    def test_match_by_slovak_name(self):
        ci = resolve_canonical('Mletá rasca')
        self.assertIsNotNone(ci)
        self.assertEqual(ci.slug, 'cumin')

    def test_match_case_insensitive(self):
        self.assertIsNotNone(resolve_canonical('OLIVE OIL'))
        self.assertIsNotNone(resolve_canonical('olive oil'))
        self.assertIsNotNone(resolve_canonical('Olive Oil'))

    def test_match_via_alias(self):
        # 'salt' is an alias for 'Table salt'
        ci = resolve_canonical('salt')
        self.assertIsNotNone(ci)
        self.assertEqual(ci.slug, 'table-salt')

    def test_match_via_czech_alias(self):
        # 'sůl' is a cs alias for table salt
        ci = resolve_canonical('sůl')
        self.assertIsNotNone(ci)
        self.assertEqual(ci.slug, 'table-salt')

    def test_unknown_returns_none(self):
        self.assertIsNone(resolve_canonical('chicken breast'))
        self.assertIsNone(resolve_canonical(''))
        self.assertIsNone(resolve_canonical('   '))
        self.assertIsNone(resolve_canonical(None))

    def test_whitespace_is_stripped(self):
        self.assertIsNotNone(resolve_canonical('  Olive oil  '))
