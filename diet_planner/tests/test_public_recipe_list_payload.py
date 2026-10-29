"""Public list payload: only what the /recepty cards render.

The list used the full RecipeSerializer, pricing every row (price_range,
shopping_list) and rebuilding the deal index per recipe — 9-11 s per page on
prod (QA 2026-10-29). The cards show name, photo, description, time, servings
and the deals badge; nothing else.
"""
from unittest import mock

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from diet_planner.models import DietaryGoal, Recipe

INSTRUCTIONS = [
    'Nakrájejte kuřecí prsa na plátky a osolte je ze všech stran.',
    'Obalte je ve strouhance a smažte dozlatova, poté zapečte se sýrem.',
    'Podávejte s rajčatovou omáčkou a čerstvou bazalkou navrchu.',
]


class PublicRecipeListPayloadTest(TestCase):
    def setUp(self):
        user = get_user_model().objects.create(username='chef')
        self.goal = DietaryGoal.objects.create(
            user=user, prompt='týden jídel', num_days=1,
            country='CZ', currency='CZK', language_code='cs',
        )
        self.client = APIClient()

    def _recipes(self, n):
        start = Recipe.objects.count()
        for i in range(start, start + n):
            Recipe.objects.create(
                meal_identifier=f'g:{i}:lunch:0', dietary_goal=self.goal,
                name=f'Recept {i}', servings=4, instructions=INSTRUCTIONS,
                preparation_time=20,
                ingredients=[{'name': 'kuřecí prsa', 'quantity': 400, 'unit': 'g'}],
            )

    def _rows(self):
        resp = self.client.get('/api/recipes/public/')
        self.assertEqual(resp.status_code, 200)
        return resp.data['data']['results']

    def test_rows_carry_card_fields_and_deals_but_no_pricing(self):
        self._recipes(1)
        row = self._rows()[0]
        for field in ('id', 'slug', 'name', 'description', 'food_category',
                      'image_url', 'preparation_time', 'servings', 'deals'):
            self.assertIn(field, row)
        for field in ('price_range', 'shopping_list', 'instructions', 'ingredients'):
            self.assertNotIn(field, row)

    def test_list_does_not_price_recipes(self):
        self._recipes(2)
        with mock.patch('diet_planner.serializers.build_price_range', return_value=None) as pr, \
                mock.patch('diet_planner.serializers.build_shopping_list', return_value=None) as sl:
            self._rows()
        pr.assert_not_called()
        sl.assert_not_called()

    def test_deal_index_built_once_per_page(self):
        self._recipes(5)
        with mock.patch('diet_planner.services.recipe_deals.active_deal_index',
                        return_value={}) as idx:
            self._rows()
        self.assertEqual(idx.call_count, 1)

    def test_query_count_does_not_grow_with_rows(self):
        self._recipes(2)
        with CaptureQueriesContext(connection) as few:
            self._rows()
        self._recipes(10)
        with CaptureQueriesContext(connection) as many:
            self._rows()
        self.assertEqual(len(few), len(many))

    def test_ingredient_lookups_shared_across_rows_when_deals_exist(self):
        deal = {'canonical': 'x', 'shop': 'Lidl', 'display_name': 'X',
                'source_url': '', 'valid_until': '2026-11-01T00:00:00'}
        with mock.patch('diet_planner.services.recipe_deals.active_deal_index',
                        return_value={'x': deal}):
            self._recipes(2)
            self._rows()  # warm resolve_canonical's per-process normalized index
            with CaptureQueriesContext(connection) as few:
                self._rows()
            self._recipes(10)
            with CaptureQueriesContext(connection) as many:
                self._rows()
        self.assertEqual(len(few), len(many))

    def test_deals_badge_still_matches(self):
        Recipe.objects.create(
            meal_identifier='g:deal:lunch:0', dietary_goal=self.goal,
            name='Losos', servings=2, instructions=INSTRUCTIONS,
            ingredients=[{'name': 'losos', 'canonical': 'salmon', 'quantity': 300, 'unit': 'g'},
                         {'name': 'sůl', 'quantity': 1, 'unit': 'g'}],
        )
        deal = {'canonical': 'salmon', 'shop': 'Lidl', 'display_name': 'Losos',
                'source_url': '', 'valid_until': '2026-11-01T00:00:00'}
        with mock.patch('diet_planner.services.recipe_deals.active_deal_index',
                        return_value={'salmon': deal}):
            row = self._rows()[0]
        self.assertEqual(row['deals']['matched'], 1)
        self.assertEqual(row['deals']['total'], 2)
