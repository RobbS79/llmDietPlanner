from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase, override_settings

from analytics import capi
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


class BuildPayloadTests(TestCase):
    def test_build_payload_hashes_email_and_sets_action_source(self):
        payload = capi.build_payload(
            event_name="Purchase",
            event_id="evt-1",
            email="Buyer@Example.com",
            fbp="fb.1.123.456",
            fbc="fb.1.123.abc",
            client_ip="203.0.113.5",
            user_agent="UA/1.0",
            event_source_url="https://eatalnicek.eu/pricing",
            custom_data={"value": 99, "currency": "CZK"},
        )
        from analytics.hashing import hash_email
        data = payload["data"][0]
        self.assertEqual(data["event_name"], "Purchase")
        self.assertEqual(data["event_id"], "evt-1")
        self.assertEqual(data["action_source"], "website")
        self.assertEqual(data["user_data"]["em"], [hash_email("Buyer@Example.com")])
        self.assertEqual(data["user_data"]["fbp"], "fb.1.123.456")
        self.assertEqual(data["custom_data"], {"value": 99, "currency": "CZK"})


@override_settings(
    ANALYTICS_ENABLED=True, FB_PIXEL_ID="123", FB_CAPI_ACCESS_TOKEN="tok",
    FB_CAPI_TEST_EVENT_CODE="",
)
class SendEventTests(TestCase):
    @patch("analytics.capi.requests.post")
    def test_send_posts_to_graph(self, mock_post):
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"events_received": 1}
        ok = capi.send_event(event_name="CompleteRegistration", event_id="e1",
                             email="a@b.com")
        self.assertTrue(ok)
        url = mock_post.call_args[0][0]
        self.assertIn("/123/events", url)

    @patch("analytics.capi.requests.post")
    def test_disabled_flag_short_circuits(self, mock_post):
        with override_settings(ANALYTICS_ENABLED=False):
            ok = capi.send_event(event_name="CompleteRegistration", event_id="e1",
                                 email="a@b.com")
        self.assertFalse(ok)
        mock_post.assert_not_called()

    @patch("analytics.capi.requests.post")
    def test_missing_credentials_short_circuits(self, mock_post):
        with override_settings(FB_CAPI_ACCESS_TOKEN=""):
            ok = capi.send_event(event_name="CompleteRegistration", event_id="e1",
                                 email="a@b.com")
        self.assertFalse(ok)
        mock_post.assert_not_called()
