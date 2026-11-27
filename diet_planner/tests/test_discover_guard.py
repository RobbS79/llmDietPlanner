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

    @override_settings(TURNSTILE_SECRET_KEY='secret', TURNSTILE_SITE_KEY='',
                       DISCOVER_FREE_SEARCHES_BEFORE_CHALLENGE=1)
    def test_challenge_not_needed_without_site_key(self):
        # A secret alone would 403 visitors whose bundle has no widget to show.
        for _ in range(5):
            self.assertFalse(g.challenge_needed('5.5.5.5'))

    @override_settings(TURNSTILE_SECRET_KEY='secret', TURNSTILE_SITE_KEY='site',
                       DISCOVER_FREE_SEARCHES_BEFORE_CHALLENGE=3)
    def test_challenge_after_free_searches_until_verified(self):
        for _ in range(3):
            self.assertFalse(g.challenge_needed('9.9.9.9'))
        self.assertTrue(g.challenge_needed('9.9.9.9'))
        with mock.patch.object(g, '_siteverify', return_value=True):
            self.assertTrue(g.verify_challenge('token', '9.9.9.9'))
        self.assertFalse(g.challenge_needed('9.9.9.9'))


def _resp(status, body=None, bad_json=False):
    r = mock.Mock(status_code=status)
    if bad_json:
        r.json.side_effect = ValueError('not json')
    else:
        r.json.return_value = body or {}
    return r


@override_settings(TURNSTILE_SECRET_KEY='secret')
class TurnstileHardeningTest(TestCase):
    def setUp(self):
        cache.clear()

    def _verify(self, token='tok', **post):
        with mock.patch.object(g.requests, 'post', **post) as p:
            ok = g.verify_challenge(token, '1.2.3.4')
        return ok, p

    def test_non_string_or_huge_token_is_refused_without_network(self):
        for token in (['a'], 123, {'x': 1}, 'x' * 2049):
            ok, p = self._verify(token, return_value=_resp(200, {'success': True}))
            self.assertFalse(ok)
            p.assert_not_called()
        self.assertIsNone(cache.get('discover:verified:1.2.3.4'))

    def test_already_verified_skips_siteverify(self):
        cache.set('discover:verified:1.2.3.4', 1, 60)
        ok, p = self._verify(return_value=_resp(200, {'success': False}))
        self.assertTrue(ok)
        p.assert_not_called()

    def test_success_and_failure(self):
        self.assertTrue(self._verify(return_value=_resp(200, {'success': True}))[0])
        cache.clear()
        self.assertFalse(self._verify(return_value=_resp(200, {'success': False}))[0])

    def test_4xx_is_refused(self):
        ok, _ = self._verify(return_value=_resp(400, {'success': True}))
        self.assertFalse(ok)
        self.assertIsNone(cache.get('discover:verified:1.2.3.4'))

    def test_unparseable_body_is_refused(self):
        self.assertFalse(self._verify(return_value=_resp(200, bad_json=True))[0])

    def test_fails_open_only_on_outage(self):
        for kwargs in ({'side_effect': g.requests.Timeout()},
                       {'side_effect': g.requests.ConnectionError()},
                       {'return_value': _resp(503, bad_json=True)}):
            cache.clear()
            self.assertTrue(self._verify(**kwargs)[0], kwargs)

    def test_other_errors_do_not_fail_open(self):
        self.assertFalse(self._verify(side_effect=RuntimeError('boom'))[0])


class PragueDayTest(TestCase):
    def test_today_is_prague_date(self):
        from datetime import datetime, timezone as tz
        late = datetime(2026, 11, 30, 23, 30, tzinfo=tz.utc)  # 00:30 on 1 Dec in Prague
        with mock.patch('django.utils.timezone.now', return_value=late):
            self.assertEqual(g._today(), '2026-12-01')
