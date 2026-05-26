from django.contrib.sitemaps import Sitemap


class StaticPagesSitemap(Sitemap):
    """Sitemap for all public-facing SPA pages (served by the React SPA)."""
    protocol = "https"
    changefreq = "weekly"
    priority = 0.5

    def items(self):
        return ["/", "/login", "/pricing", "/privacy", "/terms"]

    def location(self, item):
        return item


class LandingSitemap(Sitemap):
    """High-priority landing page."""
    protocol = "https"
    changefreq = "daily"
    priority = 1.0

    def items(self):
        return ["/"]

    def location(self, item):
        return item


class PricingSitemap(Sitemap):
    """Pricing page — updated frequently."""
    protocol = "https"
    changefreq = "weekly"
    priority = 0.9

    def items(self):
        return ["/pricing"]

    def location(self, item):
        return item


class LegalSitemap(Sitemap):
    """Privacy and terms pages — rarely change."""
    protocol = "https"
    changefreq = "yearly"
    priority = 0.3

    def items(self):
        return ["/privacy", "/terms"]

    def location(self, item):
        return item


class AuthSitemap(Sitemap):
    """Login/register page."""
    protocol = "https"
    changefreq = "monthly"
    priority = 0.6

    def items(self):
        return ["/login"]

    def location(self, item):
        return item


# Registry for urls.py
sitemaps = {
    "landing": LandingSitemap,
    "pricing": PricingSitemap,
    "legal": LegalSitemap,
    "auth": AuthSitemap,
}
