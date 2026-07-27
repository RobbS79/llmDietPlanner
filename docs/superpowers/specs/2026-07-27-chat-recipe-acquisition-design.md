# Refine Chat v2: Real AI Conversation + Web Recipe Acquisition

**Date:** 2026-07-27
**Status:** Approved design, pending implementation plan
**Builds on:** `docs/superpowers/specs/2026-07-18-recipe-refine-chat-design.md` (refine chat v1),
`docs/recipe-grounding-plan.md` (Direction B corpus)

## Problem

The refine chat (recipe detail page) is a facet extractor wearing a chat UI. Every
visible reply is a frontend template string; the LLM never sees the recipe the user
is looking at. Real failure observed in prod: user viewing Menemen (lunch slot) wrote
"Vypadá to jak snídaně" — the facet extractor found nothing enforceable, the endpoint
fell back to an unsteered argmax pick, and the UI claimed "Přesně podle vašeho přání
jsme nic nenašli" despite 192 eligible lunch recipes. The user concluded we are short
on recipes. We are not (372 published; lunch pool 192 catalog-mapped); the chat is
short on comprehension, and its fallback copy is dishonest.

Product direction (user decision, 2026-07-27): the chat must be a **full AI
conversation**, and when the corpus genuinely has no match — the user wants
"something special" — the assistant must be able to **research the web and bring
back a brand-new recipe** that is not yet in the DB.

## Decisions (locked with user)

1. **Integrity gate for chat-found recipes:** allow with degraded features. A web
   recipe whose ingredients don't all map to the catalog still enters the user's
   plan; unmapped ingredients simply carry no price/deals data. Honesty by
   omission, never fabrication. Portion-plausibility and coherence gates stay hard.
2. **Chat depth:** real AI conversation. The LLM authors every reply in Czech, sees
   the current recipe + slot + dietary profile, answers questions, and decides
   itself when to search the corpus vs the web.
3. **Latency model:** web research runs as a background Celery job; the chat
   replies instantly ("Hledám recept na webu…") and the result card pops in via
   frontend polling.
4. **Corpus growth:** chat-found recipes are saved as `CuratedRecipe` drafts,
   visible only to the requesting user's plan; the owner promotes good ones to
   published via the existing flow (demand-driven corpus growth).
5. **Architecture:** Approach A — agentic tool loop (Gemini function calling) over
   code-enforced tools, not an intent router, not in-turn streaming.

## Non-goals

- No change to plan *generation* (overlay path) — this spec covers the refine chat only.
- No LLM-invented recipe content. Every offered recipe is either a published corpus
  recipe or curated from a concrete fetched source page with attribution. If no
  source page can be fetched and parsed, the research fails honestly.
- No relaxation of the published-corpus 100% mapping gate. The soft-mapping policy
  applies only to `origin=chat_web` drafts.
- No streaming/SSE infra.

## Architecture

```
RecipeRefineChat.tsx ──POST /recipe-refine/<meal_identifier>──▶ RecipeRefineView
                                                                   │ agentic loop (≤3 tool rounds)
                                                                   │ Gemini flash + function calling
                                              ┌────────────────────┴───────────────────┐
                                              ▼                                        ▼
                                     tool: search_corpus                      tool: research_web
                                     eligible_recipes_for_slot                cap check → RecipeResearchJob
                                     + score_recipe (code gate)               + research_recipe_task.delay()
                                              │                                        │ Celery
                                              ▼                                        ▼
                                     top-5 candidates → model picks           Gemini + Google Search grounding
                                                                               → 3-5 candidate source URLs
                                                                               → curate_from_source() per URL
                                                                               → draft CuratedRecipe
                                                                                 (origin=chat_web,
                                                                                  created_for_user=requester)
RecipeRefineChat polls ◀──GET /recipe-research/<job_id>/── job status: queued/searching/curating/ready/failed
```

## Components

### 1. Data model

**`CuratedRecipe` (diet_planner/models/curated.py) — two new fields:**

- `origin`: CharField choices `curated` (default) | `chat_web`, db_index. Existing
  rows keep `curated` via default; migration is additive.
- `created_for_user`: nullable FK to `AUTH_USER_MODEL`, `on_delete=SET_NULL`,
  related_name `chat_recipes`. Set only for `chat_web` drafts.

Invariants:
- Plan generation and public surfaces read `status=published` only — unchanged —
  so chat drafts never leak to other users.
- Promotion to published requires the recipe to pass `is_catalog_mapped()` (the
  existing promote flow's bar is unchanged); until then it serves only its requester.

**New model `RecipeResearchJob` (diet_planner/models/curated.py):**

| field | type | notes |
|---|---|---|
| `user` | FK User, CASCADE | requester; daily cap counted on this |
| `meal_identifier` | CharField(64) | slot being refined |
| `query` | CharField(300) | the model-authored search query |
| `status` | choices: `queued`, `searching`, `curating`, `ready`, `failed` | polled by frontend |
| `result_recipe` | nullable FK CuratedRecipe, SET_NULL | set on `ready` |
| `fail_reason` | CharField(60), blank | machine code: `no_sources`, `all_sources_failed`, `gates_failed`, `error` |
| `reply_text` | TextField, blank | Czech completion line authored by the task's LLM step, shown in chat on ready/failed |
| `created_at` / `updated_at` | timestamps | cap window + poll staleness |

### 2. Conversational endpoint (agentic tool loop)

`RecipeRefineView.post` preview turns (accept branch unchanged) are replaced behind
the feature flag by a tool loop in a new service `diet_planner/services/refine_agent.py`:

- **Context given to the model:** current recipe (name, description, meal slot,
  main ingredients), user's enforceable dietary tags (from `required_tags_for_goal`
  — stated as facts the model must respect in conversation but does NOT enforce),
  cuisines already used in the plan, clamped transcript (reuse `clamp_messages`,
  same 8-user-message cap).
- **Tools (Gemini function calling):**
  - `search_corpus(cuisines?, wanted_ingredients?, avoided_ingredients?, styles?,
    emphases?)` → runs `eligible_recipes_for_slot(meal_type, required_tags, pool,
    exclude_ids, facets)` + `score_recipe`, returns top 5 as compact JSON (id,
    name_cs, description, total_time, calories, cuisine, dietary_tags). Dietary
    tags are injected code-side from profile + goal + chat-stated restrictions;
    the model cannot omit them. `exclude_ids` = current recipe + rejected ids, as
    today.
  - `research_web(query, dish_hint?)` → validates the daily cap; on success creates
    `RecipeResearchJob(status=queued)`, enqueues `research_recipe_task`, returns
    `{job_id}`. On cap exhaustion returns `{error: 'cap_reached'}` so the model can
    explain in Czech.
- **Loop bounds:** at most 3 tool rounds per turn, then the model must produce a
  final text reply. One preview turn therefore costs 1–4 flash calls (was 1).
- **Reply contract:** the model's final text is the visible chat reply (Czech).
  The endpoint returns
  `{reply_text, candidate?, research_job_id?, question: null}`; `candidate` is
  present iff the model picked a `search_corpus` result — the payload is built
  code-side via the existing `_candidate_payload` from the *tool result*, keyed by
  id, so the model cannot fabricate card contents.
- **Prompt rules:** respond in Czech; only ever offer dishes returned by
  `search_corpus`; use `research_web` when the corpus can't satisfy the request or
  the user explicitly asks for something novel; never state prices or availability;
  never claim a search happened that didn't (the v1 dishonest-fallback bug class).
- **Failure containment (same never-raise philosophy as v1):** any LLM/tool-loop
  exception degrades to the v1 deterministic path (facet pipeline) for that turn,
  logged with a `refine_agent_fallback` marker.

### 3. Web research task

`research_recipe_task(job_id)` in `diet_planner/tasks.py` (`@shared_task`,
`max_retries=0` — a failed job reports honestly rather than silently retrying):

1. `status=searching`. Source discovery: Gemini flash with Google Search grounding
   proposes up to 5 concrete recipe-page URLs for the query (prompt requires real,
   fetchable recipe pages, prefers schema.org/Recipe sites, any language).
2. `status=curating`. For each URL in order, run the existing
   `curate_from_source(url, ...)` — fetch, JSON-LD extract, Czech novice rewrite,
   `resolve_canonical` ingredient mapping, portion-plausibility check, coherence
   judge. First success wins.
3. **Gate policy for `chat_web`:**
   - Portion plausibility: HARD — implausible recipe → try next URL.
   - Coherence judge: stays advisory (recorded in `quality_score`), consistent
     with the corpus pipeline.
   - Catalog mapping: SOFT — unmapped non-optional ingredients are kept with
     `canonical=None, catalog_id=None`. Downstream pricing/deals already key off
     `canonical`/`catalog_id`; unmapped lines contribute nothing (verify in plan:
     `recipe_deals` and shopping-list rendering tolerate null canonicals).
   - Attribution: HARD — `source_url`/`source_name` must be non-empty (guaranteed
     by `curate_from_source`'s source-page requirement).
4. Save draft with `origin=chat_web`, `created_for_user`, `status=draft`;
   set job `ready`, `result_recipe`, and a short Czech `reply_text`
   ("Našel jsem: Shakshuka podle …"). On exhausted URLs → `failed` with
   `fail_reason` and an honest Czech `reply_text`.
5. Wall-clock target < 90 s typical; the task sets `updated_at` on each transition
   so the frontend can show stage-appropriate copy.

### 4. Accept flow

`RecipeRefineView._accept` re-validation pool becomes
`published ∪ (drafts where origin=chat_web AND created_for_user=request.user)`.
All other gates unchanged (slot membership, `required_tags`). Explicitly tested:
another user's chat draft is never acceptable. `is_catalog_mapped()` is NOT part of
the accept gate for own chat drafts (decision 1) — `eligible_recipes_for_slot`'s
mapping check is bypassed for these via an explicit allowlist parameter, not by
weakening the shared gate.

### 5. Frontend (`RecipeRefineChat.tsx`)

- Assistant bubbles render `reply_text` verbatim; the `assistantText` template
  helper and `hint_matched`-driven copy are removed.
- A turn returning `research_job_id` renders a persistent "searching" bubble
  (spinner + stage copy from job status) and polls
  `GET /api/recipe-research/<job_id>/` every 5 s, stopping at `ready`/`failed` or
  after 5 min (then shows a "still working — check back" line; the job keeps
  running server-side).
- `ready` → the job's `reply_text` plus a standard candidate card (same
  `RefineCandidate` shape, same accept button). `failed` → `reply_text` alone.
- Chat input stays enabled while a job runs; a new user message does not cancel
  the job.
- Recipe card for accepted `chat_web` recipes: no deals headline when no mapped
  ingredients have active deals (existing behavior — headline is computed from
  mapped canonicals only); attribution line renders as for corpus recipes.

New endpoint: `RecipeResearchJobView` (GET, `IsAuthenticated`, owner-only 404
otherwise) returning `{status, reply_text?, candidate?}` — `candidate` built with
`_candidate_payload` when `ready`.

### 6. Guardrails & config

- **Daily cap:** 5 research jobs/user/day (row count on `RecipeResearchJob` since
  midnight Prague). Cap exhaustion is surfaced to the model as a tool error so the
  reply is conversational, not an HTTP failure.
- **Turn bounds:** 8 user messages/chat (unchanged), ≤3 tool rounds/turn,
  `MAX_MESSAGE_CHARS=500` (unchanged).
- **Feature flag:** `REFINE_CHAT_AGENT_ENABLED` (default false). Off → v1 facet
  path serves, including its frontend copy. Frontend reads the mode from the
  preview response shape (`reply_text` present ⇒ v2), so no separate flag plumbing.
- **Cost:** worst case per turn ≈ 4 flash calls; research job ≈ 2 flash calls +
  1 judge call. Bounded by caps above.

### 7. Testing

- **refine_agent unit tests:** injected fake model (scripted tool-call
  transcripts): plain conversation, corpus pick, web trigger, cap-reached, 3-round
  bound, exception → v1 fallback. Assert dietary tags always reach
  `eligible_recipes_for_slot` regardless of model output.
- **research task tests:** mocked URL discovery + `curate_from_source`: first-URL
  success, fallback across URLs, all-fail → honest `fail_reason`, soft-mapping
  draft saved with unmapped ingredient intact, plausibility rejection skips source.
- **Accept gate tests:** own chat draft accepted; foreign chat draft rejected;
  published unaffected.
- **Frontend (vitest):** polling state machine (queued→ready, failed, timeout),
  reply_text rendering, card pop-in.
- **Post-deploy:** `/qa-prod` run including one real web-research round trip on
  the QA account.

## Rollout

1. Ship dark (`REFINE_CHAT_AGENT_ENABLED=false`), migrations applied.
2. Enable on prod, self-test with QA account (`/qa-prod`).
3. Watch: research-job failure rate, per-turn flash-call count, cap hits, and
   `refine_agent_fallback` log rate. Kill switch = flag off.

## Open follow-ups (out of scope here)

- Corpus `meal_types` audit: breakfast-identity dishes (menemen, omelets) tagged
  as lunch/dinner dilute slot identity — retag or add slot-affinity penalty.
- Style facets (`light`, `comfort`) still don't influence `score_recipe`; the
  agent's `search_corpus` inherits this. Worth a scoring pass later.
- Promote-review queue UX for accumulated `chat_web` drafts (admin list filter on
  `origin` suffices initially).
