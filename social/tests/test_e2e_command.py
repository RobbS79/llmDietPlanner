import io
import json
from datetime import date
from unittest.mock import MagicMock

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from social.facts import NoFacts
from social.models import SocialPost

FACTS = {'kind': 'recipe', 'recipe_id': 1, 'name': 'Svíčková', 'kcal': 420, 'minutes': 60,
         'servings': 4, 'source_name': 'Apetit', 'source_url': 'https://apetit.cz', 'deals_matched': 0,
         'deals_total': 5, 'deal_shops': [], 'image_url': 'https://eatalnicek.eu/static/x.webp'}
CAPTION = 'Svíčková, hotová za 60 minut. #recept #vareni'
TODAY = date(2026, 9, 18)


def _photo():
    from PIL import Image
    buf = io.BytesIO()
    Image.new('RGB', (400, 300), (120, 80, 40)).save(buf, format='WEBP')
    return buf.getvalue()


def _build_facts(kind, week):
    return {**FACTS, 'iso_week': week,
            'link': f'https://eatalnicek.eu/recepty/1/svickova/?utm_source={{channel}}&utm_campaign=auto-{kind}-{week}'}


def _slack():
    slack = MagicMock()

    def post_draft(post, today=None):
        post.slack_channel, post.slack_ts = 'C1', '1.0'
        post.save(update_fields=['slack_channel', 'slack_ts'])
        return '1.0'

    slack.post_draft.side_effect = post_draft
    slack.caption_override.return_value = None
    return slack


def _decide_on_sleep(n, status='approved'):
    """A sleep seam that plays the owner: on its n-th call it clicks the button
    (i.e. flips the E2E row's status the way social.interact does)."""
    def sleep(_):
        sleep.calls += 1
        if sleep.calls == n:
            SocialPost.objects.filter(iso_week__startswith='E').update(status=status, approved_by='UHUMAN')
    sleep.calls = 0
    return sleep


def _seams(sleep=None, **kw):
    seams = dict(
        build_facts=_build_facts, fetch_image=lambda url: _photo(),
        generate=lambda prompt: json.dumps({'caption': CAPTION}),
        slack=_slack(),
        publishers={'facebook': MagicMock(return_value='111_999')},
        read_post=MagicMock(return_value={'message': f'{CAPTION}\n\nhttps://eatalnicek.eu/…',
                                          'permalink_url': 'https://facebook.com/111/posts/999'}),
        today=TODAY, sleep=sleep or _decide_on_sleep(10 ** 6), stdout=io.StringIO(),
    )
    seams.update(kw)
    return seams


@override_settings(SOCIAL_SLACK_CHANNEL='C1', SLACK_BOT_TOKEN='x')
class SocialE2ECommandTests(TestCase):
    def test_waits_for_approval_then_publishes_to_facebook_only_and_reads_back(self):
        # still a draft on the first two polls, then the owner clicks Schválit
        seams = _seams(sleep=_decide_on_sleep(2))
        call_command('social_e2e', **seams)

        post = SocialPost.objects.get()
        self.assertEqual(post.status, 'published')
        self.assertEqual(post.channels, ['facebook'])
        self.assertEqual(post.facebook_post_id, '111_999')
        self.assertEqual(post.scheduled_for, TODAY)
        self.assertRegex(post.iso_week, r'^E\d{6}$')
        self.assertEqual(seams['sleep'].calls, 2)
        kwargs = seams['publishers']['facebook'].call_args.kwargs
        self.assertEqual(kwargs['caption'], CAPTION)
        self.assertIn('utm_source=facebook', kwargs['link'])
        self.assertIn(post.iso_week, kwargs['link'])
        seams['read_post'].assert_called_once_with('111_999')
        self.assertIn('https://facebook.com/111/posts/999', seams['stdout'].getvalue())
        replies = [c.args[1] for c in seams['slack'].reply.call_args_list]
        self.assertTrue(any('E2E' in r for r in replies))
        self.assertTrue(any('facebook.com/111/posts/999' in r for r in replies))

    def test_does_not_touch_other_due_drafts(self):
        other = SocialPost.objects.create(
            kind='deals', iso_week='2026-W38', scheduled_for=TODAY, caption='Cibule.', image=b'PNG',
            facts={'kind': 'deals', 'link': 'https://eatalnicek.eu/?utm_source={channel}'},
            slack_channel='C1', slack_ts='9.0')
        seams = _seams(sleep=_decide_on_sleep(1))
        call_command('social_e2e', **seams)
        other.refresh_from_db()
        self.assertEqual(other.status, 'draft')
        self.assertEqual(seams['publishers']['facebook'].call_count, 1)

    def test_timeout_rejects_the_draft_so_the_scheduled_job_never_posts_it(self):
        seams = _seams()
        with self.assertRaisesMessage(CommandError, 'no Schválit'):
            call_command('social_e2e', timeout=30, poll=10, **seams)
        post = SocialPost.objects.get()
        self.assertEqual(post.status, 'rejected')
        seams['publishers']['facebook'].assert_not_called()

    def test_rejection_in_slack_fails_without_publishing(self):
        seams = _seams(sleep=_decide_on_sleep(1, 'rejected'))
        with self.assertRaisesMessage(CommandError, 'rejected'):
            call_command('social_e2e', **seams)
        self.assertEqual(SocialPost.objects.get().status, 'rejected')
        seams['publishers']['facebook'].assert_not_called()

    def test_rejected_caption_aborts_before_slack(self):
        seams = _seams(generate=lambda prompt: json.dumps({'caption': 'Sleva 50 % v Lidlu!'}))
        with self.assertRaisesMessage(CommandError, 'caption'):
            call_command('social_e2e', **seams)
        self.assertFalse(SocialPost.objects.exists())
        seams['slack'].post_draft.assert_not_called()

    def test_no_facts_aborts_before_slack(self):
        def no_facts(kind, week):
            raise NoFacts('nothing left to post')
        seams = _seams(build_facts=no_facts)
        with self.assertRaisesMessage(CommandError, 'nothing left to post'):
            call_command('social_e2e', **seams)
        seams['slack'].post_draft.assert_not_called()

    def test_readback_mismatch_fails_but_keeps_the_published_row(self):
        seams = _seams(sleep=_decide_on_sleep(1),
                       read_post=MagicMock(return_value={'message': 'something else', 'permalink_url': 'u'}))
        with self.assertRaisesMessage(CommandError, 'read-back'):
            call_command('social_e2e', **seams)
        self.assertEqual(SocialPost.objects.get().status, 'published')
