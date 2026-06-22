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
