"""Slack is the approval UI. A draft is a parent message (caption + how to
decide) with the card uploaded in its thread; ✅ / ❌ reactions on the parent
are the decision; a thread reply starting with `caption:` replaces the text.
Uses the bot token the LLM canary already has. Scopes needed on the app:
chat:write, files:write, reactions:read, channels:history (public channel) or
groups:history (private) — the drafts channel may be private only if
groups:history is granted."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from django.conf import settings
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from .models import SocialPost

logger = logging.getLogger(__name__)

APPROVE = frozenset({'white_check_mark', 'heavy_check_mark', 'ballot_box_with_check'})
REJECT = frozenset({'x', 'heavy_multiplication_x', 'no_entry_sign'})
OVERRIDE_PREFIX = 'caption:'


class SlackNotConfigured(Exception):
    pass


@dataclass(frozen=True)
class Decision:
    status: str                       # 'approved' | 'rejected' | 'pending'
    approved_by: str = ''
    caption_override: Optional[str] = None


def _esc(text: str) -> str:
    return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def draft_text(post: SocialPost) -> str:
    targets = ' + '.join(c.capitalize() for c in post.channels)
    head = f'📅 {post.scheduled_for} · *{post.kind}* · → {targets}'
    if post.caption:
        body = _esc(post.caption)
    else:
        body = f'⚠️ caption failed validation — {_esc(post.error)}\nReply `caption: …` with one, then ✅.'
    return (f'{head}\n\n{body}\n\n'
            f'— react ✅ to approve, ❌ to reject, or reply `{OVERRIDE_PREFIX} …` to replace the text')


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

    def post_draft(self, post: SocialPost) -> str:
        parent = self.client.chat_postMessage(channel=self.channel, text=draft_text(post))
        ts = parent['ts']
        if post.image:
            self.client.files_upload_v2(channel=self.channel, thread_ts=ts,
                                        content=post.image_bytes,
                                        filename=f'{post.kind}-{post.iso_week}.png',
                                        title=f'{post.kind} {post.iso_week}')
        if post.group_variant:
            self.client.chat_postMessage(channel=self.channel, thread_ts=ts,
                                         text=f'*Pro skupiny (vložit ručně):*\n{_esc(post.group_variant)}')
        # Persist slack_ts only once the upload and group reply have both
        # succeeded — a failure above propagates (job goes red) and leaves
        # slack_ts empty so the generator retries the draft on its next run.
        post.slack_channel, post.slack_ts = self.channel, ts
        post.save(update_fields=['slack_channel', 'slack_ts'])
        return ts

    # ---- deciding

    def read_decision(self, post: SocialPost) -> Decision:
        reactions = self.client.reactions_get(channel=post.slack_channel,
                                              timestamp=post.slack_ts)['message'].get('reactions', [])
        approvers, rejected = [], False
        for r in reactions:
            humans = [u for u in r.get('users', []) if u != self.bot_user_id]
            if not humans:
                continue
            if r['name'] in REJECT:
                rejected = True
            elif r['name'] in APPROVE:
                approvers.extend(humans)
        override = self._caption_override(post)
        if rejected:
            return Decision('rejected', '', override)
        if approvers:
            return Decision('approved', approvers[0], override)
        return Decision('pending', '', override)

    def _caption_override(self, post: SocialPost) -> Optional[str]:
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
        try:
            self.client.chat_postMessage(channel=post.slack_channel, thread_ts=post.slack_ts, text=text)
        except SlackApiError as exc:
            logger.warning('slack reply failed for %s: %s', post, exc)

    def reply_channel(self, text: str) -> None:
        """A channel-level note (not in any thread), e.g. 'skipped this week'."""
        try:
            self.client.chat_postMessage(channel=self.channel, text=text)
        except SlackApiError as exc:
            logger.warning('slack channel note failed: %s', exc)
