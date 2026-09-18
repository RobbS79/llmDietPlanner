"""Manual end-to-end check of the approval path, against the real Slack
workspace and the real Facebook Page:

    python manage.py social_e2e [--timeout 900] [--poll 10]

Drafts a genuine recipe post, sends it to Slack, waits for a human ✅, then
publishes it through publish_social_posts and reads the post back from the
Graph API. THE POST IS REAL AND STAYS ON THE PAGE — delete it there by hand if
it is unwanted. The row stays `published` too, so the weekly job will not
re-post the same recipe inside RECIPE_REPOST_DAYS. Pinterest is left out.

Exit non-zero when anything short of a verified post happens. A run that gets
no ✅ in time rejects its own draft, so the scheduled job never posts it later.
"""
from __future__ import annotations

import time
from datetime import datetime

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

from social.captions import CaptionRejected, known_recipe_names, known_shops, write_caption
from social.cards import render_card
from social.facts import NoFacts, build_facts, recipe_photo
from social.models import SocialPost
from social.publishers import PublishError
from social.publishers.facebook import read_post
from social.slack import SlackDrafts, SlackNotConfigured
from social.weeks import PRAGUE, prague_today

KIND = 'recipe'
E2E_NOTE = ('🧪 *E2E test run* — ✅ publishes this to the real Facebook Page *right now* '
            '(not on a scheduled day); ❌ cancels the test.')


class Command(BaseCommand):
    help = 'End-to-end test: Slack approval → real Facebook post → Graph read-back'
    # Seams for tests, not CLI flags (same pattern as generate_social_drafts).
    stealth_options = ('build_facts', 'fetch_image', 'generate', 'slack', 'publishers',
                       'read_post', 'today', 'sleep')

    def add_arguments(self, parser):
        parser.add_argument('--timeout', type=int, default=900, help='seconds to wait for ✅ (default 900)')
        parser.add_argument('--poll', type=int, default=10, help='seconds between Slack checks (default 10)')

    def handle(self, *args, **options):
        build = options.get('build_facts') or build_facts
        fetch = options.get('fetch_image')
        generate = options.get('generate')
        read_back = options.get('read_post') or read_post
        sleep = options.get('sleep') or time.sleep
        today = options.get('today') or prague_today()
        try:
            slack = options.get('slack') or SlackDrafts()
        except SlackNotConfigured as exc:
            raise CommandError(str(exc))

        post = self._draft(build, fetch, generate, today)
        slack.post_draft(post)
        slack.reply(post, E2E_NOTE)
        self.stdout.write(f'draft {post.iso_week} (id {post.pk}) is in Slack — react ✅ on it; '
                          f'waiting up to {options["timeout"]}s')

        if not self._wait_for_decision(post, slack, sleep, options['timeout'], options['poll']):
            post.status, post.error = SocialPost.Status.REJECTED, 'e2e: no ✅ before the timeout'
            post.save(update_fields=['status', 'error'])
            slack.reply(post, f'🚫 E2E test gave up — no ✅ within {options["timeout"]}s. Nothing was published.')
            raise CommandError(f'no ✅ within {options["timeout"]}s — draft rejected, nothing published')

        # The real publish path, narrowed to this one row.
        call_command('publish_social_posts', only=post.pk, slack=slack, today=today,
                     publishers=options.get('publishers'), stdout=self.stdout)
        post.refresh_from_db()
        if post.status != SocialPost.Status.PUBLISHED:
            raise CommandError(f'not published: {post.status} — {post.error}')

        try:
            live = read_back(post.facebook_post_id)
        except PublishError as exc:
            raise CommandError(f'published as {post.facebook_post_id} but the read-back failed: {exc}')
        if post.caption.strip() not in (live.get('message') or ''):
            raise CommandError(f'read-back mismatch: post {post.facebook_post_id} does not carry the '
                               f'approved caption (got {(live.get("message") or "")[:120]!r})')

        permalink = live.get('permalink_url') or post.facebook_post_id
        slack.reply(post, f'🧪 E2E verified — the post is live: {permalink}\nDelete it on the Page if you do not want to keep it.')
        self.stdout.write(self.style.SUCCESS(f'E2E OK — {post.facebook_post_id} is live: {permalink}'))

    # ------------------------------------------------------------------

    def _draft(self, build, fetch, generate, today) -> SocialPost:
        # Not an ISO week on purpose: the tag can never collide with a weekly
        # row under the (kind, iso_week) constraint, and it marks the UTM campaign.
        tag = f'E{datetime.now(PRAGUE):%d%H%M}'
        try:
            facts = build(KIND, tag)
            photo = recipe_photo(facts, **({'fetch': fetch} if fetch else {}))
            written = write_caption(facts, known_shops=known_shops(), known_recipes=known_recipe_names(),
                                    **({'generate': generate} if generate else {}))
        except NoFacts as exc:
            raise CommandError(f'no facts to post: {exc}')
        except CaptionRejected as exc:
            raise CommandError(f'caption failed validation, nothing sent to Slack: {exc}')
        return SocialPost.objects.create(
            kind=KIND, iso_week=tag, scheduled_for=today, channels=['facebook'],
            facts=facts, caption=written['caption'], image=render_card(KIND, facts, photo=photo))

    @staticmethod
    def _wait_for_decision(post, slack, sleep, timeout, poll) -> bool:
        """True once Slack shows ✅ or ❌; False when the time runs out."""
        for attempt in range(max(timeout // max(poll, 1), 1)):
            if attempt:
                sleep(poll)
            if slack.read_decision(post).status != 'pending':
                return True
        return False
