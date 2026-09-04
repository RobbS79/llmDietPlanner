# Social Content Pipeline — Design

**Date:** 2026-09-04
**Status:** approved, not built
**Related:** `docs/persona-test-prompts.md`, `diet_planner/services/recipe_deals.py`,
`diet_planner/management/commands/check_llm_health.py` (the job + Slack pattern this copies),
`analytics/` (UTM attribution that measures the result)

## The problem

Vařto has a Facebook Page, a Pinterest account and nobody posting to them. The
owner's go-to-market plan calls for three posts a week produced by "AI tools"
and scheduled through Buffer, and the owner does not want to write them by hand.
Two constraints make the obvious tools a poor fit:

1. **Every public claim must be derivable from the database.** The July copy
   sweep removed all fabricated numbers from the site; a marketing bot that
   invents "ušetříte 300 Kč" would put them straight back.
2. **Meta's API cannot post into Facebook groups** (removed 2024), Buffer's API
   is closed to new apps, and the dev droplet is already memory-starved, so a
   third-party scheduler buys little and costs a service.

The pipeline therefore lives in Django, next to the data it talks about, with a
human checkmark between generation and publication.

## Goals

1. Produce three posts a week — Monday deals roundup, Wednesday recipe card,
   Friday plan showcase — each with a branded image, from database facts only.
2. Put every draft in Slack for one-tap approval; publish approved posts to the
   Vařto Facebook Page and (recipe cards) to Pinterest without further work.
3. Make every post traceable: which facts it came from, who approved it, what
   the platforms returned, and which signups it produced (via UTM).
4. Fail loudly and safely: nothing publishes without approval, and a broken
   platform or LLM turns the DO job red exactly like the LLM canary.

## Non-goals

- Posting into Facebook groups, other Pages, or Instagram (not selected; adding
  Instagram later is one more publisher class, not a redesign).
- A calendar or editing UI. Slack reactions and a `caption:` reply are the UI.
- Engagement handling (replying to comments), analytics dashboards, A/B tests.
- AI-generated photography. Images are composed from existing recipe photos
  and typography so nothing in a picture can be false.

## Architecture

A new Django app `social` with three layers: **facts → post → publish**. Each
layer is a module with one entry point and no knowledge of the others' internals.

```
generate_social_drafts (Sun 18:00 Prague, DO scheduled job)
  facts.py        build_facts(kind, week)      -> dict          (DB only)
  captions.py     write_caption(facts)         -> str           (Gemini + validator)
  cards.py        render_card(kind, facts)     -> PNG bytes     (Pillow)
  slack.py        post_draft(post)             -> message ts
  models.py       SocialPost row, status=draft

publish_social_posts (Mon/Wed/Fri 09:00 Prague, DO scheduled job)
  slack.py        read_decision(post)          -> approved | rejected | pending, caption override
  publishers/facebook.py   publish(post)       -> external id
  publishers/pinterest.py  publish(post)       -> external id
  slack.py        reply_result(post, ...)
```

### Data model

`social.SocialPost`

| field | notes |
|---|---|
| `kind` | `deals` / `recipe` / `showcase` |
| `iso_week` | e.g. `2026-W37`; unique together with `kind` — reruns are idempotent |
| `scheduled_for` | date the publisher may act on it |
| `channels` | JSON list, subset of `["facebook", "pinterest"]` |
| `facts` | JSON, the only input the caption may draw from |
| `caption` | Czech text, the version that will be published |
| `group_variant` | shorter text for manual group pasting (deals only) |
| `image` | `BinaryField`, the PNG card (~150–300 KB; three rows a week) |
| `utm_campaign` | `auto-<kind>-<iso_week>` |
| `status` | `draft` → `approved` / `rejected` → `published` / `failed`; also `skipped` when facts could not be built |
| `slack_ts`, `slack_channel` | the draft message |
| `approved_by` | Slack user id from the reaction |
| `facebook_post_id`, `pinterest_pin_id` | written after publish |
| `error` | last failure text |
| `created_at`, `published_at` | |

The image lives in the row because the generator and publisher run in separate
containers and the database is the only storage they share.

`social.PostedRecipe` is not needed: "not posted in the last 90 days" is a query
on `SocialPost.facts->recipe_id` with `status=published`.

### Layer 1 — facts (`social/facts.py`)

Pure functions over the ORM; no LLM, no network. Each returns a dict or raises
`NoFacts(reason)`, which the generator records as `status=skipped` with the
reason and reports to Slack.

**deals** — the active leaflet deals index from
`diet_planner.services.recipe_deals._active_deal_index()` (LEAFLET_DISCOUNT
`PriceRecord` rows inside their validity window, one per canonical
ingredient), ranked by soonest expiry, top 8. For each: Czech ingredient name,
shop, valid-until date. No prices — the deals layer carries none on purpose.
Plus two public `Recipe` rows whose ingredients hit the most of those
deals (reuse `recipe_deals()`), each with name, public URL, matched count.
`NoFacts` if fewer than 3 ingredients are on offer.

**recipe** — one `Recipe` with `is_public=True`, `has_substantive_instructions()`,
a per-dish image (`has_dish_image`), not published as a card in the last 90
days, preferring the one with the most active deals this week. Facts: name,
public URL, image URL, kcal per portion (from `nutritional_info`), prep and
cook minutes if present, servings, `source_name`, `source_url`, deal matches.
`NoFacts` if the public pool is exhausted (then Slack says so; the fix is
publishing more recipes, which is a curation task, not a pipeline bug).

**showcase** — the pipeline generates a real plan the way a user would: it
creates a `DietaryGoal` for the QA account (`QA_TEST_USERNAME`) from one of
three fixed persona prompts in `social/personas.py` (rotating by week),
runs `process_dietary_goal_task` synchronously (`.apply()`; the task's own
retry and timeout handling bound the wait, there is no separate timer). Facts:
the prompt, day 1's meals (name, per-portion kcal, deal badge) and the day's
kcal total. `NoFacts` if generation fails — which doubles as a weekly
end-to-end canary of the product. The goals belong to the QA account (never a
real user); the pipeline keeps the newest four of its own goals there and
deletes older ones, leaving the QA tester's goals alone.

**Nutrition basis.** A corpus-backed recipe's `nutritional_info` covers all
`servings` portions (the site divides before showing "na porci"); the facts
layer divides the same way and publishes per-portion kcal only when the basis
is certain (`curated_recipe_slug` set), otherwise no kcal at all.

Every fact dict also carries `link`: `https://eatalnicek.eu/?utm_source=<channel>
&utm_medium=social&utm_campaign=auto-<kind>-<week>` (channel filled in at
publish time; the recipe card links to the recipe page instead).

### Layer 2 — caption (`social/captions.py`)

`write_caption(facts, kind)` calls Gemini (existing `GEMINI_MODEL`) with a
per-kind prompt that receives **only** the facts JSON and the house rules:
Czech, informal, no emoji walls, no claims beyond the facts, ≤ 600 characters
for Facebook, hashtags only for Pinterest. Output is validated by
`validate_caption(caption, facts)`, a deterministic check that:

- every integer and decimal in the caption appears in the facts (kcal, prices,
  minutes, counts);
- every shop name from the known shop list that appears in the caption is in
  the facts;
- every recipe name in the caption is in the facts (fuzzy, case- and
  diacritic-insensitive);
- banned phrases are absent: `ušetříte`, `exkluzivn`, `nejlevnější`, `zaručen`,
  `%` followed by `sleva` unless the percentage is a fact.

On failure it retries once with the violations appended to the prompt, then
raises `CaptionRejected`, and the generator posts the draft to Slack anyway with
a red "caption failed validation, write one with `caption:`" note. The
validator is the honesty gate; the human is the taste gate.

The deals post also gets a `group_variant`: same facts, ≤ 350 characters,
first person ("stavím appku…"), no hashtags — written in the same call as a
second JSON field and validated the same way.

### Layer 3 — image card (`social/cards.py`)

Pillow only. Fonts (Bricolage Grotesque for display, Hanken Grotesk for text — the site's
`font-display` and `font-body` faces) are vendored under `social/fonts/` with their
OFL licences. Canvas 1080 × 1350 (4:5, the portrait size both platforms show
full-size). Palette is the Market Paper theme: paper `#F7F3EC`, ink `#241E1A`,
paprika `#DB5026` accent, green `#2E6B43` for the deal badge — values copied from the Tailwind
config into one `PALETTE` dict with a test that fails if the two drift.

- **recipe**: recipe photo (fetched over HTTPS from `https://eatalnicek.eu` +
  `image_url` at generation time; fetch failure → `NoFacts`),
  cover-cropped to the top 60 %; paper panel below with name, `kcal / porce`,
  time if known, "N surovin ve slevě" badge if N > 0, small "Zdroj: <source_name>"
  line, Vařto wordmark bottom-right.
- **deals**: full paper canvas, headline "Tenhle týden v akci", up to 8 rows of
  `ingredient — shop(s)`, footer "recepty, které je využijí → eatalnicek.eu",
  wordmark.
- **showcase**: the persona prompt in quotes as the headline, then day 1 as
  four meal rows with kcal and deal badges, total kcal, footer "jídelníček na
  míru zdarma → eatalnicek.eu", wordmark.

Text wrapping and shrink-to-fit are handled by one helper so long Czech names
never overflow. Each kind has a golden-image test: render fixed facts, compare
to a committed PNG with a small pixel tolerance.

### Layer 4 — Slack (`social/slack.py`)

Uses the existing `SLACK_BOT_TOKEN`; new setting `SOCIAL_SLACK_CHANNEL`.
Scopes to add to the existing Slack app: `files:write`, `reactions:read`,
`channels:history` (plus `chat:write`, already present).

`post_draft(post)` uploads the card via `files.upload_v2` with the caption as
initial comment in a fixed layout:

```
📅 Mon 2026-09-08 · deals · → Facebook
<caption>
— react ✅ to approve, ❌ to reject, or reply `caption: …` to replace the text
```

and stores the message `ts`. For deals it adds one thread reply with the
`group_variant` under "Pro skupiny (vložit ručně):".

`read_decision(post)` calls `reactions.get` on the message: any ✅
(`white_check_mark`) from a non-bot user = approved (user id recorded); ❌ =
rejected; neither = pending. Then `conversations.replies` for the thread; the
**last** reply starting with `caption:` (case-insensitive) replaces the caption
after passing `validate_caption`; a failing override is reported in-thread and
the original stands.

`reply_result(post, ok, detail)` posts in the thread: on success the Facebook
post URL and Pinterest pin URL; on failure the platform's error text.

### Layer 5 — publishers (`social/publishers/`)

A tiny common interface: `publish(*, caption, link, image, title="", post_fn=requests.post) -> str`
(external id) raising `PublishError(detail)`.

**facebook.py** — Meta Graph API v24: `POST /{PAGE_ID}/photos` multipart with
`source=<png>`, `message=<caption + link>`, `published=true`, using
`FB_PAGE_ACCESS_TOKEN` (a long-lived Page token; the app may stay in
development mode because the owner is the Page admin). Returns `post_id`.

**pinterest.py** — Pinterest API v5: `POST /v5/pins` JSON with `board_id`
(`PINTEREST_BOARD_ID`), `title` (recipe name), `description` (caption),
`link` (recipe URL with UTM), `media_source: {source_type: image_base64,
content_type: image/png, data: <b64>}`, bearer `PINTEREST_ACCESS_TOKEN`.
Pinterest grants new apps "trial access", which permits writing to the owner's
own account and is enough here. Returns `id`.

Channel routing is data: `recipe` → `["facebook", "pinterest"]`, `deals` and
`showcase` → `["facebook"]`.

### Commands

`generate_social_drafts [--week 2026-W37] [--kind deals|recipe|showcase] [--dry-run]`
— for each kind: if a `SocialPost` for (kind, week) exists, skip; build facts
(→ `skipped` on `NoFacts`), caption, card, Slack draft, save. `--dry-run`
writes PNG + caption to a local folder and posts nothing. Exit non-zero if any
kind ended `skipped` or errored, with a one-line summary per kind on stdout.

`publish_social_posts [--date YYYY-MM-DD] [--force-post ID]` — for each
`SocialPost` with `scheduled_for <= today` and status `draft`/`approved`: read
the Slack decision; `rejected` → status `rejected`; `pending` → leave it and
say so in-thread once ("still waiting for ✅, will retry next run");
`approved` → publish to each channel, write ids, `published`; any
`PublishError` → `failed` with the error, reported in-thread. A draft older
than 7 days that is still pending becomes `rejected` (stale deals). Exit
non-zero if anything failed.

DO app spec: two `SCHEDULED` jobs on the same image and env as
`llm-health-canary`, crons `0 18 * * 0` and `0 9 * * 1,3,5`,
`time_zone: Europe/Prague`. Env additions (all secrets): `SOCIAL_SLACK_CHANNEL`,
`FB_PAGE_ID`, `FB_PAGE_ACCESS_TOKEN`, `PINTEREST_ACCESS_TOKEN`,
`PINTEREST_BOARD_ID`. Missing publisher credentials make that channel
`failed` with a clear message, never a crash of the whole run.

## Robustness

- **Idempotent by key.** (kind, iso_week) is unique; reruns of either command
  do nothing for rows already past `draft`. A publish that succeeded on
  Facebook and failed on Pinterest records the Facebook id and only retries
  Pinterest on the next run.
- **No silent publication.** The publisher only ever acts on an explicit ✅
  reaction it read this run; a Slack outage means "pending", never "approved".
- **Stale data guard.** Deals facts are built from offers active on Sunday but
  published Monday; the facts record `valid_until` per offer, and the publisher
  refuses a deals post if more than half its offers have expired by publish
  time (status `rejected`, reason in-thread).
- **Cost guard.** One Gemini text call per post (two with retry) and one plan
  generation per week; images are local. The showcase plan uses the QA account
  so it never touches a real user's quota.
- **Secrets.** All tokens are DO secrets; none in the repo; the local `.env`
  gets none of them by default and `--dry-run` needs none.

## Testing

- `facts`: fixture DB with offers/recipes; assert ranking, 90-day exclusion,
  `NoFacts` reasons.
- `captions`: `validate_caption` table tests (numbers, shop names, banned
  phrases, diacritics); `write_caption` with a stubbed Gemini returning a bad
  caption first then a good one → exactly one retry.
- `cards`: golden PNGs per kind, plus an overflow case with a 70-character
  recipe name.
- `slack`: stubbed Web API; decision parsing for ✅/❌/none, bot reactions
  ignored, `caption:` override precedence and validation.
- `publishers`: stubbed HTTP; request shape per platform, error mapping.
- commands: end-to-end with all externals stubbed; idempotency on rerun;
  exit codes; the 7-day stale rule; partial-channel retry.
- One integration test marked `slow` that renders all three cards from the
  local snapshot DB for eyeballing (`--dry-run` output).

## Phasing

1. **Plan A (this spec's implementation plan):** app, model, facts, validator,
   cards, Slack draft + decision, Facebook publisher, both commands, tests.
   Pinterest publisher included; if trial-access approval lags, its channel
   simply reports `failed: no credentials` until the token exists.
2. **Ops (owner, outside the repo):** create the Meta app + Page token, apply
   for Pinterest trial access, add Slack scopes and reinstall the app, create
   `#varto-social`, add the five env vars, add the two jobs to the DO spec
   (doctl ≥ 1.163, see prod-console memory).
3. **Later, not now:** Instagram publisher; promoting curated recipes to public
   pages to widen the recipe-card pool; per-post engagement pull.

## Open question

None blocking. The only judgment call left is whether the showcase plan's
`DietaryGoal` should be deleted after rendering or kept for debugging; the plan
keeps the most recent four and deletes older ones.
