"""Mon/Wed/Fri job: read the Slack decision for every due draft and publish
the approved ones.

    python manage.py publish_social_posts [--date 2026-09-09]

Nothing is published without a ✅ read in this run. Exit non-zero if any
post failed or could not be published, so the DO job shows red.
"""
from __future__ import annotations

from datetime import date

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from social.captions import known_recipe_names, known_shops, validate_caption
from social.models import SocialPost
from social.publishers import PublishError, get_publisher
from social.slack import SlackDrafts, SlackNotConfigured
from social.weeks import prague_today

STALE_AFTER_DAYS = 7
WAITING_NOTE = '⏳ still waiting for ✅ — will retry next run'


class Command(BaseCommand):
    help = 'Publish approved social drafts that are due'
    # Seams for tests, not CLI flags (same pattern as generate_social_drafts).
    stealth_options = ('slack', 'publishers', 'today')

    def add_arguments(self, parser):
        parser.add_argument('--date', help='treat this YYYY-MM-DD as today')

    def handle(self, *args, **options):
        today = (date.fromisoformat(options['date']) if options.get('date')
                 else options.get('today') or prague_today())
        publishers = options.get('publishers') or {}
        try:
            slack = options.get('slack') or SlackDrafts()
        except SlackNotConfigured as exc:
            raise CommandError(str(exc))
        shops, recipes = known_shops(), known_recipe_names()

        due = SocialPost.objects.filter(
            scheduled_for__lte=today,
            status__in=[SocialPost.Status.DRAFT, SocialPost.Status.APPROVED, SocialPost.Status.FAILED],
        ).exclude(slack_ts='').order_by('scheduled_for')

        problems = []
        for post in due:
            outcome = self._handle_post(post, today, slack, publishers, shops, recipes)
            self.stdout.write(f'{post.kind} {post.iso_week}: {outcome}')
            if outcome.startswith(('failed', 'cannot')):
                problems.append(f'{post.kind} {post.iso_week}: {outcome}')
        if problems:
            raise CommandError('; '.join(problems))

    # ------------------------------------------------------------------

    def _handle_post(self, post, today, slack, publishers, shops, recipes) -> str:
        if post.status == SocialPost.Status.DRAFT and (today - post.scheduled_for).days > STALE_AFTER_DAYS:
            return self._reject(post, slack, f'stale: unapproved for more than {STALE_AFTER_DAYS} days')

        decision = slack.read_decision(post)
        if decision.status == 'rejected':
            return self._reject(post, slack, 'rejected in Slack')
        if decision.status == 'pending':
            if WAITING_NOTE not in post.error:
                post.error = WAITING_NOTE
                post.save(update_fields=['error'])
                slack.reply(post, WAITING_NOTE)
            return 'pending'

        if decision.caption_override:
            violations = validate_caption(decision.caption_override, post.facts,
                                          known_shops=shops, known_recipes=recipes)
            if violations:
                slack.reply(post, '⚠️ caption override rejected — ' + '; '.join(violations))
            else:
                post.caption = decision.caption_override
        if not post.caption:
            slack.reply(post, '⚠️ approved but there is no valid caption — reply `caption: …` and I will retry')
            return 'cannot publish: no caption'

        expired = self._expired_deals_reason(post, today)
        if expired:
            return self._reject(post, slack, expired)

        post.status, post.approved_by = SocialPost.Status.APPROVED, decision.approved_by
        post.save(update_fields=['status', 'approved_by', 'caption'])

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
            slack.reply(post, '❌ publish failed — ' + post.error + ('\n✅ ' + ', '.join(links) if links else ''))
            return f'failed ({post.error})'

        post.status, post.error, post.published_at = SocialPost.Status.PUBLISHED, '', timezone.now()
        post.save(update_fields=['status', 'error', 'published_at'])
        slack.reply(post, '✅ published — ' + ', '.join(links))
        return 'published'

    def _reject(self, post, slack, reason) -> str:
        post.status, post.error = SocialPost.Status.REJECTED, reason
        post.save(update_fields=['status', 'error'])
        slack.reply(post, f'🚫 not published — {reason}')
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
