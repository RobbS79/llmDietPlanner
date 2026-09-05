import io
import json
import tempfile
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from slack_sdk.errors import SlackApiError

from diet_planner.models import DietaryGoal, DietaryPlan
from social.facts import NoFacts
from social.models import SocialPost
from social.personas import PERSONA_PROMPTS

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


class _ModelError(Exception):
    """Stands in for a transport error out of the Gemini client."""


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

    def test_one_kinds_failure_does_not_cost_the_other_two(self):
        def generate(prompt):
            if '"kind": "deals"' in prompt:
                raise _ModelError('503 model is overloaded')
            return _fake_generate(prompt)
        seams = _seams(generate=generate)
        out = io.StringIO()
        with self.assertRaises(CommandError) as ctx:
            call_command('generate_social_drafts', stdout=out, **seams)
        self.assertIn('errored', str(ctx.exception))
        self.assertIn('errored (_ModelError: 503 model is overloaded)', out.getvalue())
        self.assertEqual(sorted(SocialPost.objects.filter(status='draft')
                                .values_list('kind', flat=True)), ['recipe', 'showcase'])
        # Nothing un-retryable was left behind for deals (the row is either
        # absent or a draft with no Slack message), so the next run recovers it.
        self.assertFalse(SocialPost.objects.filter(kind='deals').exclude(slack_ts='').exists())
        call_command('generate_social_drafts', **_seams())
        deals = SocialPost.objects.get(kind='deals')
        self.assertEqual((deals.status, deals.caption), ('draft', 'Cibule v Lidlu v akci.'))
        self.assertTrue(deals.slack_ts)
        self.assertEqual(SocialPost.objects.count(), 3)

    def test_a_slack_failure_leaves_the_draft_for_the_next_run(self):
        seams = _seams()
        seams['slack'].post_draft.side_effect = SlackApiError('ratelimited', MagicMock())
        with self.assertRaises(CommandError) as ctx:
            call_command('generate_social_drafts', kind='deals', **seams)
        self.assertIn('errored', str(ctx.exception))
        post = SocialPost.objects.get(kind='deals')
        self.assertEqual((post.status, post.slack_ts), ('draft', ''))
        recovered = _seams()
        call_command('generate_social_drafts', kind='deals', **recovered)
        recovered['slack'].post_draft.assert_called_once()
        self.assertEqual(SocialPost.objects.count(), 1)
        self.assertTrue(SocialPost.objects.get(kind='deals').slack_ts)

    def test_a_retry_replaces_the_stale_caption_facts_and_group_variant(self):
        SocialPost.objects.create(kind='deals', iso_week='2026-W37', scheduled_for='2026-09-07',
                                  status='draft', slack_ts='', caption='stale',
                                  facts={'old': 1}, group_variant='old')
        seams = _seams()
        call_command('generate_social_drafts', kind='deals', **seams)
        post = SocialPost.objects.get(kind='deals')
        self.assertEqual(post.caption, 'Cibule v Lidlu v akci.')
        self.assertEqual(post.group_variant, 'Stavím appku.')
        self.assertEqual(post.facts, FACTS['deals'])

    def test_a_rejected_caption_also_clears_a_stale_group_variant(self):
        SocialPost.objects.create(kind='deals', iso_week='2026-W37', scheduled_for='2026-09-07',
                                  status='skipped', group_variant='old', caption='stale')
        seams = _seams(generate=lambda p: json.dumps({'caption': 'Ušetříte 500 Kč!'}))
        with self.assertRaises(CommandError):
            call_command('generate_social_drafts', kind='deals', **seams)
        post = SocialPost.objects.get(kind='deals')
        self.assertEqual((post.caption, post.group_variant), ('', ''))

    def test_a_malformed_week_is_refused_before_anything_happens(self):
        seams = _seams()
        with self.assertRaises(CommandError) as ctx:
            call_command('generate_social_drafts', week='next week', **seams)
        self.assertIn('2026-W37', str(ctx.exception))
        self.assertEqual(SocialPost.objects.count(), 0)
        seams['slack'].post_draft.assert_not_called()

    def test_unconfigured_slack_is_a_command_error(self):
        seams = _seams()
        seams.pop('slack')
        with override_settings(SOCIAL_SLACK_CHANNEL=''):
            with self.assertRaises(CommandError) as ctx:
                call_command('generate_social_drafts', **seams)
        self.assertIn('SOCIAL_SLACK_CHANNEL', str(ctx.exception))
        self.assertEqual(SocialPost.objects.count(), 0)


@override_settings(SOCIAL_SLACK_CHANNEL='C1', SLACK_BOT_TOKEN='x')
class DryRunShowcaseTests(TestCase):
    """The dry run rehearses the real facts layer, so it must not generate a
    plan: the showcase reads the newest completed one instead."""

    def setUp(self):
        self.qa = User.objects.create_user('qa_bot', password='x')
        self.dir = Path(tempfile.mkdtemp())

    def _meal(self, name, calories):
        return {'name': name, 'servings': 2, 'curated_recipe_slug': 'x',
                'nutritional_info': {'calories': calories}, 'ingredients': []}

    def _completed_showcase_goal(self):
        goal = DietaryGoal.objects.create(user=self.qa, prompt=PERSONA_PROMPTS[0], country='CZ',
                                          num_days=1, language_code='cs',
                                          status=DietaryGoal.StatusChoices.COMPLETED)
        DietaryPlan.objects.create(dietary_goal=goal, days=[{
            'day_number': 1,
            'breakfast': self._meal('Ovesná kaše', 700),
            'lunch': self._meal('Kuřecí rizoto', 1240),
            'small_meals': [], 'snacks': [],
        }])
        return goal

    def _run(self):
        seams = dict(generate=_fake_generate, slack=_slack_mock(), today=date(2026, 9, 6))
        out = io.StringIO()
        with patch.dict('os.environ', {'QA_TEST_USERNAME': 'qa_bot'}):
            with patch('social.management.commands.generate_social_drafts.DRY_RUN_DIR', self.dir):
                call_command('generate_social_drafts', dry_run=True, kind='showcase',
                             stdout=out, **seams)
        return out.getvalue()

    def test_dry_run_reads_the_last_real_plan_and_generates_none(self):
        goal = self._completed_showcase_goal()
        self._run()
        self.assertEqual(list(DietaryGoal.objects.values_list('id', flat=True)), [goal.id])
        self.assertTrue((self.dir / 'showcase-2026-W37.png').exists())
        self.assertTrue((self.dir / 'showcase-2026-W37.txt').exists())
        self.assertEqual(SocialPost.objects.count(), 0)

    def test_dry_run_reports_skipped_when_there_is_no_plan_to_reuse(self):
        with self.assertRaises(CommandError) as ctx:
            self._run()
        self.assertIn('no completed showcase plan to reuse', str(ctx.exception))
        self.assertEqual(DietaryGoal.objects.count(), 0)
        self.assertFalse((self.dir / 'showcase-2026-W37.png').exists())
