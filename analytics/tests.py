from django.contrib.auth.models import User
from django.test import TestCase

from analytics.models import MarketingAttribution


class MarketingAttributionModelTests(TestCase):
    def test_defaults(self):
        user = User.objects.create_user(username="u1", email="u1@example.com")
        attr = MarketingAttribution.objects.create(user=user)
        self.assertFalse(attr.marketing_consent)
        self.assertEqual(attr.utm_source, "")
        self.assertEqual(user.marketing_attribution, attr)
