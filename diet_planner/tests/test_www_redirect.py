"""www.eatalnicek.eu must 301 to the bare domain (one host for search engines).

Found 2026-10-29: www served the whole site with 200 alongside eatalnicek.eu.
"""
from django.test import TestCase, override_settings

HOSTS = ['eatalnicek.eu', 'www.eatalnicek.eu', 'testserver']


@override_settings(ALLOWED_HOSTS=HOSTS, PUBLIC_SITE_URL='https://eatalnicek.eu')
class WwwRedirectTest(TestCase):
    def test_www_get_redirects_permanently_keeping_path_and_query(self):
        resp = self.client.get('/recepty/?page=2', HTTP_HOST='www.eatalnicek.eu')
        self.assertEqual(resp.status_code, 301)
        self.assertEqual(resp['Location'], 'https://eatalnicek.eu/recepty/?page=2')

    def test_www_post_keeps_method(self):
        resp = self.client.post('/api/auth/login/', HTTP_HOST='www.eatalnicek.eu')
        self.assertEqual(resp.status_code, 308)
        self.assertEqual(resp['Location'], 'https://eatalnicek.eu/api/auth/login/')

    def test_bare_domain_is_served(self):
        resp = self.client.get('/robots.txt', HTTP_HOST='eatalnicek.eu')
        self.assertEqual(resp.status_code, 200)

    def test_other_hosts_untouched(self):
        # DO health checks and the dev box hit other hostnames
        resp = self.client.get('/robots.txt')
        self.assertEqual(resp.status_code, 200)
