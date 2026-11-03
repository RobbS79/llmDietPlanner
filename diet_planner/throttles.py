"""Throttles for the anonymous first-visit endpoints.

DRF's AnonRateThrottle skips signed-in users, but a signed-in user can still
burn Gemini calls on /api/discover/, so these key on the user id when there is
one and on the client IP otherwise.
"""
from rest_framework.throttling import SimpleRateThrottle


class _EveryoneThrottle(SimpleRateThrottle):
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
