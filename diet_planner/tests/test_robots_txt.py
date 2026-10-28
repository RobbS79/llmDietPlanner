"""/robots.txt must be served at the site root.

Crawlers only look at /robots.txt; Vite's `/static/` base put the old
public/robots.txt at /static/robots.txt, and the React catch-all 404'd the
root (found while wiring Google Search Console 2026-10-28).
"""
from django.test import TestCase


class RobotsTxtTest(TestCase):
    def test_served_at_root_as_plain_text(self):
        resp = self.client.get('/robots.txt')
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp['Content-Type'].startswith('text/plain'))

    def test_allows_crawling_and_points_at_sitemap(self):
        body = self.client.get('/robots.txt').content.decode()
        self.assertIn('User-agent: *', body)
        self.assertIn('Allow: /', body)
        self.assertIn('Sitemap: https://eatalnicek.eu/sitemap.xml', body)
        self.assertNotIn('Disallow: /\n', body)
