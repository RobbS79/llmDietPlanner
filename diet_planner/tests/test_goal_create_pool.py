"""POST /api/goals/ takes per-slot counts; legacy day fields are refused."""
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from diet_planner.models import DietaryGoal
from login_app.models import UserProfile


class GoalCreatePoolTest(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='u', email='u@x.cz', password='pw')
        profile, _ = UserProfile.objects.get_or_create(user=self.user)
        profile.free_generations_remaining = 5
        profile.email_verified = True
        profile.save(update_fields=['free_generations_remaining', 'email_verified'])
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.task = patch('diet_planner.views.generate_meal_pool_task.delay',
                          return_value=type('T', (), {'id': 'task-1'})())
        self.task.start()
        self.addCleanup(self.task.stop)

    def _payload(self, **over):
        base = {'prompt': 'Rychlé večeře z kuřecího.', 'country': 'CZ', 'city': 'Praha',
                'breakfasts': 0, 'lunches': 2, 'dinners': 5, 'small_meals': 0, 'snacks': 1}
        base.update(over)
        return base

    def test_counts_are_stored_and_legacy_fields_stay_null(self):
        resp = self.client.post('/api/goals/', self._payload(), format='json')
        self.assertEqual(resp.status_code, 201, resp.content)
        goal = DietaryGoal.objects.get(id=resp.json()['data']['goal_id'])
        self.assertEqual(goal.pool_counts(), {'breakfast': 0, 'lunch': 2, 'dinner': 5, 'small_meal': 0, 'snack': 1})
        self.assertIsNone(goal.num_days)
        self.assertTrue(goal.is_pool)

    def test_all_zero_counts_rejected(self):
        resp = self.client.post('/api/goals/', self._payload(lunches=0, dinners=0, snacks=0), format='json')
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(DietaryGoal.objects.exists())

    def test_legacy_fields_rejected(self):
        resp = self.client.post('/api/goals/', self._payload(num_days=7), format='json')
        self.assertEqual(resp.status_code, 400)

    def test_count_above_14_rejected(self):
        resp = self.client.post('/api/goals/', self._payload(dinners=15), format='json')
        self.assertEqual(resp.status_code, 400)

    def test_counts_default_to_zero_when_omitted(self):
        resp = self.client.post('/api/goals/', {'prompt': 'Rychlé večeře z kuřecího.', 'country': 'CZ', 'city': 'Praha', 'dinners': 3}, format='json')
        self.assertEqual(resp.status_code, 201, resp.content)
        goal = DietaryGoal.objects.get(id=resp.json()['data']['goal_id'])
        self.assertEqual(goal.breakfasts, 0)
        self.assertEqual(goal.dinners, 3)
