# diet_planner/tests/test_discover_guard.py
from unittest import mock

from django.core.cache import cache
from django.test import TestCase, override_settings

from diet_planner.services import discover_guard as g


@override_settings(DISCOVER_DAILY_LLM_BUDGET=2, TURNSTILE_SECRET_KEY='')
class GuardTest(TestCase):
    def setUp(self):
        cache.clear()

    def test_budget_allows_then_refuses(self):
        self.assertTrue(g.take_llm_slot())
        self.assertTrue(g.take_llm_slot())
        self.assertFalse(g.take_llm_slot())

    def test_alert_fires_once_at_80_percent(self):
        with mock.patch.object(g, '_alert') as alert:
            g.take_llm_slot(); g.take_llm_slot(); g.take_llm_slot()
        alert.assert_called_once()

    def test_result_cache_key_ignores_case_and_accents(self):
        self.assertEqual(g.result_key('Kuřecí  Prsa'), g.result_key('kureci prsa'))

    def test_challenge_not_needed_without_turnstile_keys(self):
        for _ in range(10):
            self.assertFalse(g.challenge_needed('1.2.3.4'))

    @override_settings(TURNSTILE_SECRET_KEY='secret', DISCOVER_FREE_SEARCHES_BEFORE_CHALLENGE=3)
    def test_challenge_after_free_searches_until_verified(self):
        for _ in range(3):
            self.assertFalse(g.challenge_needed('9.9.9.9'))
        self.assertTrue(g.challenge_needed('9.9.9.9'))
        with mock.patch.object(g, '_siteverify', return_value=True):
            self.assertTrue(g.verify_challenge('token', '9.9.9.9'))
        self.assertFalse(g.challenge_needed('9.9.9.9'))
