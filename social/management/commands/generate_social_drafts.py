"""Evening job (Sun/Tue/Thu): draft the post due tomorrow from database facts
and put it in Slack as a card with Schválit/Zamítnout buttons.

    python manage.py generate_social_drafts [--week 2026-W37] [--kind deals] [--dry-run]

With no options it drafts the one kind whose publish day is tomorrow (Prague)
and does nothing on other days. ``--week`` drafts every kind of that week (a
manual catch-up); ``--kind`` alone drafts that kind for the week of tomorrow.

Exit non-zero when any kind could not be drafted (no facts, an unexpected
error, or a caption that failed validation) so the DO job shows red — and
every such outcome is also announced in the drafts channel, so a failure is
never silent. Kinds that did succeed stay in Slack; one kind's failure never
costs the others.
"""
from __future__ import annotations

import logging
import re
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from social.captions import CaptionRejected, known_recipe_names, known_shops, write_caption
from social.cards import render_card
from social.facts import NoFacts, build_facts, recipe_photo
from social.models import SocialPost
from social.slack import KIND_LABELS, SlackDrafts, SlackNotConfigured
from social.weeks import KIND_OFFSETS, cs_day, due_tomorrow, iso_week, prague_today, scheduled_date

logger = logging.getLogger(__name__)

DRY_RUN_DIR = Path('social_dry_run')
KINDS = list(KIND_OFFSETS)
WEEK_RE = re.compile(r'^\d{4}-W\d{2}$')


class Command(BaseCommand):
    help = 'Draft the social post due tomorrow and send it to Slack for approval'
    # Seams for tests, not CLI flags (same pattern as check_llm_health).
    stealth_options = ('build_facts', 'fetch_image', 'generate', 'slack', 'today')

    def add_arguments(self, parser):
        parser.add_argument('--week', help='ISO week like 2026-W37: draft every kind of that week')
        parser.add_argument('--kind', choices=KINDS, help='only this post kind')
        parser.add_argument('--dry-run', action='store_true',
                            help=f'write PNG + caption to ./{DRY_RUN_DIR}/ and touch neither DB nor '
                                 'Slack; the showcase reuses the last real plan instead of '
                                 'generating one')

    def handle(self, *args, **options):
        build = options.get('build_facts') or build_facts
        fetch = options.get('fetch_image')
        generate = options.get('generate')
        today = options.get('today') or prague_today()
        dry_run = options['dry_run']

        if options.get('week'):
            week = options['week']
            kinds = [options['kind']] if options.get('kind') else KINDS
        elif options.get('kind'):
            week, kinds = iso_week(today + timedelta(days=1)), [options['kind']]
        else:
            due = due_tomorrow(today)
            if due is None:
                self.stdout.write('nothing due tomorrow')
                return
            kinds, week = [due[0]], due[1]
        if not WEEK_RE.match(week):
            raise CommandError('--week must look like 2026-W37')

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
            try:
                outcome = self._draft(kind, week, build, fetch, generate, shops, recipes, slack,
                                      dry_run, today, existing=None if dry_run else existing)
            except Exception as exc:   # one kind's bad day must not cost the other two
                logger.exception('drafting %s %s failed', kind, week)
                outcome = f'errored ({exc.__class__.__name__}: {exc})'
            self.stdout.write(f'{kind} {week}: {outcome}')
            if outcome != 'draft':
                failures.append(f'{kind}: {outcome}')
                if slack is not None:
                    self._announce_failure(slack, kind, week, outcome)

        if failures:
            raise CommandError('some posts were not drafted — ' + '; '.join(failures))

    @staticmethod
    def _announce_failure(slack, kind, week, outcome) -> None:
        """A channel-level note with the owner mentioned: a red DO job alone
        was how W38 went by unnoticed."""
        mention = f' <@{settings.SOCIAL_SLACK_MENTION}>' if settings.SOCIAL_SLACK_MENTION else ''
        slack.reply_channel(f'⚠️ {KIND_LABELS[kind]} na {cs_day(scheduled_date(week, kind))} '
                            f'se nepodařilo připravit — {outcome}{mention}')

    def _draft(self, kind, week, build, fetch, generate, shops, recipes, slack, dry_run, today,
               existing=None) -> str:
        # A week that ended `skipped` (no facts), or a draft whose Slack post
        # never completed (slack_ts empty), is retried on the next run by
        # reusing its row, so the (kind, week) constraint never blocks recovery.
        post = existing or SocialPost(kind=kind, iso_week=week, scheduled_for=scheduled_date(week, kind))
        post.status, post.error = SocialPost.Status.DRAFT, ''
        try:
            # A dry run must never generate a plan; the showcase reads the last real one.
            facts = build(kind, week, publish_day=post.scheduled_for,
                          **({'reuse_latest': True} if dry_run and kind == 'showcase' else {}))
            photo = None
            if kind == 'recipe':
                photo = recipe_photo(facts, **({'fetch': fetch} if fetch else {}))
        except NoFacts as exc:
            post.status, post.error = SocialPost.Status.SKIPPED, str(exc)
            if not dry_run:
                post.save()
            return f'skipped ({exc})'

        post.facts = facts
        post.image = render_card(kind, facts, photo=photo)
        try:
            written = write_caption(facts, known_shops=shops, known_recipes=recipes,
                                    **({'generate': generate} if generate else {}))
            post.caption, post.group_variant = written['caption'], written['group_variant']
        except CaptionRejected as exc:
            post.caption, post.group_variant = '', ''
            post.error = f'caption failed validation: {exc}'

        if dry_run:
            DRY_RUN_DIR.mkdir(parents=True, exist_ok=True)
            (DRY_RUN_DIR / f'{kind}-{week}.png').write_bytes(post.image_bytes)
            (DRY_RUN_DIR / f'{kind}-{week}.txt').write_text(
                f'{post.caption or "(caption rejected: " + post.error + ")"}\n\n{post.group_variant}')
            return 'draft' if post.caption else f'draft without caption ({post.error})'

        post.save()
        slack.post_draft(post, today)
        return 'draft' if post.caption else f'draft without caption ({post.error})'
