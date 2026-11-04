# diet_planner/tests/test_discover_cards.py
from unittest import mock

from django.test import TestCase

from diet_planner.models import CuratedRecipe
from diet_planner.services.discover_cards import recipe_card, recipe_sheet


def _recipe(**kw):
    d = dict(slug='kureci-wok', name_cs='Kuřecí wok s rýží', meal_types=['dinner'],
             dish_role='main', prep_time=10, cook_time=15, base_servings=2,
             base_nutrition={'calories': 1000, 'protein': 80, 'carbs': 90, 'fat': 30},
             ingredients=[{'name': 'kuřecí prsa', 'canonical': 'chicken-breast', 'quantity': 300, 'unit': 'g'},
                          {'name': 'česnek', 'canonical': 'garlic', 'quantity': 2, 'unit': 'stroužky'}],
             instructions=['Nakrájej maso.', 'Orestuj.', 'Přidej rýži.'],
             source_url='https://example.com/wok', source_name='Toprecepty.cz',
             status=CuratedRecipe.Status.PUBLISHED)
    d.update(kw)
    return CuratedRecipe.objects.create(**d)


DEAL = {'canonical': 'garlic', 'shop': 'Tesco', 'display_name': 'Česnek',
        'source_url': '', 'valid_until': '2026-11-04T05:59:59+00:00'}


class RecipeCardTest(TestCase):
    def test_card_is_per_portion_and_carries_deals(self):
        r = _recipe()
        with mock.patch('diet_planner.services.recipe_deals._ingredient_slug',
                        side_effect=lambda ing, cache=None: ing.get('canonical')):
            card = recipe_card(r, deal_index={'garlic': DEAL}, slug_cache={})
        self.assertEqual(card['id'], r.id)
        self.assertEqual(card['name'], 'Kuřecí wok s rýží')
        self.assertEqual(card['minutes'], 25)
        self.assertEqual(card['kcal'], 500)
        self.assertEqual(card['deals']['matched'], 1)
        self.assertEqual(card['deals']['names'], ['česnek'])
        self.assertEqual(card['image_url'], '/static/food-images/wok.webp')

    def test_missing_nutrition_is_none_not_zero(self):
        r = _recipe(slug='x', base_nutrition={})
        card = recipe_card(r, deal_index={}, slug_cache={})
        self.assertIsNone(card['kcal'])

    def test_sheet_has_macros_steps_and_source(self):
        r = _recipe()
        sheet = recipe_sheet(r, deal_index={}, slug_cache={})
        self.assertEqual(sheet['macros'], {'protein': 40, 'carbs': 45, 'fat': 15})
        self.assertEqual(len(sheet['steps']), 3)
        self.assertEqual(sheet['source'], {'name': 'Toprecepty.cz', 'url': 'https://example.com/wok'})
        self.assertEqual(sheet['ingredients'][0]['name'], 'kuřecí prsa')

    def test_zero_macro_is_real_zero_kcal_zero_is_unknown(self):
        r = _recipe(slug='z', base_nutrition={'calories': 0, 'protein': 20, 'carbs': 0, 'fat': 4})
        sheet = recipe_sheet(r, deal_index={}, slug_cache={})
        self.assertIsNone(sheet['kcal'])
        self.assertEqual(sheet['macros'], {'protein': 10, 'carbs': 0, 'fat': 2})

    def test_missing_or_non_numeric_macro_hides_macros(self):
        for nutrition in ({'calories': 500, 'protein': 20, 'fat': 4},
                          {'calories': 500, 'protein': 20, 'carbs': 'n/a', 'fat': 4},
                          {'calories': 500, 'protein': True, 'carbs': 1, 'fat': 4}):
            r = _recipe(slug=f's{len(str(nutrition))}', base_nutrition=nutrition)
            self.assertIsNone(recipe_sheet(r, deal_index={}, slug_cache={})['macros'], nutrition)
