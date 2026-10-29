from urllib.parse import urlparse

from django.conf import settings
from django.http import HttpResponsePermanentRedirect


class WwwRedirectMiddleware:
    """
    Send www.<public domain> to the bare public domain so search engines see a
    single host. 301 for GET/HEAD, 308 otherwise so form posts keep their method.
    Other hostnames (DO health checks, dev box) pass through untouched.
    """

    def __init__(self, get_response):
        self.get_response = get_response
        self.public_host = (urlparse(settings.PUBLIC_SITE_URL).hostname or '').lower()

    def __call__(self, request):
        host = request.get_host().split(':')[0].lower()
        if self.public_host and host == f'www.{self.public_host}':
            response = HttpResponsePermanentRedirect(
                settings.PUBLIC_SITE_URL.rstrip('/') + request.get_full_path())
            if request.method not in ('GET', 'HEAD'):
                response.status_code = 308
            return response
        return self.get_response(request)


class SecurityHeadersMiddleware:
    """
    Add Content-Security-Policy and Permissions-Policy headers to every
    response, except requests to /admin/ paths (Django admin relies on
    inline scripts/styles that would break under strict CSP).
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        if not request.path.startswith("/admin/"):
            response["Content-Security-Policy"] = (
                "default-src 'self'; "
                "script-src 'self' https://connect.facebook.net; "
                "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
                "img-src 'self' data: https://www.facebook.com; "
                "font-src 'self' https://fonts.gstatic.com; "
                "connect-src 'self' https://www.facebook.com https://connect.facebook.net; "
                "frame-src 'none'; "
                "object-src 'none'; "
                "base-uri 'self'; "
                "form-action 'self'; "
                "frame-ancestors 'none'; "
                "worker-src blob:; "
                "manifest-src 'self'"
            )
            response["Permissions-Policy"] = (
                "accelerometer=(), "
                "camera=(), "
                "geolocation=(), "
                "gyroscope=(), "
                "magnetometer=(), "
                "microphone=(), "
                "payment=(), "
                "usb=(), "
                "interest-cohort=()"
            )

        return response
