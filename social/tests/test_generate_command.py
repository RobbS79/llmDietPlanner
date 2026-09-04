import io
import json
import tempfile
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from social.facts import NoFacts
from social.models import SocialPost

FACTS = {
    'deals': {'kind': 'deals', 'iso_week': '2026-W37', 'deals': [{'ingredient': 'cibule', 'shop': 'Lidl', 'valid_until': '2026-09-13'}],
              'recipes': [], 'link': 'https://eatalnicek.eu/?utm_source={channel}&utm_campaign=auto-deals-2026-W37'},
    'recipe': {'kind': 'recipe', 'iso_week': '2026-W37', 'recipe_id': 1, 'name': 'Svíčková', 'kcal': 420, 'minutes': 60,
               'servings': 4, 'source_name': 'Apetit', 'source_url': 'https://apetit.cz', 'deals_matched': 0,
               'deals_total': 5, 'deal_shops': [], 'image_url': 'https://eatalnicek.eu/static/x.webp',
               'link': 'https://eatalnicek.eu/recepty/1/svickova/?utm_source={channel}'},
    'showcase': {'kind': 'showcase', 'iso_week': '2026-W37', 'goal_id': 1, 'prompt': 'Chci zhubnout.',
                 'meals': [{'slot': 'lunch', 'name': 'Rizoto', 'kcal': 600, 'deals_matched': 0}],
                 'total_kcal': 600, 'link': 'https://eatalnicek.eu/?utm_source={channel}'},
}


def _photo():
    from PIL import Image
    buf = io.BytesIO()
    Image.new('RGB', (400, 300), (120, 80, 40)).save(buf, format='WEBP')
    return buf.getvalue()


# The prompt write_caption builds embeds the facts JSON, so the fake model can
# answer per kind — a caption is only honest about the facts it was given.
REPLIES = {
    'deals': {'caption': 'Cibule v Lidlu v akci.', 'group_variant': 'Stavím appku.'},
    'recipe': {'caption': 'Svíčková, hotová za 60 minut. #recept #vareni'},
    'showcase': {'caption': 'Někdo napsal: chci zhubnout. Vařto poskládalo den kolem rizota.'},
}


def _fake_generate(prompt):
    for kind, reply in REPLIES.items():
        if f'"kind": "{kind}"' in prompt:
            return json.dumps(reply)
    raise AssertionError('prompt carried no known kind')


def _slack_mock():
    """Fake with the real SlackDrafts.post_draft contract: it stamps the row
    once the whole thread is up, which is what makes a rerun idempotent."""
    slack = MagicMock()

    def post_draft(post):
        post.slack_channel, post.slack_ts = 'C1', '1700000000.000100'
        post.save(update_fields=['slack_channel', 'slack_ts'])
        return post.slack_ts

    slack.post_draft.side_effect = post_draft
    return slack


def _seams(**overrides):
    seams = dict(
        build_facts=lambda kind, week, **kw: FACTS[kind],
        fetch_image=lambda url: _photo(),
        generate=_fake_generate,
        slack=_slack_mock(),
        today=date(2026, 9, 6),   # a Sunday
    )
    seams.update(overrides)
    return seams


@override_settings(SOCIAL_SLACK_CHANNEL='C1', SLACK_BOT_TOKEN='x')
class GenerateCommandTests(TestCase):
    def test_creates_three_drafts_for_next_week_and_posts_them(self):
        seams = _seams()
        out = io.StringIO()
        call_command('generate_social_drafts', stdout=out, **seams)
        posts = SocialPost.objects.order_by('scheduled_for')
        self.assertEqual([p.kind for p in posts], ['deals', 'recipe', 'showcase'])
        self.assertEqual([str(p.scheduled_for) for p in posts], ['2026-09-07', '2026-09-09', '2026-09-11'])
        self.assertTrue(all(p.iso_week == '2026-W37' for p in posts))
        self.assertTrue(all(p.status == 'draft' for p in posts))
        self.assertTrue(all(p.image for p in posts))
        self.assertEqual(posts[0].group_variant, 'Stavím appku.')
        self.assertEqual(seams['slack'].post_draft.call_count, 3)
        self.assertIn('deals 2026-W37: draft', out.getvalue())

    def test_skipped_week_is_retried_on_next_run(self):
        SocialPost.objects.create(kind='deals', iso_week='2026-W37', scheduled_for='2026-09-07',
                                  status='skipped', error='only 0 ingredients on offer')
        seams = _seams(build_facts=lambda kind, week, **kw: FACTS[kind])
        call_command('generate_social_drafts', kind='deals', **seams)
        post = SocialPost.objects.get(kind='deals')
        self.assertEqual((post.status, post.error), ('draft', ''))
        self.assertTrue(post.image)

    def test_draft_without_slack_message_is_retried(self):
        SocialPost.objects.create(kind='deals', iso_week='2026-W37', scheduled_for='2026-09-07',
                                  status='draft', slack_ts='')
        seams = _seams()
        call_command('generate_social_drafts', kind='deals', **seams)
        seams['slack'].post_draft.assert_called_once()
        self.assertEqual(SocialPost.objects.count(), 1)

    def test_rerun_is_idempotent(self):
        seams = _seams()
        call_command('generate_social_drafts', **seams)
        call_command('generate_social_drafts', **seams)
        self.assertEqual(SocialPost.objects.count(), 3)
        self.assertEqual(seams['slack'].post_draft.call_count, 3)

    def test_no_facts_records_skipped_and_exits_non_zero(self):
        def facts(kind, week, **kw):
            if kind == 'showcase':
                raise NoFacts('plan generation ended failed: LLM down')
            return FACTS[kind]
        seams = _seams(build_facts=facts)
        with self.assertRaises(CommandError):
            call_command('generate_social_drafts', **seams)
        skipped = SocialPost.objects.get(kind='showcase')
        self.assertEqual(skipped.status, 'skipped')
        self.assertIn('LLM down', skipped.error)
        self.assertEqual(SocialPost.objects.filter(status='draft').count(), 2)
        seams['slack'].reply_channel.assert_called_once()

    def test_rejected_caption_still_drafts_with_empty_caption(self):
        seams = _seams(generate=lambda p: json.dumps({'caption': 'Ušetříte 500 Kč!'}))
        with self.assertRaises(CommandError):
            call_command('generate_social_drafts', **seams)
        post = SocialPost.objects.get(kind='deals')
        self.assertEqual(post.status, 'draft')
        self.assertEqual(post.caption, '')
        self.assertIn('caption failed validation', post.error)
        self.assertTrue(post.image)

    def test_week_and_kind_options(self):
        seams = _seams()
        call_command('generate_social_drafts', week='2026-W40', kind='recipe', **seams)
        post = SocialPost.objects.get()
        self.assertEqual((post.kind, post.iso_week, str(post.scheduled_for)), ('recipe', '2026-W40', '2026-09-30'))

    def test_dry_run_writes_files_and_touches_nothing(self):
        seams = _seams()
        with patch('social.management.commands.generate_social_drafts.DRY_RUN_DIR',
                   Path(tempfile.mkdtemp())) as d:
            call_command('generate_social_drafts', dry_run=True, **seams)
            self.assertTrue((d / 'deals-2026-W37.png').exists())
            self.assertTrue((d / 'deals-2026-W37.txt').exists())
        self.assertEqual(SocialPost.objects.count(), 0)
        seams['slack'].post_draft.assert_not_called()
