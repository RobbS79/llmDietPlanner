"""Server-rendered /recepty/<pk>/ must not leak internal catalog strings.

Prod QA 2026-08-23: the newest public recipes rendered `pappudia tofu (#2153)`
in the SSR <li> list AND the recipeIngredient JSON-LD (both SEO-visible). The
SSR view and the API serializer share `display_ingredients` so they cannot
drift.
"""
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from diet_planner.models import DietaryGoal, Recipe
from diet_planner.services.canonical_lookup import clear_cache
from diet_planner.tests.factories import make_canonical, make_price, make_store

_TEMPLATE = (
    '<html><head><title>x</title></head><body><!--ssr-outlet--></body></html>'
)


class PublicRecipeSSRIngredientTest(TestCase):
    def setUp(self):
        make_store('LIDL_CZ', name='Lidl')
        tofu = make_canonical('tofu', default_unit='g', name_cs='tofu')
        pr = make_price(store_code='LIDL_CZ', normalized_name='tofu',
                        display_name='Pappudia tofu', price='39.90',
                        canonical=tofu)
        self.sp_id = pr.store_product.id
        clear_cache()
        user = get_user_model().objects.create_user('ssr', password='x')
        goal = DietaryGoal.objects.create(user=user, country='CZ')
        self.recipe = Recipe.objects.create(
            meal_identifier=f'g{goal.id}:1:lunch:0', dietary_goal=goal,
            name='Tofu mísa', servings=1, is_public=True,
            ingredients=[f'pappudia tofu (#{self.sp_id})'],
            instructions=['Uvařte rýži.', 'Přidejte tofu a promíchejte.'],
        )

    def test_ssr_html_shows_clean_name_not_internal_string(self):
        with patch('llm_diet_planner_project.views._get_index_template',
                   return_value=_TEMPLATE):
            resp = self.client.get(self.recipe.get_absolute_url())
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()
        # covers both the <li> list and the recipeIngredient JSON-LD
        self.assertNotIn(f'(#{self.sp_id})', body)
        self.assertNotIn('pappudia', body.lower())
        self.assertIn('tofu', body)
