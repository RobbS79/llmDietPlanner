import hmac
import json
import time
from hashlib import sha256
from unittest.mock import patch
from urllib.parse import urlencode

from django.test import TestCase, override_settings

from social.cards import card_signature, card_url
from social.models import SocialPost


def _post(**kw):
    defaults = dict(kind='recipe', iso_week='2026-W39', scheduled_for='2026-09-23',
                    caption='Tofu kari.', image=b'\x89PNG', slack_channel='C1', slack_ts='1.0')
    defaults.update(kw)
    return SocialPost.objects.create(**defaults)


class CardUrlTests(TestCase):
    def test_url_is_site_plus_signed_path(self):
        post = _post()
        url = card_url(post)
        self.assertTrue(url.startswith('https://eatalnicek.eu/api/social/card/'))
        self.assertTrue(url.endswith(f'/{card_signature(post.pk)}.png'))
        self.assertEqual(len(card_signature(post.pk)), 32)
        self.assertNotEqual(card_signature(post.pk), card_signature(post.pk + 1))

    def test_card_served_with_valid_signature(self):
        post = _post()
        r = self.client.get(f'/api/social/card/{post.pk}/{card_signature(post.pk)}.png')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r['Content-Type'], 'image/png')
        self.assertEqual(r.content, b'\x89PNG')
        self.assertIn('max-age', r['Cache-Control'])

    def test_bad_signature_missing_row_or_missing_image_are_404(self):
        post = _post()
        empty = _post(iso_week='2026-W40', image=None)
        self.assertEqual(self.client.get(f'/api/social/card/{post.pk}/{"0" * 32}.png').status_code, 404)
        self.assertEqual(self.client.get(f'/api/social/card/999/{card_signature(999)}.png').status_code, 404)
        self.assertEqual(self.client.get(f'/api/social/card/{empty.pk}/{card_signature(empty.pk)}.png').status_code, 404)
