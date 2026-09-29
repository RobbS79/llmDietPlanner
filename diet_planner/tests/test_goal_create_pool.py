"""POST /api/goals/ takes per-slot counts; legacy day fields are refused."""
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from diet_planner.models import DietaryGoal
from login_app.models import UserProfile


class _PoolCreateBase(TestCase):
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


class GoalCreatePoolTest(_PoolCreateBase):
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


class GoalCreatePoolValidationTest(_PoolCreateBase):
    """Error codes, draft path, finalise, and no side effects on a 400."""

    def _free_left(self):
        return UserProfile.objects.get(user=self.user).free_generations_remaining

    def _assert_rejected(self, payload, code=None):
        before = self._free_left()
        resp = self.client.post('/api/goals/', payload, format='json')
        self.assertEqual(resp.status_code, 400, resp.content)
        body = resp.json()
        if code:
            self.assertEqual(body['code'], code)
        self.assertNotIn('input_value', resp.content.decode())
        self.assertFalse(DietaryGoal.objects.exists())
        self.assertEqual(self._free_left(), before)
        return body

    def test_draft_without_counts_leaves_counts_null(self):
        resp = self.client.post('/api/goals/', {'is_draft': True, 'prompt': 'rozepsané', 'country': 'CZ'}, format='json')
        self.assertEqual(resp.status_code, 201, resp.content)
        goal = DietaryGoal.objects.get(id=resp.json()['data']['goal_id'])
        for field in DietaryGoal.POOL_COUNT_FIELDS.values():
            self.assertIsNone(getattr(goal, field))

    def test_draft_with_legacy_field_still_saves(self):
        resp = self.client.post('/api/goals/', {'is_draft': True, 'prompt': 'rozepsané', 'country': 'CZ', 'num_days': 7}, format='json')
        self.assertEqual(resp.status_code, 201, resp.content)

    def test_draft_then_finalise_updates_same_row(self):
        resp = self.client.post('/api/goals/', {'is_draft': True, 'prompt': 'rozepsané', 'country': 'CZ'}, format='json')
        goal_id = resp.json()['data']['goal_id']
        resp = self.client.post('/api/goals/', self._payload(goal_id=goal_id), format='json')
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertEqual(resp.json()['data']['goal_id'], goal_id)
        self.assertEqual(DietaryGoal.objects.count(), 1)
        goal = DietaryGoal.objects.get(id=goal_id)
        self.assertEqual(goal.dinners, 5)
        self.assertIsNone(goal.num_days)

    def test_finalise_legacy_row_nulls_legacy_fields(self):
        goal = DietaryGoal.objects.create(user=self.user, prompt='stará', country='CZ', num_days=7,
                                          breakfast=True, lunch=True, dinner=True,
                                          small_meals_per_day=2, snacks_per_day=1)
        resp = self.client.post('/api/goals/', self._payload(goal_id=goal.id), format='json')
        self.assertEqual(resp.status_code, 201, resp.content)
        goal.refresh_from_db()
        for f in ('num_days', 'breakfast', 'lunch', 'dinner', 'small_meals_per_day', 'snacks_per_day'):
            self.assertIsNone(getattr(goal, f), f)
        self.assertTrue(goal.is_pool)

    def test_count_at_14_accepted(self):
        resp = self.client.post('/api/goals/', self._payload(dinners=14), format='json')
        self.assertEqual(resp.status_code, 201, resp.content)

    def test_negative_count_rejected(self):
        body = self._assert_rejected(self._payload(dinners=-1), code='INVALID_INPUT')
        self.assertIn('dinners', body['fields'])

    def test_null_count_rejected(self):
        self._assert_rejected(self._payload(dinners=None), code='INVALID_INPUT')

    def test_each_legacy_field_rejected_with_code(self):
        from diet_planner.schemas import DietaryGoalCreateRequest
        for field in DietaryGoalCreateRequest._LEGACY_FIELDS:
            with self.subTest(field=field):
                self._assert_rejected(self._payload(**{field: 1}), code='LEGACY_PAYLOAD')

    def test_all_zero_error_message(self):
        body = self._assert_rejected(self._payload(lunches=0, dinners=0, snacks=0), code='INVALID_INPUT')
        self.assertEqual(body['error'], 'Vyberte alespoň jedno jídlo.')
