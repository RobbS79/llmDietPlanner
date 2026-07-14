from django.contrib.auth.models import User
from django.test import TestCase

from analytics.models import MarketingAttribution
from analytics.hashing import hash_email


class MarketingAttributionModelTests(TestCase):
    def test_defaults(self):
        user = User.objects.create_user(username="u1", email="u1@example.com")
        attr = MarketingAttribution.objects.create(user=user)
        self.assertFalse(attr.marketing_consent)
        self.assertEqual(attr.utm_source, "")
        self.assertEqual(user.marketing_attribution, attr)


class HashEmailTests(TestCase):
    def test_normalizes_then_sha256(self):
        # Meta requires lowercase + trimmed before SHA-256.
        import hashlib
        expected = hashlib.sha256("user@example.com".encode()).hexdigest()
        self.assertEqual(hash_email("  User@Example.com "), expected)

    def test_empty_returns_empty(self):
        self.assertEqual(hash_email(""), "")
        self.assertEqual(hash_email(None), "")
