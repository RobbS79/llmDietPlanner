# Social pipeline — Slack buttons, one card per post — Design

**Date:** 2026-09-24
**Status:** approved, not built
**Supersedes:** the Slack approval section of
`2026-09-04-social-content-pipeline-design.md` (reactions on a parent message)
**Related:** `social/slack.py`, `social/management/commands/{generate_social_drafts,publish_social_posts,social_e2e}.py`,
`billing/views.py` `WebhookView` (the signature-verified receiver this copies),
`docs/social-pipeline-ops.md`

## The problem

Three weeks of running the pipeline published nothing, and the owner did not
know which Slack message to approve. Root causes found 2026-09-24:

1. A draft is a plain bot post with the caption as a wall of text; the card
   image and the group text are hidden in its thread. Three drafts land within
   one minute on Sunday. Nothing marks "react on THIS one".
2. Every status update ("still waiting", "not published") is a thread reply,
   invisible in the channel and notifying nobody. There is no @mention anywhere.
3. A deals draft made on Sunday carried offers ending Monday; a ✅ that came
   after Monday 09:00 hit the expiry gate on Wednesday.
4. When Gemini failed inside caption writing (W38), the generator's generic
   error path saved no row and told Slack nothing; only the DO job went red.

## Goals

1. Exactly one obvious thing to approve at a time, with two buttons on it.
2. The card itself always shows its current state; no thread digging.
3. No week can fail silently.
4. Keep the honesty validator, the caption override, and the publish gates.

## Non-goals

- Editing the caption from a Slack modal (the `caption: …` thread reply stays).
- Moving approval to a web page.
- Pinterest changes.

## 1. Message layout

One Block Kit message per post, posted by `SlackDrafts.post_draft`:

| Block | Content |
|---|---|
| header | `🍲 Recept · středa 24. 9. · Facebook + Pinterest` — kinds shown as *Akce* (deals), *Recept*, *Ukázka jídelníčku* (showcase); Czech weekday + day.month |
| image | the card PNG, via the public card URL (§2) |
| section | the full caption (it is what gets published), escaped as today |
| context | status line, see table below, ending with `<@SOCIAL_SLACK_MENTION>` while a decision is pending |
| actions | `✅ Schválit` (action_id `social_approve`) and `❌ Zamítnout` (`social_reject`), both with `value=<post id>` |

Status line by state (the message is edited in place with `chat.update`;
buttons are present only in the first row):

| State | Status line |
|---|---|
| draft, before deadline | `⏳ Čeká na schválení · do <den> 9:00 · <@owner>` |
| draft, deadline passed | `⏳ Nestihlo se · schval a půjde ven při dalším běhu (po/st/pá 9:00) · <@owner>` |
| approved | `✅ Schváleno (<jméno>) · jde ven <den> 9:00` |
| rejected by button | `❌ Zamítnuto (<jméno>)` |
| rejected by a gate | `🚫 Nepublikováno — <reason>` |
| published | `🚀 Publikováno · <facebook permalink>[ · pinterest: <id>]` |
| failed | `⚠️ Publikování selhalo — <reason>` |
| no valid caption | `⚠️ Text neprošel kontrolou — odpověz v threadu `caption: …` a pak Schválit` (buttons stay) |

The thread keeps only: the *Pro skupiny* text (deals), the E2E note, and any
human `caption: …` reply. `SlackDrafts.reply` remains for those; every status
change goes through a new `SlackDrafts.update_card(post)` that re-renders the
whole message from the row, so the card is always a pure function of the
database row.

A caption override validated at publish time that fails posts the
`⚠️ caption override rejected` reply in the thread as today (it is a reply to
the human's reply) and leaves the card in its state.

## 2. Card image URL

`GET /api/social/card/<id>/<sig>.png` returns `SocialPost.image` with
`Content-Type: image/png` and a long `Cache-Control`. `sig` is the first 32 hex
chars of HMAC-SHA256(`settings.SECRET_KEY`, `social-card:<id>`), compared with
`hmac.compare_digest`; any mismatch or missing image is a 404. The URL is
built by `social.cards.card_url(post)` from `settings.SOCIAL_SITE_URL`, the
same base the facts layer uses for links.

Why not Slack-hosted files: `files_upload_v2` + `slack_file` in an image
block works but the share handshake is asynchronous and untestable offline;
a signed URL is deterministic and the same PNG bytes are already in the row.

## 3. Interactivity endpoint

`POST /api/social/slack/interact/` (`social/views.py`, `SlackInteractView`,
`permission_classes=[AllowAny]`, `authentication_classes=[]`, mirroring
`billing.views.WebhookView`).

Request handling, in order:

1. Read raw body. Verify `X-Slack-Signature` = `v0=` + HMAC-SHA256
   (`settings.SLACK_SIGNING_SECRET`, `v0:<X-Slack-Request-Timestamp>:<body>`)
   with `hmac.compare_digest`; reject 400 if the timestamp is more than 300 s
   from now (replay), 400 on bad signature, 503 if the secret is unset.
2. Parse the `payload` form field (JSON). Accept only `type == block_actions`;
   anything else returns 200 with an empty body (Slack tolerates it).
3. For each action with `action_id` in {`social_approve`, `social_reject`}:
   load `SocialPost` by `value`; 200 with nothing if it does not exist.
   - If `status == draft`: set `approved`/`rejected`, `approved_by` = the
     clicking user's Slack id (`user.id`), `error=''`, save, then
     `update_card`.
   - Any other status: `update_card` only (a second click just refreshes).
4. Return 200 with an empty body within Slack's 3 s. `update_card` is one
   `chat.update` call; if it raises `SlackApiError` it is logged and the
   status change still stands (the next publish run re-renders).

Who may click: anyone in the drafts channel. The channel holds the owner and
the bot; if that changes, an approver allow-list is a one-line follow-up.

New settings: `SLACK_SIGNING_SECRET` (default `''`), `SOCIAL_SLACK_MENTION`
(Slack user id, default `''`, omitted from the card when empty).

## 4. Status is the source of truth

- `SlackDrafts.read_decision` and the reaction constants go away.
- `publish_social_posts` selects `status in (approved, failed)` with
  `scheduled_for <= today` (and `slack_ts != ''`). `failed` retries
  the channels still missing an external id, as today.
- Drafts (`status == draft`, `scheduled_for <= today`) are not published; the
  job calls `update_card` on them so the line reads "Nestihlo se". After
  `STALE_AFTER_DAYS` (7) it rejects them as today, via the card.
- The deals expiry gate and the caption override (`_caption_override`, read
  from the thread at publish time, validated) stay unchanged.
- `--force` keeps skipping the stale and expiry gates only.
- `social_e2e` waits on `post.status != draft` (re-read from the DB) instead
  of reactions; its message text changes from "✅ publishes" to "Schválit
  publishes".

Data migration `social/migrations/000X_reject_reaction_era_drafts.py`: every
row with `status='draft'` at migration time becomes `rejected` with
`error='superseded: approval moved to Slack buttons'`. Those cards have no
buttons and would otherwise sit unpublishable.

## 5. Cadence: one draft, the evening before

- DO job `social-generate` cron becomes `0 18 * * 0,2,4` (Sun/Tue/Thu,
  Europe/Prague). `social-publish` stays `0 9 * * 1,3,5`.
- With no `--kind`, `generate_social_drafts` drafts only the kind whose
  `scheduled_date` is tomorrow (Prague); `--week` and `--kind` keep their
  meaning for manual runs. The week is the ISO week of tomorrow, not "next
  week" — `next_iso_week` is replaced by `week_of(tomorrow)`; the runbook
  line about a run "slipping past Monday" is rewritten.
- If tomorrow is none of Mon/Wed/Fri the command prints `nothing due
  tomorrow` and exits 0.
- `deals_facts(iso_week, publish_day)` drops offers with
  `valid_until < publish_day` before ranking; `MIN_DEAL_INGREDIENTS` applies
  after the filter. The publish-time expiry gate stays as the safety net.

## 6. No silent failures

In `generate_social_drafts`, the generic `except Exception` branch (and the
`draft without caption` outcome) now also calls
`slack.reply_channel('⚠️ <Kind> na <den> se nepodařilo připravit — <reason> <@owner>')`.
The `NoFacts`/skipped branch gets the same mention. The command still exits
non-zero so the DO job stays red as the second signal.

## 7. Owner setup (manual, once)

1. api.slack.com/apps → vartobot → **Interactivity & Shortcuts** → on →
   Request URL `https://eatalnicek.eu/api/social/slack/interact/` → Save.
   **Basic Information** → App Credentials → copy *Signing Secret*.
2. DO app spec: add `SLACK_SIGNING_SECRET` (secret), `SOCIAL_SLACK_MENTION`
   (`U0BV78Z27AS`), and change the `social-generate` cron. Claude prepares
   the spec diff; owner applies with doctl ≥ 1.163.
3. After deploy: `python manage.py social_e2e` in the prod console, click
   *Schválit*, confirm the permalink. Runbook §§1, 4, 5, 7, 8 are updated.

## 8. Tests

- `social/tests/test_views.py`: signature ok / bad / stale timestamp / secret
  unset; approve and reject set status + approver and call `chat.update` with
  the expected blocks; a click on a non-draft only refreshes; unknown id and
  non-`block_actions` payloads are 200 no-ops; card endpoint 200 with PNG,
  404 on bad signature or missing image.
- `test_slack.py`: `draft_blocks(post)` per state (golden blocks), `post_draft`
  posts blocks and persists `slack_ts`, `update_card` calls `chat.update`.
- `test_generate_command.py`: tomorrow-kind selection (each weekday), `--kind`
  override, failure branch posts the channel warning with the mention.
- `test_facts.py`: deals filter by publish day.
- `test_publish_command.py`: publishes `approved` only; draft past deadline
  gets the "Nestihlo se" card; stale → rejected card; expiry gate still fires.
- `test_e2e_command.py`: waits on DB status.
- Migration test: draft rows become rejected with the superseded reason.
