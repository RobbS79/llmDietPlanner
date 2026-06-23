from django.contrib.auth.models import User
from django.test import TestCase

from diet_planner.models import DietaryGoal, PriceSourceType, Recipe
from diet_planner.serializers import RecipeSerializer
from diet_planner.services.canonical_lookup import clear_cache
from diet_planner.tests.factories import make_canonical, make_price, make_store


class RecipeDealsFieldTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('u1', password='x')
        self.goal = DietaryGoal.objects.create(user=self.user, country='CZ')
        make_store('LIDL_CZ', name='Lidl')
        onion = make_canonical('onion', default_unit='ks', name_cs='cibule')
        clear_cache()
        make_price(store_code='LIDL_CZ', normalized_name='cibule', price='9.90',
                   source_type=PriceSourceType.LEAFLET_DISCOUNT, canonical=onion,
                   source_url='http://lidl.cz/cibule')

    def _recipe(self, ingredients):
        return Recipe.objects.create(
            meal_identifier=f'g{self.goal.id}:0:dinner:0',
            dietary_goal=self.goal, name='Test dish',
            ingredients=ingredients, servings=4,
        )

    def test_deals_present_for_recipe_with_active_deal(self):
        r = self._recipe([{'name': 'cibule', 'canonical': 'onion',
                           'quantity': 1, 'unit': 'ks'}])
        deals = RecipeSerializer(r).data['deals']
        self.assertEqual(deals['matched'], 1)
        self.assertEqual(deals['total'], 1)
        self.assertEqual(deals['deals'][0]['shop'], 'Lidl')

    def test_deals_empty_when_no_match(self):
        r = self._recipe([{'name': 'mystery', 'canonical': 'mystery-xyz',
                           'quantity': 100, 'unit': 'g'}])
        deals = RecipeSerializer(r).data['deals']
        self.assertEqual(deals['matched'], 0)
        self.assertEqual(deals['deals'], [])
