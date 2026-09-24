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
    post = SocialPost.objects.create(**defaults)
    post.refresh_from_db()   # dates as the jobs see them, not the strings above
    return post


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


# ---------------------------------------------------------------- interactivity

from social.interact import handle_action, verify_slack_signature  # noqa: E402

SECRET = 's3cret'


def _sign(body: bytes, ts=None, secret=SECRET):
    ts = ts or str(int(time.time()))
    return ts, 'v0=' + hmac.new(secret.encode(), f'v0:{ts}:'.encode() + body, sha256).hexdigest()


def _body(action_id, value, user='UHUMAN', kind='block_actions'):
    payload = {'type': kind, 'user': {'id': user},
               'actions': [{'action_id': action_id, 'value': str(value)}]}
    return urlencode({'payload': json.dumps(payload)}).encode()


class VerifySignatureTests(TestCase):
    def test_valid_stale_and_wrong(self):
        body = b'payload=%7B%7D'
        ts, sig = _sign(body)
        self.assertTrue(verify_slack_signature(SECRET, ts, sig, body))
        self.assertFalse(verify_slack_signature('other', ts, sig, body))
        self.assertFalse(verify_slack_signature(SECRET, ts, sig, body + b'x'))
        old_ts, old_sig = _sign(body, ts=str(int(time.time()) - 400))
        self.assertFalse(verify_slack_signature(SECRET, old_ts, old_sig, body))
        self.assertFalse(verify_slack_signature(SECRET, 'notanumber', sig, body))
        self.assertFalse(verify_slack_signature('', ts, sig, body))


@override_settings(SLACK_SIGNING_SECRET=SECRET, SOCIAL_SLACK_CHANNEL='C1', SLACK_BOT_TOKEN='x')
class InteractViewTests(TestCase):
    URL = '/api/social/slack/interact/'

    def setUp(self):
        patcher = patch('social.interact.SlackDrafts')
        self.drafts = patcher.start().return_value
        self.addCleanup(patcher.stop)

    def _send(self, body):
        ts, sig = _sign(body)
        return self.client.post(self.URL, data=body, content_type='application/x-www-form-urlencoded',
                                HTTP_X_SLACK_REQUEST_TIMESTAMP=ts, HTTP_X_SLACK_SIGNATURE=sig)

    def test_approve_sets_status_and_updates_card(self):
        post = _post()
        r = self._send(_body('social_approve', post.pk))
        self.assertEqual(r.status_code, 200)
        post.refresh_from_db()
        self.assertEqual((post.status, post.approved_by, post.error), ('approved', 'UHUMAN', ''))
        self.drafts.update_card.assert_called_once()
        self.assertEqual(self.drafts.update_card.call_args.args[0].pk, post.pk)

    def test_reject_sets_status(self):
        post = _post()
        self._send(_body('social_reject', post.pk))
        post.refresh_from_db()
        self.assertEqual((post.status, post.approved_by), ('rejected', 'UHUMAN'))

    def test_second_click_only_refreshes(self):
        post = _post(status='approved', approved_by='UFIRST')
        self._send(_body('social_reject', post.pk))
        post.refresh_from_db()
        self.assertEqual((post.status, post.approved_by), ('approved', 'UFIRST'))
        self.drafts.update_card.assert_called_once()

    def test_bad_signature_is_400_and_changes_nothing(self):
        post = _post()
        body = _body('social_approve', post.pk)
        ts, _ = _sign(body)
        r = self.client.post(self.URL, data=body, content_type='application/x-www-form-urlencoded',
                             HTTP_X_SLACK_REQUEST_TIMESTAMP=ts, HTTP_X_SLACK_SIGNATURE='v0=bad')
        self.assertEqual(r.status_code, 400)
        post.refresh_from_db()
        self.assertEqual(post.status, 'draft')
        self.drafts.update_card.assert_not_called()

    def test_unset_secret_is_503(self):
        with override_settings(SLACK_SIGNING_SECRET=''):
            self.assertEqual(self._send(_body('social_approve', 1)).status_code, 503)

    def test_unknown_post_other_payload_types_and_garbage_are_200_noops(self):
        self.assertEqual(self._send(_body('social_approve', 999)).status_code, 200)
        self.assertEqual(self._send(_body('social_approve', 1, kind='view_submission')).status_code, 200)
        self.assertEqual(self._send(b'payload=not-json').status_code, 200)
        self.assertEqual(self._send(b'nothing=here').status_code, 200)
        self.drafts.update_card.assert_not_called()

    def test_card_update_failure_does_not_undo_the_decision(self):
        self.drafts.update_card.side_effect = RuntimeError('slack down')
        post = _post()
        r = self._send(_body('social_approve', post.pk))
        self.assertEqual(r.status_code, 200)
        post.refresh_from_db()
        self.assertEqual(post.status, 'approved')

    def test_handle_action_reports_outcome(self):
        post = _post()
        self.assertEqual(handle_action('social_approve', str(post.pk), 'UHUMAN'), 'approved')
        self.assertEqual(handle_action('social_approve', str(post.pk), 'UHUMAN'), 'refreshed')
        self.assertEqual(handle_action('social_reject', 'abc', 'UHUMAN'), 'ignored')
        self.assertEqual(handle_action('other_action', str(post.pk), 'UHUMAN'), 'ignored')
