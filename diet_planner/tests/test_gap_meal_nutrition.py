"""Gap-fill (Gemini) meals: nutrition computed from the table when every line
converts, else Gemini's numbers kept and labelled estimated."""
from unittest.mock import MagicMock, patch

from django.contrib.auth.models import User
from django.test import TestCase

from diet_planner.models import DietaryGoal
from diet_planner.services import recipe_curation
from diet_planner.services.meal_pool import build_meal_pool, stamp_generated_nutrition
from diet_planner.services.nutrition_lookups import nutrition_table
from diet_planner.services.prompt_facets import PromptFacets
from diet_planner.tests.factories import make_canonical


def _chicken():
    make_canonical('Chicken breast', name_cs='kuřecí prsa', kcal_per_100g=165,
                   protein_per_100g=31, carbs_per_100g=0, fat_per_100g=3.6)
    recipe_curation.clear_resolver_cache()


class StampTest(TestCase):
    def setUp(self):
        _chicken()

    def test_resolvable_meal_is_computed(self):
        meal = {'name': 'Kuře', 'servings': 1,
                'ingredients': [{'name': 'kuřecí prsa', 'quantity': 200, 'unit': 'g'}],
                'nutritional_info': {'calories': 999, 'protein': '1g'}}
        stamp_generated_nutrition(meal, nutrition_table())
        self.assertEqual(meal['nutritional_info'], {'calories': 330, 'protein': '62g', 'carbs': '0g', 'fat': '7g',
                                                    'basis': 'total', 'servings': 1, 'nutrition_source': 'computed'})
        self.assertEqual(meal['ingredients'][0]['canonical'], 'chicken-breast')

    def test_unresolvable_meal_keeps_gemini_numbers_as_estimate(self):
        meal = {'name': 'X', 'servings': 1,
                'ingredients': [{'name': 'dračí ovoce', 'quantity': 100, 'unit': 'g'}],
                'nutritional_info': {'calories': 120, 'protein': '2g'}}
        stamp_generated_nutrition(meal, nutrition_table())
        self.assertEqual(meal['nutritional_info']['calories'], 120)
        self.assertEqual(meal['nutritional_info']['nutrition_source'], 'estimated')
        self.assertEqual(meal['nutritional_info']['basis'], 'total')

    def test_only_to_taste_lines_is_not_a_computation(self):
        meal = {'name': 'Y', 'servings': 1,
                'ingredients': [{'name': 'kuřecí prsa'}],
                'nutritional_info': {'calories': 300}}
        stamp_generated_nutrition(meal, nutrition_table())
        self.assertEqual((meal['nutritional_info']['calories'],
                          meal['nutritional_info']['nutrition_source']), (300, 'estimated'))


class PoolIntegrationTest(TestCase):
    def test_gap_meal_from_pool_is_stamped(self):
        user = User.objects.create_user('p', password='x')
        _chicken()
        goal = DietaryGoal.objects.create(user=user, prompt='x', country='CZ',
                                          language_code='cs', dinners=1)
        llm = MagicMock()
        llm.generate_slot_meal.return_value = {
            'meal': {'name': 'Kuře', 'ingredients': [{'name': 'kuřecí prsa', 'quantity': 200, 'unit': 'g'}],
                     'nutritional_info': {'calories': 999}},
            'input_tokens': 1, 'output_tokens': 1, 'total_tokens': 2, 'cost_usd': 0, 'model': 'f'}
        with patch('diet_planner.services.meal_pool.extract_prompt_facets', return_value=PromptFacets()):
            result = build_meal_pool(goal, llm=llm)
        generated = [m for m in result.meals if m['source'] == 'generated']
        self.assertTrue(generated)
        ni = generated[0]['nutritional_info']
        self.assertEqual((ni['calories'], ni['nutrition_source']), (330, 'computed'))
