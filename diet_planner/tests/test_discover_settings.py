import warnings

from django.conf import settings
from django.test import SimpleTestCase


class DiscoverSettingsTest(SimpleTestCase):
    def test_throttle_scopes_exist(self):
        rates = settings.REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']
        for scope in ('discover', 'discover_burst', 'compose', 'discover_sheet', 'signup'):
            self.assertIn(scope, rates)
        self.assertEqual(rates['discover_sheet'], '120/hour')

    def test_defaults(self):
        self.assertEqual(settings.DISCOVER_DAILY_LLM_BUDGET, 500)
        self.assertEqual(settings.DISCOVER_FREE_SEARCHES_BEFORE_CHALLENGE, 3)
        self.assertEqual(settings.TURNSTILE_SECRET_KEY, '')
        self.assertEqual(settings.DISCOVER_LLM_TIMEOUT_SECONDS, 4)

    def test_cache_falls_back_to_locmem_without_url(self):
        self.assertIn('LocMemCache', settings.CACHES['default']['BACKEND'])

    def test_missing_shared_cache_warns_loudly_in_production(self):
        from llm_diet_planner_project import settings as project_settings
        with self.assertWarns(RuntimeWarning):
            project_settings._warn_if_no_shared_cache(debug=False, cache_url='')
        with warnings.catch_warnings():
            warnings.simplefilter('error')
            project_settings._warn_if_no_shared_cache(debug=True, cache_url='')
            project_settings._warn_if_no_shared_cache(debug=False, cache_url='redis://r:6379/1')
