"""build_meal_pool: corpus first, Gemini for gaps, shortfall when Gemini fails."""
from unittest.mock import MagicMock, patch

from django.contrib.auth.models import User
from django.test import TestCase

from diet_planner.models import CuratedRecipe, DietaryGoal
from diet_planner.services.meal_pool import build_meal_pool
from diet_planner.services.prompt_facets import PromptFacets
from diet_planner.services.restrictions import RepairBudgetExhausted
from diet_planner.tests.test_recipe_replace import make_recipe


def _llm(meals=None, fail=False):
    llm = MagicMock()
    if fail:
        llm.generate_slot_meal.side_effect = RuntimeError('gemini down')
    else:
        queue = list(meals or [])

        def _gen(**kw):
            m = queue.pop(0) if queue else {'name': f"LLM {kw['slot']}", 'ingredients': [{'name': 'rýže'}],
                                            'nutritional_info': {'calories': 400}}
            return {'meal': m, 'input_tokens': 5, 'output_tokens': 7, 'total_tokens': 12,
                    'cost_usd': 0.001, 'model': 'fake'}
        llm.generate_slot_meal.side_effect = _gen
    return llm


class BuildMealPoolTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('pool', password='x')
        for i in range(3):
            make_recipe(name_cs=f'Večeře {i}', meal_types=['dinner'], dish_role='main', dish_family=f'f{i}')
        self.facets_patch = patch('diet_planner.services.meal_pool.extract_prompt_facets',
                                  return_value=PromptFacets())
        self.facets_patch.start()
        self.addCleanup(self.facets_patch.stop)

    def _goal(self, **counts):
        return DietaryGoal.objects.create(user=self.user, prompt='večeře', country='CZ',
                                          language_code='cs', **counts)

    def test_all_from_corpus_when_it_covers(self):
        goal = self._goal(dinners=3)
        result = build_meal_pool(goal, llm=_llm())
        self.assertEqual(len(result.meals), 3)
        self.assertTrue(all(m['source'] == 'curated' for m in result.meals))
        self.assertEqual([m['meal_identifier'] for m in result.meals],
                         [f'{goal.id}:dinner:{i}' for i in range(3)])
        self.assertEqual([(m['slot'], m['index']) for m in result.meals],
                         [('dinner', 0), ('dinner', 1), ('dinner', 2)])
        self.assertEqual(result.grounding_debug['coverage'], {'filled': 3, 'total': 3})
        self.assertEqual(result.grounding_debug['shortfall'], {})
        self.assertEqual(result.llm_usage['total_tokens'], 0)
        self.assertEqual(CuratedRecipe.objects.filter(usage_count=1).count(), 3)

    def test_gaps_are_filled_by_llm_and_marked_generated(self):
        goal = self._goal(dinners=3, breakfasts=2)
        result = build_meal_pool(goal, llm=_llm())
        bfs = [m for m in result.meals if m['slot'] == 'breakfast']
        self.assertEqual(len(bfs), 2)
        self.assertTrue(all(m['source'] == 'generated' for m in bfs))
        self.assertEqual([m['meal_identifier'] for m in bfs],
                         [f'{goal.id}:breakfast:0', f'{goal.id}:breakfast:1'])
        self.assertEqual(result.llm_usage['total_tokens'], 24)
        self.assertEqual(result.grounding_debug['shortfall'], {})

    def test_llm_failure_becomes_shortfall_not_crash(self):
        goal = self._goal(dinners=3, breakfasts=2)
        result = build_meal_pool(goal, llm=_llm(fail=True))
        self.assertEqual(len(result.meals), 3)
        self.assertEqual(result.grounding_debug['shortfall'], {'breakfast': 2})

    def test_repair_budget_exhausted_counts_as_shortfall(self):
        goal = self._goal(breakfasts=1)
        with patch('diet_planner.services.meal_pool.repair_single_meal',
                   side_effect=RepairBudgetExhausted('x', meal_key='breakfast:0', violations=[])):
            with self.assertRaises(ValueError):
                build_meal_pool(goal, llm=_llm())   # only position is short → empty pool → refused

    def test_repair_budget_exhausted_is_shortfall_when_others_exist(self):
        goal = self._goal(dinners=1, breakfasts=1)
        with patch('diet_planner.services.meal_pool.repair_single_meal',
                   side_effect=RepairBudgetExhausted('x', meal_key='breakfast:0', violations=[])):
            result = build_meal_pool(goal, llm=_llm())
        self.assertEqual([m['slot'] for m in result.meals], ['dinner'])
        self.assertEqual(result.grounding_debug['shortfall'], {'breakfast': 1})

    def test_empty_pool_raises(self):
        goal = self._goal(breakfasts=1)
        with self.assertRaises(ValueError):
            build_meal_pool(goal, llm=_llm(fail=True))

    def test_suspect_facets_route_mains_to_llm(self):
        goal = self._goal(dinners=2, snacks=1)
        make_recipe(name_cs='Jablko', meal_types=['snack'], dish_role='')
        with patch('diet_planner.services.meal_pool.extract_prompt_facets',
                   return_value=PromptFacets(suspect=True)):
            result = build_meal_pool(goal, llm=_llm())
        by_slot = {}
        for m in result.meals:
            by_slot.setdefault(m['slot'], []).append(m['source'])
        self.assertEqual(by_slot['dinner'], ['generated', 'generated'])
        self.assertEqual(by_slot['snack'], ['curated'])

    def test_meals_are_ordered_by_slot_then_index(self):
        goal = self._goal(dinners=1, breakfasts=1, snacks=1)
        result = build_meal_pool(goal, llm=_llm())
        self.assertEqual([m['slot'] for m in result.meals], ['breakfast', 'dinner', 'snack'])

    def test_repair_uses_slot_aware_regenerate_and_counts_usage(self):
        goal = self._goal(breakfasts=1)
        captured = {}

        def fake_repair(meal, *, goal, exclusions, llm, meal_key, regenerate=None, **kw):
            captured['regenerate'] = regenerate
            fixed = regenerate(meal)            # one slot-aware re-prompt
            return fixed, 1, 0
        llm = _llm()
        with patch('diet_planner.services.meal_pool.repair_single_meal', side_effect=fake_repair):
            result = build_meal_pool(goal, llm=llm)
        self.assertIsNotNone(captured['regenerate'])
        self.assertEqual(llm.generate_slot_meal.call_count, 2)
        self.assertEqual(result.llm_usage['total_tokens'], 24)
        self.assertEqual(result.meals[0]['source'], 'generated')
