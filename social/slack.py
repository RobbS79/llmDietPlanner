"""Slack is the approval UI. Every post is ONE Block Kit message: header,
card image, caption, a status line, and — while it is a draft — two buttons.
The message is re-rendered from the database row on every state change
(`update_card`), so what Slack shows is always a function of the row.

Button clicks arrive at social.views.SlackInteractView. A human thread reply
starting with `caption:` still replaces the text (validated at publish time).
Uses the bot token the LLM canary already has. Scopes needed on the app:
chat:write, channels:history (public channel) or groups:history (private) —
plus Interactivity switched on with the request URL pointing at the view."""
from __future__ import annotations

import logging
from datetime import date
from typing import Optional

from django.conf import settings
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from .cards import card_url
from .models import SocialPost
from .weeks import cs_day, prague_today

logger = logging.getLogger(__name__)

APPROVE_ACTION = 'social_approve'
REJECT_ACTION = 'social_reject'
OVERRIDE_PREFIX = 'caption:'
# Stored in .error on a draft the publish job found unapproved; the card then
# says so instead of naming a deadline that has passed.
MISSED_NOTE = 'missed: unapproved when the publish job ran'
KIND_LABELS = {'deals': 'Akce', 'recipe': 'Recept', 'showcase': 'Ukázka jídelníčku'}
KIND_EMOJI = {'deals': '🛒', 'recipe': '🍲', 'showcase': '📅'}
NEXT_RUN = 'při dalším běhu (po/st/pá 9:00)'


class SlackNotConfigured(Exception):
    pass


def _esc(text: str) -> str:
    return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def _who(post: SocialPost) -> str:
    return f' (<@{post.approved_by}>)' if post.approved_by else ''


def _mention() -> str:
    return f' · <@{settings.SOCIAL_SLACK_MENTION}>' if settings.SOCIAL_SLACK_MENTION else ''


def status_line(post: SocialPost, today: Optional[date] = None) -> str:
    """One line that tells the owner what state the post is in and what, if
    anything, is expected of them."""
    today = today or prague_today()
    S = SocialPost.Status
    if post.status == S.DRAFT:
        if not post.caption:
            return '⚠️ Text neprošel kontrolou — odpověz v threadu `caption: …` a pak Schválit' + _mention()
        if post.error == MISSED_NOTE:
            return f'⏳ Nestihlo se · schval a půjde ven {NEXT_RUN}' + _mention()
        return f'⏳ Čeká na schválení · do {cs_day(post.scheduled_for)} 9:00' + _mention()
    if post.status == S.APPROVED:
        if not post.caption:
            return ('⚠️ Schváleno, ale text neprošel kontrolou — odpověz v threadu `caption: …`, '
                    'publikuje se při dalším běhu')
        when = NEXT_RUN if today > post.scheduled_for else f'{cs_day(post.scheduled_for)} 9:00'
        return f'✅ Schváleno{_who(post)} · jde ven {when}'
    if post.status == S.REJECTED:
        return f'🚫 Nepublikováno — {post.error}' if post.error else f'❌ Zamítnuto{_who(post)}'
    if post.status == S.PUBLISHED:
        parts = ['🚀 Publikováno']
        if post.facebook_post_id:
            parts.append(f'https://www.facebook.com/{post.facebook_post_id}')
        if post.pinterest_pin_id:
            parts.append(f'pinterest: {post.pinterest_pin_id}')
        return ' · '.join(parts)
    if post.status == S.FAILED:
        return f'⚠️ Publikování selhalo — {post.error}'
    return f'⏭️ Přeskočeno — {post.error}'


def header_text(post: SocialPost) -> str:
    targets = ' + '.join(c.capitalize() for c in post.channels)
    return f'{KIND_EMOJI[post.kind]} {KIND_LABELS[post.kind]} · {cs_day(post.scheduled_for)} · {targets}'


def draft_blocks(post: SocialPost, today: Optional[date] = None) -> list:
    """The whole card, rendered from the row. Buttons only while it is a draft."""
    body = _esc(post.caption) if post.caption else f'_(bez textu — {_esc(post.error)})_'
    blocks = [{'type': 'header', 'text': {'type': 'plain_text', 'text': header_text(post), 'emoji': True}}]
    if post.image:
        blocks.append({'type': 'image', 'image_url': card_url(post),
                       'alt_text': f'{KIND_LABELS[post.kind]} {post.iso_week}'})
    blocks.append({'type': 'section', 'text': {'type': 'mrkdwn', 'text': body}})
    blocks.append({'type': 'context', 'elements': [{'type': 'mrkdwn', 'text': status_line(post, today)}]})
    if post.status == SocialPost.Status.DRAFT:
        blocks.append({'type': 'actions', 'block_id': f'social-{post.pk}', 'elements': [
            {'type': 'button', 'action_id': APPROVE_ACTION, 'value': str(post.pk), 'style': 'primary',
             'text': {'type': 'plain_text', 'text': '✅ Schválit', 'emoji': True}},
            {'type': 'button', 'action_id': REJECT_ACTION, 'value': str(post.pk), 'style': 'danger',
             'text': {'type': 'plain_text', 'text': '❌ Zamítnout', 'emoji': True}},
        ]})
    return blocks


def fallback_text(post: SocialPost) -> str:
    """Notification/preview text; Slack shows blocks in the channel itself."""
    return f'{header_text(post)}\n{post.caption[:200]}'


class SlackDrafts:
    def __init__(self, client: Optional[WebClient] = None):
        self.channel = settings.SOCIAL_SLACK_CHANNEL
        token = settings.SLACK_BOT_TOKEN
        if not self.channel:
            raise SlackNotConfigured('SOCIAL_SLACK_CHANNEL must be set')
        if client is None and not token:
            raise SlackNotConfigured('SLACK_BOT_TOKEN must be set')
        self.client = client or WebClient(token=token)
        self._bot_user_id: Optional[str] = None

    @property
    def bot_user_id(self) -> str:
        if self._bot_user_id is None:
            self._bot_user_id = self.client.auth_test()['user_id']
        return self._bot_user_id

    # ---- drafting

    def post_draft(self, post: SocialPost, today: Optional[date] = None) -> str:
        parent = self.client.chat_postMessage(channel=self.channel, text=fallback_text(post),
                                              blocks=draft_blocks(post, today))
        ts = parent['ts']
        if post.group_variant:
            self.client.chat_postMessage(channel=self.channel, thread_ts=ts,
                                         text=f'*Pro skupiny (vložit ručně):*\n{_esc(post.group_variant)}')
        # Persist slack_ts only once the group reply has succeeded too — a
        # failure above propagates (job goes red) and leaves slack_ts empty so
        # the generator retries the draft on its next run.
        post.slack_channel, post.slack_ts = self.channel, ts
        post.save(update_fields=['slack_channel', 'slack_ts'])
        return ts

    def update_card(self, post: SocialPost, today: Optional[date] = None) -> None:
        """Re-render the card from the row. Never raises: a failed edit is a
        cosmetic problem, the row is the truth and the next run re-renders."""
        if not post.slack_ts:
            return
        try:
            self.client.chat_update(channel=post.slack_channel, ts=post.slack_ts,
                                    text=fallback_text(post), blocks=draft_blocks(post, today))
        except SlackApiError as exc:
            logger.warning('slack card update failed for %s: %s', post, exc)

    # ---- deciding

    def caption_override(self, post: SocialPost) -> Optional[str]:
        """The last human `caption: …` reply in the thread, or None."""
        messages = self.client.conversations_replies(channel=post.slack_channel,
                                                     ts=post.slack_ts)['messages']
        override = None
        for m in messages:
            text = (m.get('text') or '').strip()
            if m.get('user') != self.bot_user_id and text.lower().startswith(OVERRIDE_PREFIX):
                override = text[len(OVERRIDE_PREFIX):].strip()
        return override or None

    # ---- reporting

    def reply(self, post: SocialPost, text: str) -> None:
        """A thread reply — only for things that are not the card's state
        (the group text, the E2E note, an answer to a human's reply)."""
        try:
            self.client.chat_postMessage(channel=post.slack_channel, thread_ts=post.slack_ts, text=text)
        except SlackApiError as exc:
            logger.warning('slack reply failed for %s: %s', post, exc)

    def reply_channel(self, text: str) -> None:
        """A channel-level note (not in any thread), e.g. 'could not draft'."""
        try:
            self.client.chat_postMessage(channel=self.channel, text=text)
        except SlackApiError as exc:
            logger.warning('slack channel note failed: %s', exc)
