# Social Slack Buttons Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace reaction-based Slack approval with one self-updating Block Kit card per post carrying Schválit/Zamítnout buttons, driven by a signed interactivity endpoint, drafted one at a time the evening before publish day.

**Architecture:** `social/slack.py` renders every card as a pure function of the `SocialPost` row (`draft_blocks`) and edits it in place (`update_card`); `social/interact.py` verifies Slack's signature and flips the row's status; `SocialPost.status` becomes the only decision source for `publish_social_posts`. The generator drafts only the kind due tomorrow and never fails silently.

**Tech Stack:** Django 5 + DRF `APIView`, `slack_sdk` 3.42 (`chat_postMessage`, `chat_update`), Block Kit, HMAC-SHA256 signing, pytest (`python3 -m pytest social -q`).

Spec: `docs/superpowers/specs/2026-09-24-social-slack-buttons-design.md`.

---

## File map

| File | Responsibility |
|---|---|
| `llm_diet_planner_project/settings.py` | + `SLACK_SIGNING_SECRET`, `SOCIAL_SLACK_MENTION` |
| `social/weeks.py` | + `due_tomorrow(today)`, `cs_day(d)`; − `next_iso_week` |
| `social/cards.py` | + `card_signature(pk)`, `card_url(post)` |
| `social/slack.py` | rewrite: `draft_blocks`, `status_line`, `post_draft` (blocks), `update_card`, `caption_override`; − reactions |
| `social/interact.py` | new: `verify_slack_signature`, `handle_action` |
| `social/views.py` | new: `SlackInteractView`, `card_png` |
| `social/urls.py` | new; wired at `api/social/` |
| `social/facts.py` | `deals_facts(iso_week, publish_day)` filter |
| `social/management/commands/generate_social_drafts.py` | tomorrow-kind default, channel warning on every non-draft outcome |
| `social/management/commands/publish_social_posts.py` | status-driven, cards not thread replies |
| `social/management/commands/social_e2e.py` | wait on DB status |
| `social/migrations/0002_reject_reaction_era_drafts.py` | data migration |
| `docs/social-pipeline-ops.md` | runbook §1, §4, §5, §7, §8 |
| tests | `test_weeks.py`, `test_slack.py`, `test_views.py` (new), `test_facts.py`, `test_generate_command.py`, `test_publish_command.py`, `test_e2e_command.py`, `test_migration_0002.py` (new) |

Run tests with: `cd /opt/llmDietPlanner && python3 -m pytest social -q` (178 pass at start).

---

### Task 1: settings + week helpers

**Files:** Modify `llm_diet_planner_project/settings.py:377`, `social/weeks.py`, `social/tests/test_weeks.py`

- [ ] **Step 1: failing tests** — replace the `next_iso_week` tests in `social/tests/test_weeks.py` with:

```python
from social.weeks import (KIND_OFFSETS, cs_day, due_tomorrow, iso_week, prague_today,
                          scheduled_date, week_start)

def test_due_tomorrow_picks_the_kind_whose_day_is_tomorrow():
    assert due_tomorrow(date(2026, 9, 6)) == ('deals', '2026-W37')      # Sunday → Monday deals
    assert due_tomorrow(date(2026, 9, 8)) == ('recipe', '2026-W37')     # Tuesday → Wednesday
    assert due_tomorrow(date(2026, 9, 10)) == ('showcase', '2026-W37')  # Thursday → Friday
    assert due_tomorrow(date(2026, 9, 7)) is None                       # Monday → Tuesday: nothing

def test_due_tomorrow_crosses_iso_year():
    assert due_tomorrow(date(2026, 12, 27)) == ('deals', '2026-W53')

def test_cs_day_is_czech_weekday_and_day_month():
    assert cs_day(date(2026, 9, 23)) == 'středa 23. 9.'
    assert cs_day(date(2026, 9, 21)) == 'pondělí 21. 9.'
```
(also update `test_iso_year_can_differ_from_calendar_year`: drop its `next_iso_week` line.)

- [ ] **Step 2:** `python3 -m pytest social/tests/test_weeks.py -q` → ImportError.
- [ ] **Step 3:** in `social/weeks.py` delete `next_iso_week`, add:

```python
WEEKDAYS_CS = ('pondělí', 'úterý', 'středa', 'čtvrtek', 'pátek', 'sobota', 'neděle')

def due_tomorrow(today: date):
    """(kind, iso_week) whose publish day is tomorrow, or None. The generator
    runs the evening before each publish day and drafts exactly that post."""
    tomorrow = today + timedelta(days=1)
    week = iso_week(tomorrow)
    for kind in KIND_OFFSETS:
        if scheduled_date(week, kind) == tomorrow:
            return kind, week
    return None

def cs_day(d: date) -> str:
    return f'{WEEKDAYS_CS[d.weekday()]} {d.day}. {d.month}.'
```
and in settings after `SOCIAL_SLACK_CHANNEL`:
```python
SLACK_SIGNING_SECRET = config('SLACK_SIGNING_SECRET', default='')   # Slack app → Basic Information
SOCIAL_SLACK_MENTION = config('SOCIAL_SLACK_MENTION', default='')   # owner's Slack user id, @mentioned on cards
```
- [ ] **Step 4:** tests pass. **Step 5:** `git commit -m "feat(social): due_tomorrow/cs_day helpers, signing-secret + mention settings"`

### Task 2: signed card URL + card view + urls

**Files:** Modify `social/cards.py`; Create `social/views.py`, `social/urls.py`, `social/tests/test_views.py`; Modify `llm_diet_planner_project/urls.py:38`

- [ ] **Step 1: failing tests** `social/tests/test_views.py`:

```python
import hmac, json, time
from hashlib import sha256
from unittest.mock import MagicMock, patch
from urllib.parse import urlencode
from django.test import TestCase, override_settings
from social.cards import card_signature, card_url
from social.models import SocialPost

def _post(**kw):
    d = dict(kind='recipe', iso_week='2026-W39', scheduled_for='2026-09-23', caption='Tofu kari.',
             image=b'\x89PNG', slack_channel='C1', slack_ts='1.0')
    d.update(kw); return SocialPost.objects.create(**d)

class CardUrlTests(TestCase):
    def test_url_is_site_plus_signed_path(self):
        post = _post()
        url = card_url(post)
        self.assertTrue(url.startswith('https://eatalnicek.eu/api/social/card/'))
        self.assertTrue(url.endswith(f'/{card_signature(post.pk)}.png'))
        self.assertEqual(len(card_signature(post.pk)), 32)
    def test_card_served_with_valid_signature(self):
        post = _post()
        r = self.client.get(f'/api/social/card/{post.pk}/{card_signature(post.pk)}.png')
        self.assertEqual(r.status_code, 200); self.assertEqual(r['Content-Type'], 'image/png')
        self.assertEqual(r.content, b'\x89PNG')
    def test_bad_signature_missing_row_or_missing_image_are_404(self):
        post = _post(); empty = _post(iso_week='2026-W40', image=None)
        self.assertEqual(self.client.get(f'/api/social/card/{post.pk}/{"0"*32}.png').status_code, 404)
        self.assertEqual(self.client.get(f'/api/social/card/999/{card_signature(999)}.png').status_code, 404)
        self.assertEqual(self.client.get(f'/api/social/card/{empty.pk}/{card_signature(empty.pk)}.png').status_code, 404)
```
- [ ] **Step 2:** run → ImportError.
- [ ] **Step 3:** `social/cards.py` add (top-level, after imports; `from django.conf import settings`, `import hmac`, `from hashlib import sha256`):

```python
def card_signature(post_id: int) -> str:
    """Unguessable path segment so cards are fetchable by Slack but not enumerable."""
    return hmac.new(settings.SECRET_KEY.encode(), f'social-card:{post_id}'.encode(), sha256).hexdigest()[:32]

def card_url(post) -> str:
    return f'{settings.SOCIAL_SITE_URL.rstrip("/")}/api/social/card/{post.pk}/{card_signature(post.pk)}.png'
```
`social/views.py`:
```python
"""HTTP surface of the social pipeline: the card image Slack embeds, and the
button clicks Slack sends back. Both are unauthenticated by design — the card
path is signed, the interaction body is signed."""
import hmac, logging
from django.http import Http404, HttpResponse
from django.views.decorators.http import require_GET
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from .cards import card_signature
from .models import SocialPost

@require_GET
def card_png(request, pk: int, sig: str):
    if not hmac.compare_digest(sig, card_signature(pk)):
        raise Http404
    post = SocialPost.objects.filter(pk=pk).only('image').first()
    if post is None or not post.image:
        raise Http404
    response = HttpResponse(post.image_bytes, content_type='image/png')
    response['Cache-Control'] = 'public, max-age=86400'
    return response
```
(`SlackInteractView` is added in Task 4.) `social/urls.py`:
```python
from django.urls import path
from . import views
app_name = 'social'
urlpatterns = [
    path('card/<int:pk>/<slug:sig>.png', views.card_png, name='card'),
]
```
project `urls.py`: after the billing line add `path("api/social/", include("social.urls")),`.
- [ ] **Step 4:** pass. **Step 5:** commit `feat(social): signed card image endpoint`.

### Task 3: Block Kit cards in `social/slack.py`

**Files:** Rewrite `social/slack.py`; rewrite `social/tests/test_slack.py`

- [ ] **Step 1: failing tests** — new `test_slack.py` (keep `_slack_api_error`, `UnconfiguredTests`; drop `ReadDecisionTests`):

```python
from datetime import date
from social.slack import MISSED_NOTE, SlackDrafts, draft_blocks, status_line
def _client(replies=None, bot_id='UBOT'):
    client = MagicMock(); client.auth_test.return_value = {'user_id': bot_id}
    client.chat_postMessage.return_value = {'ts': '1700000000.000100'}
    client.chat_update.return_value = {'ok': True}
    client.conversations_replies.return_value = {'messages': replies or []}
    return client
def _post(**kw): (as before, kind='deals', scheduled_for='2026-09-07', ...)
TODAY = date(2026, 9, 6)

@override_settings(SOCIAL_SLACK_CHANNEL='C123', SLACK_BOT_TOKEN='xoxb-test', SOCIAL_SLACK_MENTION='UOWNER')
class DraftBlocksTests(TestCase):
    def _types(self, post): return [b['type'] for b in draft_blocks(post, today=TODAY)]
    def test_draft_card_has_header_image_caption_status_and_buttons(self):
        post = _post(); blocks = draft_blocks(post, today=TODAY)
        self.assertEqual([b['type'] for b in blocks], ['header', 'image', 'section', 'context', 'actions'])
        self.assertEqual(blocks[0]['text']['text'], '🛒 Akce · pondělí 7. 9. · Facebook')
        self.assertIn(f'/api/social/card/{post.pk}/', blocks[1]['image_url'])
        self.assertEqual(blocks[2]['text']['text'], 'Cibule je v akci.')
        self.assertEqual(blocks[3]['elements'][0]['text'], '⏳ Čeká na schválení · do pondělí 7. 9. 9:00 · <@UOWNER>')
        ids = [e['action_id'] for e in blocks[4]['elements']]
        self.assertEqual(ids, ['social_approve', 'social_reject'])
        self.assertEqual({e['value'] for e in blocks[4]['elements']}, {str(post.pk)})
    def test_recipe_header_names_both_channels(self):
        post = _post(kind='recipe', scheduled_for='2026-09-09')
        self.assertEqual(draft_blocks(post, today=TODAY)[0]['text']['text'], '🍲 Recept · středa 9. 9. · Facebook + Pinterest')
    def test_no_image_block_without_image(self):
        self.assertNotIn('image', self._types(_post(image=None)))
    def test_mention_omitted_when_unset(self):
        with override_settings(SOCIAL_SLACK_MENTION=''):
            self.assertEqual(status_line(_post(), today=TODAY), '⏳ Čeká na schválení · do pondělí 7. 9. 9:00')
    def test_missed_draft_says_so_and_keeps_buttons(self):
        post = _post(error=MISSED_NOTE)
        self.assertEqual(status_line(post, today=date(2026, 9, 7)), '⏳ Nestihlo se · schval a půjde ven při dalším běhu (po/st/pá 9:00) · <@UOWNER>')
        self.assertIn('actions', self._types(post))
    def test_draft_without_caption_asks_for_override_and_keeps_buttons(self):
        post = _post(caption='', error='caption failed validation: number 9,90')
        self.assertEqual(status_line(post, today=TODAY), '⚠️ Text neprošel kontrolou — odpověz v threadu `caption: …` a pak Schválit · <@UOWNER>')
        blocks = draft_blocks(post, today=TODAY)
        self.assertIn('actions', [b['type'] for b in blocks])
        self.assertIn('number 9,90', blocks[2]['text']['text'])
    def test_approved_has_no_buttons_and_names_publish_day(self):
        post = _post(status='approved', approved_by='UHUMAN')
        self.assertEqual(status_line(post, today=TODAY), '✅ Schváleno (<@UHUMAN>) · jde ven pondělí 7. 9. 9:00')
        self.assertNotIn('actions', self._types(post))
    def test_approved_after_its_day_goes_out_next_run(self):
        post = _post(status='approved', approved_by='UHUMAN')
        self.assertEqual(status_line(post, today=date(2026, 9, 8)), '✅ Schváleno (<@UHUMAN>) · jde ven při dalším běhu (po/st/pá 9:00)')
    def test_approved_without_caption_waits_for_override(self):
        post = _post(status='approved', approved_by='UHUMAN', caption='')
        self.assertEqual(status_line(post, today=TODAY), '⚠️ Schváleno, ale text neprošel kontrolou — odpověz v threadu `caption: …`, publikuje se při dalším běhu')
    def test_rejected_by_button_vs_by_gate(self):
        self.assertEqual(status_line(_post(status='rejected', approved_by='UHUMAN'), today=TODAY), '❌ Zamítnuto (<@UHUMAN>)')
        self.assertEqual(status_line(_post(status='rejected', error='6 of 8 offers expired before publish day'), today=TODAY), '🚫 Nepublikováno — 6 of 8 offers expired before publish day')
    def test_published_links_facebook_and_pinterest(self):
        post = _post(kind='recipe', status='published', facebook_post_id='111_999', pinterest_pin_id='pin42')
        self.assertEqual(status_line(post, today=TODAY), '🚀 Publikováno · https://www.facebook.com/111_999 · pinterest: pin42')
        self.assertEqual(status_line(_post(status='published', facebook_post_id='111_999'), today=TODAY), '🚀 Publikováno · https://www.facebook.com/111_999')
    def test_failed_and_skipped(self):
        self.assertEqual(status_line(_post(status='failed', error='facebook: 400 bad token'), today=TODAY), '⚠️ Publikování selhalo — facebook: 400 bad token')
        self.assertEqual(status_line(_post(status='skipped', error='no deals'), today=TODAY), '⏭️ Přeskočeno — no deals')
    def test_caption_is_mrkdwn_escaped(self):
        blocks = draft_blocks(_post(caption='Ovoce & zelenina <akce>'), today=TODAY)
        self.assertEqual(blocks[2]['text']['text'], 'Ovoce &amp; zelenina &lt;akce&gt;')

@override_settings(SOCIAL_SLACK_CHANNEL='C123', SLACK_BOT_TOKEN='xoxb-test')
class PostDraftTests(TestCase):
    def test_posts_blocks_with_fallback_text_then_group_reply_and_stores_ts(self):
        client = _client(); post = _post(slack_ts='', slack_channel='')
        SlackDrafts(client=client).post_draft(post)
        post.refresh_from_db()
        self.assertEqual((post.slack_ts, post.slack_channel), ('1700000000.000100', 'C123'))
        parent = client.chat_postMessage.call_args_list[0].kwargs
        self.assertEqual(parent['blocks'][0]['type'], 'header')
        self.assertIn('Cibule je v akci.', parent['text'])
        self.assertNotIn('thread_ts', parent)
        group = client.chat_postMessage.call_args_list[1].kwargs
        self.assertEqual(group['thread_ts'], '1700000000.000100'); self.assertIn('Stavím appku', group['text'])
        client.files_upload_v2.assert_not_called()
    def test_group_reply_failure_leaves_ts_empty_and_propagates(self):
        client = _client(); client.chat_postMessage.side_effect = [{'ts': '1700000000.000100'}, _slack_api_error()]
        post = _post(slack_ts='', slack_channel='')
        with self.assertRaises(SlackApiError): SlackDrafts(client=client).post_draft(post)
        post.refresh_from_db(); self.assertEqual(post.slack_ts, '')
    def test_no_group_reply_when_group_variant_empty(self):
        client = _client(); SlackDrafts(client=client).post_draft(_post(slack_ts='', slack_channel='', group_variant=''))
        self.assertEqual(client.chat_postMessage.call_count, 1)

@override_settings(SOCIAL_SLACK_CHANNEL='C123', SLACK_BOT_TOKEN='xoxb-test')
class UpdateCardTests(TestCase):
    def test_update_card_edits_the_message_in_place(self):
        client = _client(); post = _post(status='published', facebook_post_id='111_999')
        SlackDrafts(client=client).update_card(post, today=TODAY)
        kw = client.chat_update.call_args.kwargs
        self.assertEqual((kw['channel'], kw['ts']), ('C123', '1700000000.000100'))
        self.assertIn('Publikováno', kw['blocks'][-1]['elements'][0]['text'])
        self.assertNotIn('actions', [b['type'] for b in kw['blocks']])
    def test_update_card_swallows_slack_errors_and_skips_rows_without_message(self):
        client = _client(); client.chat_update.side_effect = _slack_api_error()
        SlackDrafts(client=client).update_card(_post(), today=TODAY)          # must not raise
        client.chat_update.reset_mock()
        SlackDrafts(client=client).update_card(_post(slack_ts='', iso_week='2026-W40'), today=TODAY)
        client.chat_update.assert_not_called()

@override_settings(SOCIAL_SLACK_CHANNEL='C123', SLACK_BOT_TOKEN='xoxb-test')
class CaptionOverrideTests(TestCase):
    def test_last_human_caption_reply_wins(self):
        client = _client(replies=[{'ts': '1', 'text': 'parent', 'user': 'UBOT'},
                                  {'ts': '2', 'text': 'caption: první verze', 'user': 'UHUMAN'},
                                  {'ts': '3', 'text': 'Caption:  Cibule je tenhle týden v akci v Lidlu.', 'user': 'UHUMAN'},
                                  {'ts': '4', 'text': 'nice', 'user': 'UHUMAN'}])
        self.assertEqual(SlackDrafts(client=client).caption_override(_post()), 'Cibule je tenhle týden v akci v Lidlu.')
    def test_bot_caption_reply_is_ignored_and_none_when_absent(self):
        client = _client(replies=[{'ts': '2', 'text': 'caption: lidský návrh', 'user': 'UHUMAN'},
                                  {'ts': '3', 'text': 'caption: bot návrh', 'user': 'UBOT'}])
        self.assertEqual(SlackDrafts(client=client).caption_override(_post()), 'lidský návrh')
        self.assertIsNone(SlackDrafts(client=_client()).caption_override(_post()))
    (+ keep test_reply_posts_in_thread, test_reply_swallows_slack_api_error, test_reply_channel_posts_without_thread)
```
- [ ] **Step 2:** run → fails. **Step 3:** rewrite `social/slack.py`:

```python
"""Slack is the approval UI. Every post is ONE Block Kit message: header,
card image, caption, a status line, and (while it is a draft) two buttons.
The message is re-rendered from the database row on every state change
(`update_card`), so what Slack shows is always a function of the row.
Button clicks arrive at social.views.SlackInteractView. A human thread reply
starting with `caption:` still replaces the text (validated at publish)."""
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
APPROVE_ACTION, REJECT_ACTION = 'social_approve', 'social_reject'
OVERRIDE_PREFIX = 'caption:'
MISSED_NOTE = 'missed: unapproved when the publish job ran'   # stored in .error on a draft
KIND_LABELS = {'deals': 'Akce', 'recipe': 'Recept', 'showcase': 'Ukázka jídelníčku'}
KIND_EMOJI = {'deals': '🛒', 'recipe': '🍲', 'showcase': '📅'}
NEXT_RUN = 'při dalším běhu (po/st/pá 9:00)'

class SlackNotConfigured(Exception): pass

def _esc(text): return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
def _who(post): return f' (<@{post.approved_by}>)' if post.approved_by else ''
def _mention(): return f' · <@{settings.SOCIAL_SLACK_MENTION}>' if settings.SOCIAL_SLACK_MENTION else ''

def status_line(post: SocialPost, today: Optional[date] = None) -> str:
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
            return '⚠️ Schváleno, ale text neprošel kontrolou — odpověz v threadu `caption: …`, publikuje se při dalším běhu'
        when = NEXT_RUN if today > post.scheduled_for else f'{cs_day(post.scheduled_for)} 9:00'
        return f'✅ Schváleno{_who(post)} · jde ven {when}'
    if post.status == S.REJECTED:
        return f'🚫 Nepublikováno — {post.error}' if post.error else f'❌ Zamítnuto{_who(post)}'
    if post.status == S.PUBLISHED:
        parts = ['🚀 Publikováno']
        if post.facebook_post_id: parts.append(f'https://www.facebook.com/{post.facebook_post_id}')
        if post.pinterest_pin_id: parts.append(f'pinterest: {post.pinterest_pin_id}')
        return ' · '.join(parts)
    if post.status == S.FAILED:
        return f'⚠️ Publikování selhalo — {post.error}'
    return f'⏭️ Přeskočeno — {post.error}'

def header_text(post): 
    targets = ' + '.join(c.capitalize() for c in post.channels)
    return f'{KIND_EMOJI[post.kind]} {KIND_LABELS[post.kind]} · {cs_day(post.scheduled_for)} · {targets}'

def draft_blocks(post: SocialPost, today: Optional[date] = None) -> list:
    body = _esc(post.caption) if post.caption else f'_(bez textu — {_esc(post.error)})_'
    blocks = [{'type': 'header', 'text': {'type': 'plain_text', 'text': header_text(post), 'emoji': True}}]
    if post.image:
        blocks.append({'type': 'image', 'image_url': card_url(post), 'alt_text': f'{KIND_LABELS[post.kind]} {post.iso_week}'})
    blocks.append({'type': 'section', 'text': {'type': 'mrkdwn', 'text': body}})
    blocks.append({'type': 'context', 'elements': [{'type': 'mrkdwn', 'text': status_line(post, today)}]})
    if post.status == SocialPost.Status.DRAFT:
        blocks.append({'type': 'actions', 'block_id': f'social-{post.pk}', 'elements': [
            {'type': 'button', 'action_id': APPROVE_ACTION, 'value': str(post.pk), 'style': 'primary',
             'text': {'type': 'plain_text', 'text': '✅ Schválit', 'emoji': True}},
            {'type': 'button', 'action_id': REJECT_ACTION, 'value': str(post.pk), 'style': 'danger',
             'text': {'type': 'plain_text', 'text': '❌ Zamítnout', 'emoji': True}}]})
    return blocks

def fallback_text(post): return f'{header_text(post)}\n{post.caption[:200]}'

class SlackDrafts:
    __init__ / bot_user_id: unchanged
    def post_draft(self, post, today=None) -> str:
        parent = self.client.chat_postMessage(channel=self.channel, text=fallback_text(post), blocks=draft_blocks(post, today))
        ts = parent['ts']
        if post.group_variant:
            self.client.chat_postMessage(channel=self.channel, thread_ts=ts, text=f'*Pro skupiny (vložit ručně):*\n{_esc(post.group_variant)}')
        post.slack_channel, post.slack_ts = self.channel, ts
        post.save(update_fields=['slack_channel', 'slack_ts'])
        return ts
    def update_card(self, post, today=None) -> None:
        """Re-render the card from the row. Never raises: a failed edit is a
        cosmetic problem, the row is the truth and the next run re-renders."""
        if not post.slack_ts: return
        try:
            self.client.chat_update(channel=post.slack_channel, ts=post.slack_ts, text=fallback_text(post), blocks=draft_blocks(post, today))
        except SlackApiError as exc:
            logger.warning('slack card update failed for %s: %s', post, exc)
    def caption_override(self, post) -> Optional[str]:   # body of old _caption_override
    reply / reply_channel: unchanged
```
- [ ] **Step 4:** `python3 -m pytest social/tests/test_slack.py social/tests/test_views.py -q` pass (other suites break until Tasks 6–8). **Step 5:** commit `feat(social): Block Kit cards with buttons, update_card`.

### Task 4: interactivity endpoint

**Files:** Create `social/interact.py`; Modify `social/views.py`, `social/urls.py`, `social/tests/test_views.py`

- [ ] **Step 1: failing tests** (append to `test_views.py`):

```python
from social.interact import handle_action, verify_slack_signature
SECRET = 's3cret'
def _sign(body: bytes, ts=None, secret=SECRET):
    ts = ts or str(int(time.time()))
    return ts, 'v0=' + hmac.new(secret.encode(), f'v0:{ts}:'.encode() + body, sha256).hexdigest()
def _body(action_id, value, user='UHUMAN', kind='block_actions'):
    return urlencode({'payload': json.dumps({'type': kind, 'user': {'id': user},
                                             'actions': [{'action_id': action_id, 'value': str(value)}]})}).encode()

class VerifySignatureTests(TestCase):
    def test_valid_stale_and_wrong(self):
        body = b'payload=%7B%7D'; ts, sig = _sign(body)
        self.assertTrue(verify_slack_signature(SECRET, ts, sig, body))
        self.assertFalse(verify_slack_signature('other', ts, sig, body))
        self.assertFalse(verify_slack_signature(SECRET, ts, sig, body + b'x'))
        old_ts, old_sig = _sign(body, ts=str(int(time.time()) - 400))
        self.assertFalse(verify_slack_signature(SECRET, old_ts, old_sig, body))
        self.assertFalse(verify_slack_signature(SECRET, 'notanumber', sig, body))

@override_settings(SLACK_SIGNING_SECRET=SECRET, SOCIAL_SLACK_CHANNEL='C1', SLACK_BOT_TOKEN='x')
class InteractViewTests(TestCase):
    URL = '/api/social/slack/interact/'
    def setUp(self):
        p = patch('social.interact.SlackDrafts'); self.drafts = p.start().return_value; self.addCleanup(p.stop)
    def _send(self, body, headers=None):
        ts, sig = _sign(body)
        return self.client.post(self.URL, data=body, content_type='application/x-www-form-urlencoded',
                                **(headers or {'HTTP_X_SLACK_REQUEST_TIMESTAMP': ts, 'HTTP_X_SLACK_SIGNATURE': sig}))
    def test_approve_sets_status_and_updates_card(self):
        post = _post(); r = self._send(_body('social_approve', post.pk))
        self.assertEqual(r.status_code, 200); post.refresh_from_db()
        self.assertEqual((post.status, post.approved_by, post.error), ('approved', 'UHUMAN', ''))
        self.drafts.update_card.assert_called_once()
        self.assertEqual(self.drafts.update_card.call_args.args[0].pk, post.pk)
    def test_reject_sets_status(self):
        post = _post(); self._send(_body('social_reject', post.pk)); post.refresh_from_db()
        self.assertEqual((post.status, post.approved_by), ('rejected', 'UHUMAN'))
    def test_second_click_only_refreshes(self):
        post = _post(status='approved', approved_by='UFIRST')
        self._send(_body('social_reject', post.pk)); post.refresh_from_db()
        self.assertEqual((post.status, post.approved_by), ('approved', 'UFIRST'))
        self.drafts.update_card.assert_called_once()
    def test_bad_signature_is_400_and_changes_nothing(self):
        post = _post(); body = _body('social_approve', post.pk); ts, _ = _sign(body)
        r = self.client.post(self.URL, data=body, content_type='application/x-www-form-urlencoded',
                             HTTP_X_SLACK_REQUEST_TIMESTAMP=ts, HTTP_X_SLACK_SIGNATURE='v0=bad')
        self.assertEqual(r.status_code, 400); post.refresh_from_db(); self.assertEqual(post.status, 'draft')
    def test_unset_secret_is_503(self):
        with override_settings(SLACK_SIGNING_SECRET=''):
            self.assertEqual(self._send(_body('social_approve', 1)).status_code, 503)
    def test_unknown_post_other_payload_types_and_garbage_are_200_noops(self):
        self.assertEqual(self._send(_body('social_approve', 999)).status_code, 200)
        self.assertEqual(self._send(_body('social_approve', 1, kind='view_submission')).status_code, 200)
        self.assertEqual(self._send(b'payload=not-json').status_code, 200)
        self.drafts.update_card.assert_not_called()
    def test_card_update_failure_does_not_undo_the_decision(self):
        self.drafts.update_card.side_effect = RuntimeError('slack down')
        post = _post(); r = self._send(_body('social_approve', post.pk))
        self.assertEqual(r.status_code, 200); post.refresh_from_db(); self.assertEqual(post.status, 'approved')
```
- [ ] **Step 2:** run → ImportError. **Step 3:** `social/interact.py`:

```python
"""Slack interactivity: signature check + what a button click does to a row."""
from __future__ import annotations
import hmac, logging, time
from hashlib import sha256
from typing import Optional
from .models import SocialPost
from .slack import APPROVE_ACTION, REJECT_ACTION, SlackDrafts, SlackNotConfigured
logger = logging.getLogger(__name__)
MAX_SKEW_SECONDS = 300

def verify_slack_signature(secret: str, timestamp: str, signature: str, body: bytes, now: Optional[float] = None) -> bool:
    """Slack's v0 scheme: HMAC-SHA256(secret, 'v0:<ts>:<body>'), plus a replay window."""
    if not (secret and timestamp.isdigit() and signature):
        return False
    if abs((now or time.time()) - int(timestamp)) > MAX_SKEW_SECONDS:
        return False
    expected = 'v0=' + hmac.new(secret.encode(), f'v0:{timestamp}:'.encode() + body, sha256).hexdigest()
    return hmac.compare_digest(expected, signature)

def handle_action(action_id: str, value: str, user_id: str) -> str:
    """Returns 'approved' | 'rejected' | 'refreshed' | 'ignored'. The status
    change is saved before the card is redrawn, and a redraw failure is logged,
    never raised — the row is the truth."""
    if action_id not in (APPROVE_ACTION, REJECT_ACTION) or not str(value).isdigit():
        return 'ignored'
    post = SocialPost.objects.filter(pk=int(value)).first()
    if post is None:
        return 'ignored'
    outcome = 'refreshed'
    if post.status == SocialPost.Status.DRAFT:
        post.status = SocialPost.Status.APPROVED if action_id == APPROVE_ACTION else SocialPost.Status.REJECTED
        post.approved_by, post.error = user_id[:32], ''
        post.save(update_fields=['status', 'approved_by', 'error'])
        outcome = post.status
    try:
        SlackDrafts().update_card(post)
    except (SlackNotConfigured, Exception) as exc:   # noqa: BLE001 — cosmetic; logged
        logger.warning('card redraw after %s on %s failed: %s', action_id, post.pk, exc)
    return outcome
```
`social/views.py` add:
```python
import json
from urllib.parse import parse_qs
from django.conf import settings
from .interact import handle_action, verify_slack_signature

class SlackInteractView(APIView):
    """Slack posts `payload=<json>` (form-encoded) for every button click and
    expects a 200 within 3 s. Signature-verified; no session, no CSRF."""
    permission_classes = [AllowAny]
    authentication_classes = []
    def post(self, request):
        secret = settings.SLACK_SIGNING_SECRET
        if not secret:
            logger.error('SLACK_SIGNING_SECRET not set; rejecting Slack interaction')
            return Response(status=503)
        body = request.body
        if not verify_slack_signature(secret, request.META.get('HTTP_X_SLACK_REQUEST_TIMESTAMP', ''),
                                      request.META.get('HTTP_X_SLACK_SIGNATURE', ''), body):
            return Response({'error': 'invalid signature'}, status=400)
        try:
            payload = json.loads(parse_qs(body.decode('utf-8')).get('payload', ['{}'])[0])
        except (ValueError, UnicodeDecodeError):
            payload = {}
        if not isinstance(payload, dict) or payload.get('type') != 'block_actions':
            return Response(status=200)
        user_id = (payload.get('user') or {}).get('id', '')
        for action in payload.get('actions') or []:
            handle_action(action.get('action_id', ''), action.get('value', ''), user_id)
        return Response(status=200)
```
`social/urls.py`: `path('slack/interact/', views.SlackInteractView.as_view(), name='slack-interact'),`
- [ ] **Step 4:** pass. **Step 5:** commit `feat(social): Slack interactivity endpoint (signed) flips post status`.

### Task 5: deals facts filtered by publish day

**Files:** Modify `social/facts.py:53-86,254-270`, `social/tests/test_facts.py`

- [ ] **Step 1: failing test** in `DealsFactsTests`:
```python
    def test_offers_ending_before_publish_day_are_dropped(self):
        PriceRecord.objects.all().delete()
        _seed_deal('leek', 'pórek', days=9); _seed_deal('apple', 'jablko', days=2)
        _seed_deal('butter', 'máslo', days=5); _seed_deal('egg', 'vejce', days=6)
        publish_day = timezone.now().date() + timedelta(days=3)
        facts = build_facts('deals', '2026-W37', publish_day=publish_day)
        self.assertEqual([d['ingredient'] for d in facts['deals']], ['máslo', 'vejce', 'pórek'])
    def test_filter_can_leave_too_few_offers(self):
        with self.assertRaises(NoFacts):
            build_facts('deals', '2026-W37', publish_day=timezone.now().date() + timedelta(days=30))
```
- [ ] **Step 2:** run → TypeError. **Step 3:** `deals_facts(iso_week, publish_day: Optional[date] = None)`: after `index = active_deal_index()` add
```python
    if publish_day is not None:
        index = {slug: d for slug, d in index.items()
                 if date.fromisoformat(d['valid_until'][:10]) >= publish_day}
```
(`from datetime import date, timedelta`). `build_facts(kind, iso_week, *, publish_day=None, run_plan=None, reuse_latest=False)` passes `publish_day` to `deals_facts` only; other kinds ignore it.
- [ ] **Step 4:** pass. **Step 5:** commit `feat(social): deals facts drop offers that end before publish day`.

### Task 6: publish job driven by status

**Files:** Modify `social/management/commands/publish_social_posts.py`; rewrite `social/tests/test_publish_command.py`

- [ ] **Step 1: tests** — `_seams(publishers=None, today=..., override=None)`: `slack = MagicMock(); slack.caption_override.return_value = override`. Rows default `status='approved', approved_by='UHUMAN'`. Tests:
  - approved → published, `facebook_post_id`, `published_at`, `slack.update_card` called with the post (status published), `slack.reply` NOT called.
  - recipe → both channels (unchanged).
  - `test_draft_due_is_marked_missed_once_and_not_published`: `_post(status='draft')` run twice → status draft, `error == MISSED_NOTE`, `update_card.call_count == 1`, publishers not called.
  - `test_rejected_rows_are_ignored`: `_post(status='rejected')` → publishers not called, update_card not called.
  - override valid → caption replaced; invalid → original used + `slack.reply` contains 'override rejected'.
  - approved without caption → CommandError, status stays approved, `update_card` called, publishers not called.
  - partial failure (unchanged logic) + retry from `failed`.
  - future rows untouched (`update_card` not called).
  - stale draft (>7 days) → rejected, error 'stale…', update_card called.
  - expired deals → rejected (approved row).
  - `--force`: draft stays draft even with force; approved past expiry publishes; force skips stale gate (approved stale row publishes).
  - `--date` overrides today.
- [ ] **Step 2:** run → fails. **Step 3:** rewrite command:

```python
from social.slack import MISSED_NOTE, SlackDrafts, SlackNotConfigured
...
        base = SocialPost.objects.filter(scheduled_for__lte=today).exclude(slack_ts='').order_by('scheduled_for')
        if options.get('only'): base = base.filter(pk=options['only'])
        force = bool(options.get('force')); problems = []
        for post in base.filter(status=SocialPost.Status.DRAFT):
            self.stdout.write(f'{post.kind} {post.iso_week}: {self._handle_draft(post, today, slack, force)}')
        for post in base.filter(status__in=[SocialPost.Status.APPROVED, SocialPost.Status.FAILED]):
            outcome = self._handle_post(post, today, slack, publishers, shops, recipes, force=force)
            self.stdout.write(f'{post.kind} {post.iso_week}: {outcome}')
            if outcome.startswith(('failed', 'cannot')): problems.append(...)
        if problems: raise CommandError('; '.join(problems))

    def _handle_draft(self, post, today, slack, force) -> str:
        if not force and (today - post.scheduled_for).days > STALE_AFTER_DAYS:
            return self._reject(post, slack, today, f'stale: unapproved for more than {STALE_AFTER_DAYS} days')
        if post.error != MISSED_NOTE:
            post.error = MISSED_NOTE; post.save(update_fields=['error']); slack.update_card(post, today)
        return 'pending'

    def _handle_post(...):   # approved or failed
        override = slack.caption_override(post)
        if override:
            violations = validate_caption(override, post.facts, known_shops=shops, known_recipes=recipes)
            if violations: slack.reply(post, '⚠️ caption override rejected — ' + '; '.join(violations))
            else: post.caption = override; post.save(update_fields=['caption'])
        if not post.caption:
            slack.update_card(post, today); return 'cannot publish: no caption'
        expired = '' if force else self._expired_deals_reason(post, today)
        if expired: return self._reject(post, slack, today, expired)
        ...publish loop unchanged (post.status stays approved until the end)...
        if errors: post.status, post.error = FAILED, ...; save; slack.update_card(post, today); return f'failed (...)'
        post.status, post.error, post.published_at = PUBLISHED, '', timezone.now(); save; slack.update_card(post, today); return 'published'

    def _reject(self, post, slack, today, reason):
        post.status, post.error = REJECTED, reason; post.save(update_fields=['status', 'error'])
        slack.update_card(post, today); return f'rejected ({reason})'
```
Remove `WAITING_NOTE`; docstring: "Nothing is published unless the row is `approved` (a Schválit click)".
- [ ] **Step 4:** pass. **Step 5:** commit `feat(social): publish job reads status, redraws cards`.

### Task 7: generator — tomorrow's kind, loud failures

**Files:** Modify `social/management/commands/generate_social_drafts.py`, `social/tests/test_generate_command.py`

- [ ] **Step 1: tests** — change `test_creates_three_drafts_for_next_week_and_posts_them` to pass `week='2026-W37'`. Add:
```python
    def test_default_run_drafts_only_the_kind_due_tomorrow(self):
        for today, kind in [(date(2026, 9, 6), 'deals'), (date(2026, 9, 8), 'recipe'), (date(2026, 9, 10), 'showcase')]:
            SocialPost.objects.all().delete()
            call_command('generate_social_drafts', **_seams(today=today))
            self.assertEqual(list(SocialPost.objects.values_list('kind', 'iso_week')), [(kind, '2026-W37')])
    def test_nothing_due_tomorrow_is_a_quiet_success(self):
        out = io.StringIO(); seams = _seams(today=date(2026, 9, 7))
        call_command('generate_social_drafts', stdout=out, **seams)
        self.assertIn('nothing due tomorrow', out.getvalue()); self.assertEqual(SocialPost.objects.count(), 0)
        seams['slack'].post_draft.assert_not_called()
    def test_kind_alone_targets_the_week_of_tomorrow(self):
        call_command('generate_social_drafts', kind='showcase', **_seams(today=date(2026, 9, 6)))
        self.assertEqual(SocialPost.objects.get().iso_week, '2026-W37')
    def test_every_non_draft_outcome_is_announced_in_the_channel(self):
        seams = _seams(week='2026-W37')   # (pass week via call_command, not seams)
        ... generate raising _ModelError for deals → reply_channel called once, text contains 'Akce', 'pondělí 7. 9.', '503', '<@UOWNER>' (override_settings SOCIAL_SLACK_MENTION='UOWNER')
    def test_deals_facts_get_the_publish_day(self):
        seen = {}; def build(kind, week, **kw): seen[kind] = kw; return FACTS[kind]
        call_command('generate_social_drafts', **_seams(build_facts=build, today=date(2026, 9, 6)))
        self.assertEqual(seen['deals'], {'publish_day': date(2026, 9, 7)})
```
`test_one_kinds_failure_does_not_cost_the_other_two`, `test_rerun_is_idempotent`, `test_no_facts_records_skipped_and_exits_non_zero`, `test_rejected_caption_still_drafts_with_empty_caption`, `test_dry_run_writes_files_and_touches_nothing`: add `week='2026-W37'` to the `call_command` calls so they still cover all three kinds. `test_no_facts…`: `reply_channel.assert_called_once()` stays true.
- [ ] **Step 2:** run → fails. **Step 3:** in `handle`:
```python
        if options.get('week'):
            week = options['week']; kinds = [options['kind']] if options.get('kind') else KINDS
        else:
            due = due_tomorrow(today)
            if options.get('kind'):
                week, kinds = iso_week(today + timedelta(days=1)), [options['kind']]
            elif due is None:
                self.stdout.write('nothing due tomorrow'); return
            else:
                kinds, week = [due[0]], due[1]
        if not WEEK_RE.match(week): raise CommandError(...)
        ...
            self.stdout.write(f'{kind} {week}: {outcome}')
            if outcome != 'draft':
                failures.append(f'{kind}: {outcome}')
                if slack is not None: self._announce_failure(slack, kind, week, outcome)

    @staticmethod
    def _announce_failure(slack, kind, week, outcome):
        mention = f' <@{settings.SOCIAL_SLACK_MENTION}>' if settings.SOCIAL_SLACK_MENTION else ''
        slack.reply_channel(f'⚠️ {KIND_LABELS[kind]} na {cs_day(scheduled_date(week, kind))} se nepodařilo připravit — {outcome}{mention}')
```
In `_draft`: `facts = build(kind, week, publish_day=post.scheduled_for, **(...))`; drop the `slack.reply_channel(f'⏭️ …skipped…')` line inside the `NoFacts` branch (the loop announces it now). Imports: `from django.conf import settings`, `from social.slack import KIND_LABELS, ...`, `from social.weeks import KIND_OFFSETS, cs_day, due_tomorrow, iso_week, prague_today, scheduled_date`, `from datetime import timedelta`. Docstring: "Runs Sun/Tue/Thu evening; drafts the post due tomorrow."
- [ ] **Step 4:** pass. **Step 5:** commit `feat(social): draft the post due tomorrow; announce every failure in Slack`.

### Task 8: e2e command waits on the row

**Files:** Modify `social/management/commands/social_e2e.py`, `social/tests/test_e2e_command.py`

- [ ] **Step 1: tests** — replace `_slack(decisions)` with `_slack()` (post_draft side effect only) and add a `sleep` seam that flips the row:
```python
def _decide_on_sleep(n, status='approved'):
    calls = []
    def sleep(_):
        calls.append(1)
        if len(calls) == n:
            SocialPost.objects.filter(iso_week__startswith='E').update(status=status, approved_by='UHUMAN')
    return sleep
```
Approved case: `_seams(sleep=_decide_on_sleep(2))` → published, `sleep.call_count`-style assertion becomes `len(calls) == 2` (expose via `sleep.calls`). Timeout: sleep never decides → CommandError 'no Schválit', row rejected. Rejected: `_decide_on_sleep(1, 'rejected')` → CommandError 'rejected'. Other tests unchanged except `Decision` import removed.
- [ ] **Step 2:** fails. **Step 3:** `_wait_for_decision(post, sleep, timeout, poll)`: each attempt `post.refresh_from_db(fields=['status'])`; return `post.status != DRAFT`. Messages: `'… is in Slack — click Schválit on it; waiting up to …'`, `E2E_NOTE = '🧪 *E2E test run* — Schválit publishes this to the real Facebook Page *right now* (not on a scheduled day); Zamítnout cancels the test.'`, timeout error `f'no Schválit within {timeout}s — draft rejected, nothing published'`. If status is rejected after the wait: `raise CommandError('rejected in Slack — nothing published')` before calling publish.
- [ ] **Step 4:** pass. **Step 5:** commit `feat(social): social_e2e waits on the row status`.

### Task 9: data migration

**Files:** Create `social/migrations/0002_reject_reaction_era_drafts.py`, `social/tests/test_migration_0002.py`

- [ ] **Step 1: test**
```python
from django.apps import apps
from django.test import TestCase
from social.migrations import reject_reaction_era_drafts as m   # importable module name below
from social.models import SocialPost
class RejectReactionEraDraftsTests(TestCase):
    def test_only_drafts_are_rejected_with_the_reason(self):
        d = SocialPost.objects.create(kind='recipe', iso_week='2026-W39', scheduled_for='2026-09-23', status='draft')
        p = SocialPost.objects.create(kind='deals', iso_week='2026-W39', scheduled_for='2026-09-21', status='published')
        m.reject_drafts(apps, None)
        d.refresh_from_db(); p.refresh_from_db()
        self.assertEqual((d.status, d.error), ('rejected', 'superseded: approval moved to Slack buttons'))
        self.assertEqual(p.status, 'published')
```
Name the migration file `0002_reject_reaction_era_drafts.py`; import it in the test via `importlib.import_module('social.migrations.0002_reject_reaction_era_drafts')`.
- [ ] **Step 2:** fails. **Step 3:**
```python
from django.db import migrations
REASON = 'superseded: approval moved to Slack buttons'
def reject_drafts(apps, schema_editor):
    SocialPost = apps.get_model('social', 'SocialPost')
    SocialPost.objects.filter(status='draft').update(status='rejected', error=REASON)
class Migration(migrations.Migration):
    dependencies = [('social', '0001_initial')]
    operations = [migrations.RunPython(reject_drafts, migrations.RunPython.noop)]
```
- [ ] **Step 4:** pass; `python3 manage.py makemigrations --check --dry-run` reports no model changes. **Step 5:** commit `chore(social): migration rejects reaction-era drafts`.

### Task 10: runbook + DO spec helper

**Files:** Modify `docs/social-pipeline-ops.md`; Create scratchpad `do_social_buttons_spec.py`

- [ ] **Step 1:** runbook edits: §1 add step 4 (Interactivity on, Request URL `https://eatalnicek.eu/api/social/slack/interact/`, copy Signing Secret → `SLACK_SIGNING_SECRET`; `SOCIAL_SLACK_MENTION=<your user id>`); §4 cron `"0 18 * * 0,2,4"` + sentence "drafts the post due tomorrow"; §5 rewrite to per-evening flow (one card, click Schválit; the card shows its state; deadline tomorrow 9:00); §6 "reply caption: … then click Schválit"; §7 "click Schválit"; §8 step 1 "the card must show ✅ Schváleno — click Schválit if it still has buttons", step 5 "`pending` means the card was never approved".
- [ ] **Step 2:** scratchpad script: GET app spec via API, set env `SOCIAL_SLACK_MENTION=U0BV78Z27AS`, add `SLACK_SIGNING_SECRET` from `$SLACK_SIGNING_SECRET` (type SECRET), set `social-generate.schedule.cron="0 18 * * 0,2,4"`, print the diff; `--apply` PUTs. Use distinct variable names for the DO token and the Slack secret (see [[llm-outage-canary]] bug).
- [ ] **Step 3:** commit `docs(social): runbook for button approval and evening-before cadence`.

### Task 11: full verification + PR

- [ ] `python3 -m pytest social -q` all green; `python3 -m pytest diet_planner billing analytics -q` unaffected.
- [ ] `grep -rn "read_decision\|Decision\|next_iso_week\|WAITING_NOTE\|files_upload_v2" social/` → no hits outside git history.
- [ ] Branch `feat/social-slack-buttons`, push, PR to `develop` with the spec link; CI green.
