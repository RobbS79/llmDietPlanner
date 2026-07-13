from django.contrib.auth.models import User
from django.test import TestCase

from diet_planner.models import DietaryGoal, Recipe
from diet_planner.serializers import RecipeSerializer


class RecipePriceRangeFieldTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('u1', password='x')
        # country drives currency; CZ -> CZK, matching the price book.
        self.goal = DietaryGoal.objects.create(user=self.user, country='CZ')

    def _recipe(self, ingredients, servings=4):
        return Recipe.objects.create(
            meal_identifier=f'g{self.goal.id}:0:dinner:0',
            dietary_goal=self.goal, name='Test dish',
            ingredients=ingredients, servings=servings,
        )

    def test_price_range_present_for_priceable_recipe(self):
        # canonicals known to exist in the real book
        r = self._recipe([
            {'name': 'kuřecí prsa', 'canonical': 'chicken-breast', 'quantity': 600, 'unit': 'g'},
            {'name': 'rýže', 'canonical': 'rice-jasmine', 'quantity': 320, 'unit': 'g'},
        ])
        pr = RecipeSerializer(r).data['price_range']
        self.assertIsNotNone(pr)
        self.assertLess(pr['low'], pr['high'])               # range opens upward
        self.assertEqual(pr['currency'], 'CZK')
        self.assertTrue(pr['confident'])
        self.assertIsNotNone(pr['per_portion_low'])
        # per-portion is the total divided by servings
        self.assertAlmostEqual(pr['per_portion_low'], pr['low'] / 4, places=2)

    def test_price_range_null_when_nothing_prices(self):
        r = self._recipe([{'name': 'mystery', 'canonical': 'mystery-xyz',
                           'quantity': 100, 'unit': 'g'}])
        self.assertIsNone(RecipeSerializer(r).data['price_range'])

    def test_price_range_null_for_empty_ingredients(self):
        r = self._recipe([])
        self.assertIsNone(RecipeSerializer(r).data['price_range'])

    def test_price_range_exposes_priced_and_total_counts(self):
        r = self._recipe([
            {'name': 'kuřecí prsa', 'canonical': 'chicken-breast', 'quantity': 600, 'unit': 'g'},
            {'name': 'mystery', 'canonical': 'mystery-xyz', 'quantity': 100, 'unit': 'g'},
        ])
        pr = RecipeSerializer(r).data['price_range']
        self.assertEqual(pr['priced_count'], 1)
        self.assertEqual(pr['total_count'], 2)


class RecipeShoppingListFieldTest(TestCase):
    """Component 2: per-line priced shopping list. See
    docs/superpowers/specs/2026-07-13-per-recipe-priced-shopping-list-design.md."""

    def setUp(self):
        self.user = User.objects.create_user('u2', password='x')
        self.goal = DietaryGoal.objects.create(user=self.user, country='CZ')

    def _recipe(self, ingredients, servings=4, meal='dinner', idx=0):
        return Recipe.objects.create(
            meal_identifier=f'g{self.goal.id}:0:{meal}:{idx}',
            dietary_goal=self.goal, name='Test dish',
            ingredients=ingredients, servings=servings,
        )

    def test_shopping_list_per_line_shape(self):
        # 'apples' is a verified (ČSÚ-anchored) canonical; 'chicken-breast'
        # is priced but currently an estimate (verified: false) in the book.
        r = self._recipe([
            {'name': 'jablka', 'canonical': 'apples', 'quantity': 300, 'unit': 'g'},
            {'name': 'kuřecí prsa', 'canonical': 'chicken-breast', 'quantity': 600, 'unit': 'g'},
        ])
        sl = RecipeSerializer(r).data['shopping_list']
        self.assertIsNotNone(sl)
        self.assertEqual(len(sl['lines']), 2)

        apples_line = next(l for l in sl['lines'] if l['canonical'] == 'apples')
        self.assertTrue(apples_line['priced'])
        self.assertTrue(apples_line['verified'])
        self.assertIsInstance(apples_line['consumed_cost'], float)

        chicken_line = next(l for l in sl['lines'] if l['canonical'] == 'chicken-breast')
        self.assertTrue(chicken_line['priced'])
        self.assertFalse(chicken_line['verified'])
        self.assertIsInstance(chicken_line['consumed_cost'], float)

        self.assertEqual(sl['priced_count'], 2)
        self.assertEqual(sl['total_count'], 2)
        self.assertEqual(sl['verified_count'], 1)
        self.assertEqual(sl['currency'], 'CZK')

    def test_unpriced_ingredient_yields_priced_false_never_a_fabricated_cost(self):
        r = self._recipe([
            {'name': 'jablka', 'canonical': 'apples', 'quantity': 300, 'unit': 'g'},
            {'name': 'mystery', 'canonical': 'mystery-xyz', 'quantity': 100, 'unit': 'g'},
        ])
        sl = RecipeSerializer(r).data['shopping_list']
        mystery_line = next(l for l in sl['lines'] if l['canonical'] == 'mystery-xyz')
        self.assertFalse(mystery_line['priced'])
        self.assertIsNone(mystery_line['consumed_cost'])
        self.assertFalse(mystery_line['verified'])
        self.assertEqual(sl['priced_count'], 1)
        self.assertEqual(sl['total_count'], 2)

    def test_totals_reflect_only_priced_lines(self):
        r = self._recipe([
            {'name': 'jablka', 'canonical': 'apples', 'quantity': 300, 'unit': 'g'},
            {'name': 'mystery', 'canonical': 'mystery-xyz', 'quantity': 100, 'unit': 'g'},
        ], meal='dinner', idx=0)
        sl = RecipeSerializer(r).data['shopping_list']
        apples_only = RecipeSerializer(self._recipe([
            {'name': 'jablka', 'canonical': 'apples', 'quantity': 300, 'unit': 'g'},
        ], meal='lunch', idx=0)).data['shopping_list']
        # The mystery line contributes nothing to the total — same low/high
        # whether it's present (unpriced) or absent entirely.
        self.assertAlmostEqual(sl['total_low'], apples_only['total_low'], places=2)
        self.assertAlmostEqual(sl['total_high'], apples_only['total_high'], places=2)

    def test_shopping_list_null_for_empty_ingredients(self):
        r = self._recipe([])
        self.assertIsNone(RecipeSerializer(r).data['shopping_list'])

    def test_optional_ingredient_excluded_from_lines(self):
        r = self._recipe([
            {'name': 'jablka', 'canonical': 'apples', 'quantity': 300, 'unit': 'g'},
            {'name': 'sůl', 'canonical': 'salt', 'quantity': 5, 'unit': 'g', 'optional': True},
        ])
        sl = RecipeSerializer(r).data['shopping_list']
        self.assertEqual(len(sl['lines']), 1)
        self.assertEqual(sl['total_count'], 1)
