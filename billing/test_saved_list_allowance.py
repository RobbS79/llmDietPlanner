from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from billing.entitlements import saved_list_allowance
from diet_planner.models import SavedShoppingList


class SavedListAllowanceTest(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create(username='free')

    def _save(self, when=None):
        lst = SavedShoppingList.objects.create(user=self.user, recipe_ids=[1], people=2)
        if when:
            SavedShoppingList.objects.filter(pk=lst.pk).update(created_at=when)

    def test_free_user_gets_three_this_month(self):
        for _ in range(3):
            self.assertTrue(saved_list_allowance(self.user)['can_save'])
            self._save()
        allowance = saved_list_allowance(self.user)
        self.assertFalse(allowance['can_save'])
        self.assertEqual(allowance['used'], 3)
        self.assertEqual(allowance['limit'], 3)

    def test_last_month_does_not_count(self):
        for _ in range(3):
            self._save(when=timezone.now() - timedelta(days=40))
        self.assertTrue(saved_list_allowance(self.user)['can_save'])

    def test_subscriber_is_unlimited(self):
        for _ in range(5):
            self._save()
        sub = mock.Mock()
        sub.is_entitled.return_value = True
        with mock.patch('billing.entitlements.active_subscription', return_value=sub):
            allowance = saved_list_allowance(self.user)
        self.assertTrue(allowance['can_save'])
        self.assertIsNone(allowance['limit'])
