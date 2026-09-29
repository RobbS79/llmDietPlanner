from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase

from diet_planner.models import DietaryGoal, DietaryPlan
from diet_planner.services.meal_pool import PoolResult
from diet_planner.tasks import generate_meal_pool_task


class GenerateMealPoolTaskTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('t', password='x')
        self.goal = DietaryGoal.objects.create(
            user=self.user, prompt='p', country='CZ', currency='CZK', language_code='cs', dinners=2)

    def _result(self):
        return PoolResult(
            meals=[{'slot': 'dinner', 'index': 0, 'name': 'A', 'meal_identifier': f'{self.goal.id}:dinner:0',
                    'ingredients': [{'name': 'rýže'}], 'source': 'curated'}],
            grounding_debug={'facets': {}, 'coverage': {'filled': 1, 'total': 2}, 'gaps': [],
                             'shortfall': {'dinner': 1}, 'counts': {'dinner': 2}},
            llm_usage={'input_tokens': 5, 'output_tokens': 7, 'total_tokens': 12, 'cost_usd': 0.001, 'model': 'fake'},
        )

    def test_success_stores_meals_and_completes_goal(self):
        with patch('diet_planner.tasks.build_meal_pool', return_value=self._result()), \
             patch('diet_planner.tasks.track_plan_generated') as track:
            out = generate_meal_pool_task.apply(args=(self.goal.id,)).result
        self.assertEqual(out['status'], 'success')
        plan = DietaryPlan.objects.get(dietary_goal=self.goal)
        self.assertEqual(plan.meals[0]['name'], 'A')
        self.assertEqual(plan.days, [])
        self.assertEqual(plan.grounding_debug['shortfall'], {'dinner': 1})
        self.assertEqual(plan.llm_total_tokens, 12)
        self.assertEqual(plan.llm_model_used, 'fake')
        self.assertEqual(plan.llm_cost_usd, Decimal('0.001'))
        self.goal.refresh_from_db()
        self.assertEqual(self.goal.status, DietaryGoal.StatusChoices.COMPLETED)
        self.assertIsNotNone(self.goal.completed_at)
        track.assert_called_once_with(self.user, self.goal.id)

    def test_failure_marks_goal_failed(self):
        with patch('diet_planner.tasks.build_meal_pool', side_effect=ValueError('empty')):
            try:
                generate_meal_pool_task.apply(args=(self.goal.id,), throw=True)
            except Exception:
                pass  # Retry/ValueError propagates under eager execution; the status write is what matters
        self.goal.refresh_from_db()
        self.assertEqual(self.goal.status, DietaryGoal.StatusChoices.FAILED)
        self.assertIn('empty', self.goal.error_message)
