from decimal import Decimal
from unittest.mock import patch

from billiard.exceptions import SoftTimeLimitExceeded
from celery.exceptions import Retry
from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient

from diet_planner.models import DietaryGoal, DietaryPlan
from diet_planner.services.meal_pool import PoolResult
from diet_planner.tasks import generate_meal_pool_task
from login_app.models import UserProfile


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

    def _run(self):
        return generate_meal_pool_task.apply(args=(self.goal.id,), throw=True).result

    def test_success_stores_meals_and_completes_goal(self):
        with patch('diet_planner.tasks.build_meal_pool', return_value=self._result()), \
             patch('diet_planner.tasks.track_plan_generated') as track:
            out = self._run()
        self.assertEqual(out['status'], 'success')
        plan = DietaryPlan.objects.get(dietary_goal=self.goal)
        self.assertEqual(out['plan_id'], plan.id)
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

    def test_processing_is_set_before_build(self):
        seen = {}

        def _build(goal, **kw):
            seen['status'] = DietaryGoal.objects.get(id=goal.id).status
            return self._result()

        with patch('diet_planner.tasks.build_meal_pool', side_effect=_build), \
             patch('diet_planner.tasks.track_plan_generated'):
            self._run()
        self.assertEqual(seen['status'], DietaryGoal.StatusChoices.PROCESSING)

    def test_transient_failure_marks_failed_and_retries(self):
        with patch('diet_planner.tasks.build_meal_pool', side_effect=RuntimeError('boom')) as build:
            with self.assertRaises(Retry):
                self._run()
        self.assertEqual(build.call_count, 1)
        self.goal.refresh_from_db()
        self.assertEqual(self.goal.status, DietaryGoal.StatusChoices.FAILED)
        self.assertIn('boom', self.goal.error_message)

    def test_empty_pool_is_terminal(self):
        with patch('diet_planner.tasks.build_meal_pool', side_effect=ValueError('empty')) as build:
            out = self._run()
        self.assertEqual(out, {'status': 'failed', 'reason': 'empty_pool'})
        self.assertEqual(build.call_count, 1)
        self.goal.refresh_from_db()
        self.assertEqual(self.goal.status, DietaryGoal.StatusChoices.FAILED)
        self.assertIn('empty', self.goal.error_message)

    def test_soft_time_limit_is_terminal(self):
        with patch('diet_planner.tasks.build_meal_pool', side_effect=SoftTimeLimitExceeded()) as build:
            out = self._run()
        self.assertEqual(out, {'status': 'failed', 'reason': 'soft_time_limit'})
        self.assertEqual(build.call_count, 1)
        self.goal.refresh_from_db()
        self.assertEqual(self.goal.status, DietaryGoal.StatusChoices.FAILED)

    def test_existing_plan_is_idempotent(self):
        plan = DietaryPlan.objects.create(dietary_goal=self.goal, meals=[], days=[], currency='CZK')
        with patch('diet_planner.tasks.build_meal_pool') as build:
            out = self._run()
        build.assert_not_called()
        self.assertEqual(out, {'status': 'success', 'plan_id': plan.id})
        self.assertEqual(DietaryPlan.objects.filter(dietary_goal=self.goal).count(), 1)
        self.goal.refresh_from_db()
        self.assertEqual(self.goal.status, DietaryGoal.StatusChoices.COMPLETED)
        self.assertIsNotNone(self.goal.completed_at)

    def test_legacy_goal_is_terminal(self):
        legacy = DietaryGoal.objects.create(user=self.user, prompt='p', country='CZ', num_days=3)
        self.assertFalse(any(legacy.pool_counts().values()))
        with patch('diet_planner.tasks.build_meal_pool') as build:
            out = generate_meal_pool_task.apply(args=(legacy.id,), throw=True).result
        build.assert_not_called()
        self.assertEqual(out, {'status': 'failed', 'reason': 'legacy_goal'})
        legacy.refresh_from_db()
        self.assertEqual(legacy.status, DietaryGoal.StatusChoices.FAILED)
        self.assertIn('predates the meal pool', legacy.error_message)


class AdminRetryGuardsTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('owner', password='x')
        profile, _ = UserProfile.objects.get_or_create(user=self.user)
        profile.email_verified = True
        profile.save(update_fields=['email_verified'])
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def _retry(self, goal):
        return self.client.post(f'/api/goals/{goal.id}/admin-retry/', {'action': 'retry'}, format='json')

    def test_completed_goal_is_rejected(self):
        goal = DietaryGoal.objects.create(user=self.user, prompt='p', country='CZ', dinners=2,
                                          status=DietaryGoal.StatusChoices.COMPLETED)
        DietaryPlan.objects.create(dietary_goal=goal, meals=[], days=[], currency='CZK')
        with patch('diet_planner.views.generate_meal_pool_task') as task:
            resp = self._retry(goal)
        self.assertEqual(resp.status_code, 400, resp.content)
        self.assertEqual(resp.json()['code'], 'ALREADY_COMPLETED')
        task.delay.assert_not_called()

    def test_legacy_goal_is_rejected(self):
        goal = DietaryGoal.objects.create(user=self.user, prompt='p', country='CZ', num_days=3,
                                          status=DietaryGoal.StatusChoices.FAILED)
        with patch('diet_planner.views.generate_meal_pool_task') as task:
            resp = self._retry(goal)
        self.assertEqual(resp.status_code, 400, resp.content)
        self.assertEqual(resp.json()['code'], 'LEGACY_GOAL')
        task.delay.assert_not_called()
