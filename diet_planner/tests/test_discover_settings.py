from django.conf import settings
from django.test import SimpleTestCase


class DiscoverSettingsTest(SimpleTestCase):
    def test_throttle_scopes_exist(self):
        rates = settings.REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']
        for scope in ('discover', 'discover_burst', 'compose', 'signup'):
            self.assertIn(scope, rates)

    def test_defaults(self):
        self.assertEqual(settings.DISCOVER_DAILY_LLM_BUDGET, 500)
        self.assertEqual(settings.DISCOVER_FREE_SEARCHES_BEFORE_CHALLENGE, 3)
        self.assertEqual(settings.TURNSTILE_SECRET_KEY, '')

    def test_cache_falls_back_to_locmem_without_url(self):
        self.assertIn('LocMemCache', settings.CACHES['default']['BACKEND'])
