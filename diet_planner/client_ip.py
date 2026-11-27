"""One place that decides who the client is (abuse limits key on it).

Prod is DigitalOcean App Platform behind Cloudflare. The platform sets
DO-Connecting-IP; X-Forwarded-For is client-controlled at its left end, so
only its RIGHTMOST hop (appended by the last proxy) is trusted. Every
candidate must parse as an IP address, otherwise the next one is tried.
"""
import ipaddress
import logging

logger = logging.getLogger(__name__)

_HEADERS = ('HTTP_DO_CONNECTING_IP', 'HTTP_CF_CONNECTING_IP', 'HTTP_X_FORWARDED_FOR', 'REMOTE_ADDR')
_logged = False


def _valid(value) -> str:
    value = str(value or '').strip()
    try:
        ipaddress.ip_address(value)
    except ValueError:
        return ''
    return value


def client_ip(request) -> str:
    """The client IP for throttling: DO-Connecting-IP, CF-Connecting-IP,
    the rightmost X-Forwarded-For hop, REMOTE_ADDR, else 'unknown'."""
    global _logged
    meta = getattr(request, 'META', {}) or {}
    for header in _HEADERS:
        raw = meta.get(header, '')
        if header == 'HTTP_X_FORWARDED_FOR':
            raw = raw.split(',')[-1] if raw else ''
        ip = _valid(raw)
        if ip:
            if not _logged:
                _logged = True
                logger.info('client identity taken from %s', header)
            return ip
    return 'unknown'
