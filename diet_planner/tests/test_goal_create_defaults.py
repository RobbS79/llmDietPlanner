"""When the client sends no shop/store_mode, the goal must default to the
Rohlík single-store baseline — the only store with real catalog data."""
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from diet_planner.models import DietaryGoal
from login_app.models import UserProfile


class GoalCreateDefaultsTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='u1', email='u1@example.com', password='pw'
        )
        # Give the user a free generation so creation isn't blocked by the
        # paywall, and mark the email verified so the verification gate allows
        # generation.
        profile, _ = UserProfile.objects.get_or_create(user=self.user)
        profile.free_generations_remaining = max(profile.free_generations_remaining, 1)
        profile.email_verified = True
        profile.save(update_fields=['free_generations_remaining', 'email_verified'])
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def _payload(self, **over):
        base = {
            'prompt': 'Týdenní jídelníček pro jednoho, zdravě a levně.',
            'country': 'CZ',
            'city': 'Praha',
        }
        base.update(over)
        return base

    def test_defaults_to_rohlik_single_when_omitted(self):
        resp = self.client.post('/api/goals/', self._payload(), format='json')
        self.assertEqual(resp.status_code, 201, resp.content)
        goal = DietaryGoal.objects.get(id=resp.json()['data']['goal_id'])
        self.assertEqual(goal.shop, 'ROHLIK')
        self.assertEqual(goal.store_mode, 'single')

    def test_unverified_email_blocks_generation(self):
        # A user who has not verified their email cannot generate a plan; the
        # request is refused before any goal is created.
        UserProfile.objects.filter(user=self.user).update(email_verified=False)
        resp = self.client.post('/api/goals/', self._payload(), format='json')
        self.assertEqual(resp.status_code, 403, resp.content)
        self.assertEqual(resp.json().get('code'), 'EMAIL_NOT_VERIFIED')
        self.assertFalse(DietaryGoal.objects.filter(user=self.user).exists())

    def test_unverified_email_blocks_retry_bypass(self):
        # Draft-then-retry must not bypass the verification gate: a goal created
        # via the un-gated draft path cannot be pushed through generation by an
        # unverified user via the retry endpoint.
        UserProfile.objects.filter(user=self.user).update(email_verified=False)
        goal = DietaryGoal.objects.create(
            user=self.user, prompt='draft', country='CZ',
            status=DietaryGoal.StatusChoices.PENDING,
        )
        resp = self.client.post(f'/api/goals/{goal.id}/admin-retry/', {'action': 'retry'}, format='json')
        self.assertEqual(resp.status_code, 403, resp.content)
        self.assertEqual(resp.json().get('code'), 'EMAIL_NOT_VERIFIED')
