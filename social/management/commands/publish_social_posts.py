"""Mon/Wed/Fri job: publish every due post whose card was approved.

    python manage.py publish_social_posts [--date 2026-09-09] [--only ID] [--force]

Nothing is published unless the row is `approved` — a Schválit click on the
card (social.interact). A due draft nobody decided on is told so on its card
and retried next run; after STALE_AFTER_DAYS it is rejected. ``--force`` is
for a manual run after a late click: it skips the stale and expired-deals
gates, never the approval itself. Exit non-zero if any post failed or could
not be published, so the DO job shows red.
"""
from __future__ import annotations

from datetime import date

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from social.captions import known_recipe_names, known_shops, validate_caption
from social.models import SocialPost
from social.publishers import PublishError, get_publisher
from social.slack import MISSED_NOTE, SlackDrafts, SlackNotConfigured
from social.weeks import prague_today

STALE_AFTER_DAYS = 7


class Command(BaseCommand):
    help = 'Publish approved social drafts that are due'
    # Seams for tests, not CLI flags (same pattern as generate_social_drafts).
    stealth_options = ('slack', 'publishers', 'today')

    def add_arguments(self, parser):
        parser.add_argument('--date', help='treat this YYYY-MM-DD as today')
        parser.add_argument('--only', type=int, metavar='ID',
                            help='handle just this SocialPost id (social_e2e uses it)')
        parser.add_argument('--force', action='store_true',
                            help='skip the stale and expired-deals gates (still needs Schválit)')

    def handle(self, *args, **options):
        today = (date.fromisoformat(options['date']) if options.get('date')
                 else options.get('today') or prague_today())
        publishers = options.get('publishers') or {}
        try:
            slack = options.get('slack') or SlackDrafts()
        except SlackNotConfigured as exc:
            raise CommandError(str(exc))
        shops, recipes = known_shops(), known_recipe_names()

        due = (SocialPost.objects.filter(scheduled_for__lte=today)
               .exclude(slack_ts='').order_by('scheduled_for'))
        if options.get('only'):
            due = due.filter(pk=options['only'])
        force = bool(options.get('force'))

        for post in due.filter(status=SocialPost.Status.DRAFT):
            self.stdout.write(f'{post.kind} {post.iso_week}: {self._handle_draft(post, today, slack, force)}')

        problems = []
        for post in due.filter(status__in=[SocialPost.Status.APPROVED, SocialPost.Status.FAILED]):
            outcome = self._handle_post(post, today, slack, publishers, shops, recipes, force=force)
            self.stdout.write(f'{post.kind} {post.iso_week}: {outcome}')
            if outcome.startswith(('failed', 'cannot')):
                problems.append(f'{post.kind} {post.iso_week}: {outcome}')
        if problems:
            raise CommandError('; '.join(problems))

    # ------------------------------------------------------------------

    def _handle_draft(self, post, today, slack, force) -> str:
        if not force and (today - post.scheduled_for).days > STALE_AFTER_DAYS:
            return self._reject(post, slack, today, f'stale: unapproved for more than {STALE_AFTER_DAYS} days')
        if post.error != MISSED_NOTE:
            post.error = MISSED_NOTE
            post.save(update_fields=['error'])
            slack.update_card(post, today)
        return 'pending'

    def _handle_post(self, post, today, slack, publishers, shops, recipes, force=False) -> str:
        override = slack.caption_override(post)
        if override:
            violations = validate_caption(override, post.facts, known_shops=shops, known_recipes=recipes)
            if violations:
                slack.reply(post, '⚠️ caption override rejected — ' + '; '.join(violations))
            else:
                post.caption = override
                post.save(update_fields=['caption'])
        if not post.caption:
            slack.update_card(post, today)
            return 'cannot publish: no caption'

        expired = '' if force else self._expired_deals_reason(post, today)
        if expired:
            return self._reject(post, slack, today, expired)

        errors, links = [], []
        for channel in post.pending_channels():
            publish = publishers.get(channel) or get_publisher(channel)
            link = post.facts['link'].replace('{channel}', channel)
            try:
                external_id = publish(caption=post.caption, link=link, image=post.image_bytes,
                                      title=post.facts.get('name', ''))
            except PublishError as exc:
                errors.append(f'{channel}: {exc}')
                continue
            post.set_external_id(channel, external_id)
            links.append(f'{channel}: {external_id}')
            post.save()

        if errors:
            post.status, post.error = SocialPost.Status.FAILED, '; '.join(errors)
            post.save(update_fields=['status', 'error'])
            slack.update_card(post, today)
            return f'failed ({post.error})'

        post.status, post.error, post.published_at = SocialPost.Status.PUBLISHED, '', timezone.now()
        post.save(update_fields=['status', 'error', 'published_at'])
        slack.update_card(post, today)
        return 'published'

    def _reject(self, post, slack, today, reason) -> str:
        post.status, post.error = SocialPost.Status.REJECTED, reason
        post.save(update_fields=['status', 'error'])
        slack.update_card(post, today)
        return f'rejected ({reason})'

    @staticmethod
    def _expired_deals_reason(post, today) -> str:
        if post.kind != 'deals':
            return ''
        deals = post.facts.get('deals') or []
        expired = [d for d in deals if d.get('valid_until') and date.fromisoformat(d['valid_until']) < today]
        if deals and len(expired) * 2 > len(deals):
            return f'{len(expired)} of {len(deals)} offers expired before publish day'
        return ''
