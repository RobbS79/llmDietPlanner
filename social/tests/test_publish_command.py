from datetime import date
from unittest.mock import MagicMock

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from social.models import SocialPost
from social.publishers import PublishError
from social.slack import MISSED_NOTE


def _post(kind='deals', scheduled='2026-09-07', status='approved', **kw):
    defaults = dict(kind=kind, iso_week='2026-W37', scheduled_for=scheduled, status=status,
                    approved_by='UHUMAN' if status == 'approved' else '',
                    caption='Cibule v Lidlu v akci.', image=b'PNG',
                    facts={'kind': kind, 'name': 'Svíčková',
                           'deals': [{'ingredient': 'cibule', 'shop': 'Lidl', 'valid_until': '2026-09-13'}],
                           'link': 'https://eatalnicek.eu/?utm_source={channel}&utm_campaign=auto-deals-2026-W37'},
                    slack_channel='C1', slack_ts='1.0')
    defaults.update(kw)
    return SocialPost.objects.create(**defaults)


def _seams(publishers=None, today=date(2026, 9, 7), override=None):
    slack = MagicMock()
    slack.caption_override.return_value = override
    pubs = publishers or {'facebook': MagicMock(return_value='111_999'),
                          'pinterest': MagicMock(return_value='pin42')}
    return dict(slack=slack, publishers=pubs, today=today)


def _card_statuses(seams):
    return [c.args[0].status for c in seams['slack'].update_card.call_args_list]


@override_settings(SOCIAL_SLACK_CHANNEL='C1', SLACK_BOT_TOKEN='x')
class PublishCommandTests(TestCase):
    def test_approved_post_is_published_with_channel_utm_and_card_redrawn(self):
        post = _post()
        seams = _seams()
        call_command('publish_social_posts', **seams)
        post.refresh_from_db()
        self.assertEqual(post.status, 'published')
        self.assertEqual(post.facebook_post_id, '111_999')
        self.assertEqual(post.approved_by, 'UHUMAN')
        self.assertIsNotNone(post.published_at)
        kwargs = seams['publishers']['facebook'].call_args.kwargs
        self.assertEqual(kwargs['link'], 'https://eatalnicek.eu/?utm_source=facebook&utm_campaign=auto-deals-2026-W37')
        self.assertEqual(kwargs['caption'], 'Cibule v Lidlu v akci.')
        self.assertEqual(kwargs['image'], b'PNG')
        self.assertEqual(_card_statuses(seams), ['published'])
        seams['slack'].reply.assert_not_called()

    def test_recipe_goes_to_both_channels_with_title(self):
        _post(kind='recipe', scheduled='2026-09-07')
        seams = _seams()
        call_command('publish_social_posts', **seams)
        self.assertEqual(seams['publishers']['pinterest'].call_args.kwargs['title'], 'Svíčková')
        post = SocialPost.objects.get()
        self.assertEqual((post.facebook_post_id, post.pinterest_pin_id), ('111_999', 'pin42'))

    def test_draft_due_is_marked_missed_once_and_not_published(self):
        _post(status='draft')
        seams = _seams()
        call_command('publish_social_posts', **seams)
        call_command('publish_social_posts', **seams)
        post = SocialPost.objects.get()
        self.assertEqual((post.status, post.error), ('draft', MISSED_NOTE))
        self.assertEqual(_card_statuses(seams), ['draft'])
        seams['publishers']['facebook'].assert_not_called()

    def test_rejected_and_published_rows_are_ignored(self):
        _post(status='rejected', error='❌')
        _post(status='published', iso_week='2026-W36', facebook_post_id='1_1')
        seams = _seams()
        call_command('publish_social_posts', **seams)
        seams['publishers']['facebook'].assert_not_called()
        seams['slack'].update_card.assert_not_called()

    def test_caption_override_replaces_text_after_validation(self):
        _post()
        seams = _seams(override='Cibule je v akci v Lidlu, mrkněte.')
        call_command('publish_social_posts', **seams)
        self.assertEqual(seams['publishers']['facebook'].call_args.kwargs['caption'],
                         'Cibule je v akci v Lidlu, mrkněte.')
        self.assertEqual(SocialPost.objects.get().caption, 'Cibule je v akci v Lidlu, mrkněte.')

    def test_invalid_override_is_refused_and_original_used(self):
        _post()
        seams = _seams(override='Ušetříte 500 Kč v Kauflandu!')
        call_command('publish_social_posts', **seams)
        self.assertEqual(seams['publishers']['facebook'].call_args.kwargs['caption'], 'Cibule v Lidlu v akci.')
        replies = ' '.join(c.args[1] for c in seams['slack'].reply.call_args_list)
        self.assertIn('override rejected', replies)

    def test_approved_without_caption_cannot_publish_but_stays_approved(self):
        _post(caption='', error='caption failed validation')
        seams = _seams()
        with self.assertRaises(CommandError):
            call_command('publish_social_posts', **seams)
        self.assertEqual(SocialPost.objects.get().status, 'approved')
        self.assertEqual(_card_statuses(seams), ['approved'])
        seams['publishers']['facebook'].assert_not_called()

    def test_partial_failure_keeps_success_and_retries_only_the_failed_channel(self):
        _post(kind='recipe')
        pinterest = MagicMock(side_effect=PublishError('pinterest 401: Authentication failed.'))
        seams = _seams(publishers={'facebook': MagicMock(return_value='111_999'), 'pinterest': pinterest})
        with self.assertRaises(CommandError):
            call_command('publish_social_posts', **seams)
        post = SocialPost.objects.get()
        self.assertEqual(post.status, 'failed')
        self.assertEqual(post.facebook_post_id, '111_999')
        self.assertIn('Authentication failed', post.error)
        self.assertEqual(_card_statuses(seams), ['failed'])

        pinterest.side_effect = None
        pinterest.return_value = 'pin42'
        call_command('publish_social_posts', **seams)
        post.refresh_from_db()
        self.assertEqual(post.status, 'published')
        self.assertEqual(seams['publishers']['facebook'].call_count, 1)
        self.assertEqual(_card_statuses(seams), ['failed', 'published'])

    def test_future_posts_are_not_touched(self):
        _post(scheduled='2026-09-09')
        _post(scheduled='2026-09-09', status='draft', iso_week='2026-W38')
        seams = _seams(today=date(2026, 9, 7))
        call_command('publish_social_posts', **seams)
        seams['publishers']['facebook'].assert_not_called()
        seams['slack'].update_card.assert_not_called()

    def test_stale_draft_is_rejected_after_seven_days(self):
        _post(scheduled='2026-08-24', status='draft')
        seams = _seams(today=date(2026, 9, 7))
        call_command('publish_social_posts', **seams)
        post = SocialPost.objects.get()
        self.assertEqual(post.status, 'rejected')
        self.assertIn('stale', post.error)
        self.assertEqual(_card_statuses(seams), ['rejected'])

    def test_deals_with_mostly_expired_offers_are_rejected(self):
        _post(facts={'kind': 'deals', 'link': 'https://e/?utm_source={channel}',
                     'deals': [{'ingredient': 'a', 'shop': 'Lidl', 'valid_until': '2026-09-01'},
                               {'ingredient': 'b', 'shop': 'Lidl', 'valid_until': '2026-09-02'},
                               {'ingredient': 'c', 'shop': 'Lidl', 'valid_until': '2026-09-20'}]})
        seams = _seams(today=date(2026, 9, 7))
        call_command('publish_social_posts', **seams)
        post = SocialPost.objects.get()
        self.assertEqual(post.status, 'rejected')
        self.assertIn('expired', post.error)
        seams['publishers']['facebook'].assert_not_called()
        self.assertEqual(_card_statuses(seams), ['rejected'])

    def test_force_publishes_deals_past_the_expiry_gate_but_still_needs_approval(self):
        expired = {'kind': 'deals', 'link': 'https://e/?utm_source={channel}',
                   'deals': [{'ingredient': 'a', 'shop': 'Lidl', 'valid_until': '2026-09-01'},
                             {'ingredient': 'b', 'shop': 'Lidl', 'valid_until': '2026-09-02'},
                             {'ingredient': 'c', 'shop': 'Lidl', 'valid_until': '2026-09-20'}]}
        post = _post(facts=expired, status='draft')
        seams = _seams(today=date(2026, 9, 7))
        call_command('publish_social_posts', force=True, **seams)
        self.assertEqual(SocialPost.objects.get().status, 'draft')
        seams['publishers']['facebook'].assert_not_called()

        SocialPost.objects.filter(pk=post.pk).update(status='approved', approved_by='UHUMAN')
        seams = _seams(today=date(2026, 9, 7))
        call_command('publish_social_posts', force=True, **seams)
        post.refresh_from_db()
        self.assertEqual(post.status, 'published')
        self.assertEqual(post.facebook_post_id, '111_999')

    def test_force_also_skips_the_stale_gate(self):
        _post(scheduled='2026-08-24', status='draft')
        seams = _seams(today=date(2026, 9, 7))
        call_command('publish_social_posts', force=True, **seams)
        self.assertEqual(SocialPost.objects.get().status, 'draft')   # still needs the click

    def test_only_limits_to_one_row(self):
        mine = _post()
        _post(iso_week='2026-W36')
        seams = _seams()
        call_command('publish_social_posts', only=mine.pk, **seams)
        self.assertEqual(seams['publishers']['facebook'].call_count, 1)
        self.assertEqual(SocialPost.objects.filter(status='published').get().pk, mine.pk)

    def test_date_option_overrides_today(self):
        _post(scheduled='2026-09-09')
        seams = _seams(today=date(2026, 9, 7))
        call_command('publish_social_posts', date='2026-09-09', **seams)
        self.assertEqual(SocialPost.objects.get().status, 'published')
