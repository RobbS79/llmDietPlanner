from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, RequestFactory
from rest_framework.request import Request

from diet_planner.throttles import DiscoverDayThrottle


class DiscoverThrottleTest(TestCase):
    def setUp(self):
        cache.clear()

    def _req(self, user=None, ip='1.2.3.4'):
        raw = RequestFactory().post('/api/discover/', REMOTE_ADDR=ip)
        req = Request(raw)
        if user is not None:
            req.user = user
        return req

    def test_anonymous_key_is_ip(self):
        key = DiscoverDayThrottle().get_cache_key(self._req(), view=None)
        self.assertIn('1.2.3.4', key)

    def test_authenticated_users_are_throttled_by_user_id(self):
        user = get_user_model().objects.create(username='u1')
        key = DiscoverDayThrottle().get_cache_key(self._req(user), view=None)
        self.assertIn(f'user-{user.pk}', key)
