# diet_planner/tests/test_spa_noindex_header.py
# /nakup is a personal shopping list: crawlers must be told to skip it even
# before the SPA's own robots meta runs.
from django.test import TestCase


class SpaNoindexHeaderTest(TestCase):
    def test_nakup_is_noindex(self):
        for path in ('/nakup', '/nakup/', '/nakup?vitej=1'):
            resp = self.client.get(path)
            self.assertEqual(resp.headers.get('X-Robots-Tag'), 'noindex, nofollow', path)

    def test_other_spa_routes_stay_indexable(self):
        for path in ('/', '/o-nas', '/nakupni-tipy'):
            resp = self.client.get(path)
            self.assertNotIn('X-Robots-Tag', resp.headers, path)
