"""Sunday job: build next week's three posts from database facts and put them
in Slack for approval.

    python manage.py generate_social_drafts [--week 2026-W37] [--kind deals] [--dry-run]

Exit non-zero when any kind could not be drafted (no facts, or caption failed
validation) so the DO job shows red; drafts that did succeed stay in Slack.
"""
from __future__ import annotations

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from social.captions import CaptionRejected, known_recipe_names, known_shops, write_caption
from social.cards import render_card
from social.facts import NoFacts, build_facts, recipe_photo
from social.models import SocialPost
from social.slack import SlackDrafts, SlackNotConfigured
from social.weeks import KIND_OFFSETS, next_iso_week, prague_today, scheduled_date

DRY_RUN_DIR = Path('social_dry_run')
KINDS = list(KIND_OFFSETS)


class Command(BaseCommand):
    help = 'Draft next week\'s social posts and send them to Slack for approval'
    # Seams for tests, not CLI flags (same pattern as check_llm_health).
    stealth_options = ('build_facts', 'fetch_image', 'generate', 'slack', 'today')

    def add_arguments(self, parser):
        parser.add_argument('--week', help='ISO week like 2026-W37 (default: next week)')
        parser.add_argument('--kind', choices=KINDS, help='only this post kind')
        parser.add_argument('--dry-run', action='store_true',
                            help=f'write PNG + caption to ./{DRY_RUN_DIR}/ and touch neither DB nor Slack')

    def handle(self, *args, **options):
        build = options.get('build_facts') or build_facts
        fetch = options.get('fetch_image')
        generate = options.get('generate')
        today = options.get('today') or prague_today()
        dry_run = options['dry_run']
        week = options.get('week') or next_iso_week(today)
        kinds = [options['kind']] if options.get('kind') else KINDS

        slack = None
        if not dry_run:
            try:
                slack = options.get('slack') or SlackDrafts()
            except SlackNotConfigured as exc:
                raise CommandError(str(exc))

        shops, recipes = known_shops(), known_recipe_names()
        failures = []
        for kind in kinds:
            existing = SocialPost.objects.filter(kind=kind, iso_week=week).first()
            retryable = existing is not None and (
                existing.status == SocialPost.Status.SKIPPED
                or (existing.status == SocialPost.Status.DRAFT and not existing.slack_ts))
            if existing and not retryable and not dry_run:
                self.stdout.write(f'{kind} {week}: already exists ({existing.status}), skipping')
                continue
            outcome = self._draft(kind, week, build, fetch, generate, shops, recipes, slack, dry_run,
                                  existing=None if dry_run else existing)
            self.stdout.write(f'{kind} {week}: {outcome}')
            if outcome != 'draft':
                failures.append(f'{kind}: {outcome}')

        if failures:
            raise CommandError('some posts were not drafted — ' + '; '.join(failures))

    def _draft(self, kind, week, build, fetch, generate, shops, recipes, slack, dry_run,
               existing=None) -> str:
        # A week that ended `skipped` (no facts on Sunday), or a draft whose Slack
        # post never completed (slack_ts empty), is retried on the next run by
        # reusing its row, so the (kind, week) constraint never blocks recovery.
        post = existing or SocialPost(kind=kind, iso_week=week, scheduled_for=scheduled_date(week, kind))
        post.status, post.error = SocialPost.Status.DRAFT, ''
        try:
            facts = build(kind, week)
            photo = None
            if kind == 'recipe':
                photo = recipe_photo(facts, **({'fetch': fetch} if fetch else {}))
        except NoFacts as exc:
            post.status, post.error = SocialPost.Status.SKIPPED, str(exc)
            if not dry_run:
                post.save()
                slack.reply_channel(f'⏭️ *{kind} {week}* skipped — {exc}')
            return f'skipped ({exc})'

        post.facts = facts
        post.image = render_card(kind, facts, photo=photo)
        try:
            written = write_caption(facts, known_shops=shops, known_recipes=recipes,
                                    **({'generate': generate} if generate else {}))
            post.caption, post.group_variant = written['caption'], written['group_variant']
        except CaptionRejected as exc:
            post.caption, post.error = '', f'caption failed validation: {exc}'

        if dry_run:
            DRY_RUN_DIR.mkdir(parents=True, exist_ok=True)
            (DRY_RUN_DIR / f'{kind}-{week}.png').write_bytes(post.image_bytes)
            (DRY_RUN_DIR / f'{kind}-{week}.txt').write_text(
                f'{post.caption or "(caption rejected: " + post.error + ")"}\n\n{post.group_variant}')
            return 'draft' if post.caption else f'draft without caption ({post.error})'

        post.save()
        slack.post_draft(post)
        return 'draft' if post.caption else f'draft without caption ({post.error})'
