"""Throttles for the anonymous first-visit endpoints.

DRF's AnonRateThrottle skips signed-in users, but a signed-in user can still
burn Gemini calls on /api/discover/, so these key on the user id when there is
one and on the client IP otherwise.
"""
from rest_framework.throttling import SimpleRateThrottle

from diet_planner.client_ip import client_ip


class _EveryoneThrottle(SimpleRateThrottle):
    def get_ident(self, request):
        # Not DRF's get_ident: with NUM_PROXIES unset it keys on the whole,
        # client-forgeable X-Forwarded-For string.
        return client_ip(request)

    def get_cache_key(self, request, view):
        user = getattr(request, 'user', None)
        if user is not None and getattr(user, 'is_authenticated', False):
            ident = f'user-{user.pk}'
        else:
            ident = self.get_ident(request)
        return self.cache_format % {'scope': self.scope, 'ident': ident}


class DiscoverDayThrottle(_EveryoneThrottle):
    scope = 'discover'


class DiscoverBurstThrottle(_EveryoneThrottle):
    scope = 'discover_burst'


class ComposeThrottle(_EveryoneThrottle):
    scope = 'compose'
