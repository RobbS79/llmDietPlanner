# Conversational Recipe Swap ("Refine Chat") — Design

**Date:** 2026-07-18
**Status:** Approved design, pending implementation plan
**Scope:** Per-recipe swap refinement only. No profile persistence, no plan-wide preferences.

## Problem

Users can only replace a recipe wholesale ("Vyměnit recept" with a single optional
free-text hint). There is no way to have a short conversation that gathers
preferences and converges on a better curated recipe. The feature must stay inside
the RAG grounding contract: every suggestion is a published `CuratedRecipe` with
intact `canonical`/`catalog_id` ingredient mapping. The LLM never authors or edits
recipe content — it only interprets the conversation to steer deterministic
selection.

## Decisions (locked with user)

| Decision | Choice |
|---|---|
| Preference scope | This swap only — chat context discarded after the session |
| Conversation flow | Hybrid: every assistant turn shows a candidate recipe AND asks one follow-up question |
| Entry point | Replaces the existing one-shot hint panel behind the "Vyměnit recept" button |
| Follow-up questions | LLM-generated in Czech (not a fixed question bank) |
| Architecture | Stateless backend, one combined Gemini flash call per turn, no new DB models |
| Conversation cap | **8 user messages** (up to 16 messages total incl. assistant turns) |

## Architecture

### Backend — `POST /recipes/<meal_id>/refine/`

New DRF view alongside `RecipeReplaceView` (`diet_planner/views.py`), same
auth/ownership checks. No migrations. Two request modes:

**Preview turn (default)**

Request:

```json
{
  "messages": [{"role": "user"|"assistant", "text": "..."}],
  "rejected_ids": [123, 456]
}
```

Flow:

1. Server rejects/truncates histories containing more than 8 user messages
   (keeps the last 16 entries total; the frontend never sends more — see UI
   section).
2. One Gemini flash call (`gemini-2.5-flash`, same model setting as
   `extract_prompt_facets`) receives the conversation and returns JSON:
   - `facets` — cumulative structured facets over the *whole* conversation,
     same schema as `prompt_facets.extract_prompt_facets` (cuisines, wanted /
     avoided ingredients, styles, emphases; cuisines coerced to corpus vocab).
   - `question` — the next follow-up question, in Czech, or `null` when the
     model judges it has enough signal.
3. Deterministic candidate selection: `eligible_recipes_for_slot` +
   `score_recipe` over the published corpus, excluding the current recipe and
   all `rejected_ids`.
4. Candidate is rendered via `scale_recipe_to_meal(factor=1.0)` for display.
   **Nothing is written** — plan, `Recipe` row, and `MealInstance` are untouched.

Response:

```json
{
  "candidate": { "curated_recipe_id": 789, "name": "...", "image": "...",
                 "why": "...", "meta": {...} },
  "question": "Chcete spíš něco lehčího, nebo vydatnějšího?",
  "hint_matched": true
}
```

`why` is derived in code from which facets the candidate matched (not
LLM-written). `hint_matched=false` means facets produced no scoring signal and
the candidate is the unsteered next-best.

**Accept turn**

Request: `{"accept": <curated_recipe_id>}`.

Server re-validates the recipe is still eligible for the slot, then commits
using the same write-back logic as `RecipeReplaceView` (extracted into a shared
helper): update the cached `Recipe` row in place (same pk), rewrite
`plan.days`, reset `MealInstance.is_cooked`. This is the **only** mutating
path. Response mirrors the current replace endpoint's payload so the frontend
cache-swap logic is reused.

### LLM call contract

- Single combined prompt: conversation history → `{facets, question}` JSON.
- Never-raise wrapper (same pattern as `extract_prompt_facets`): any API error,
  timeout, or malformed JSON → empty facets + `question: null`. The turn still
  returns an (unsteered) candidate; the chat degrades, never breaks.
- The question must be generated in Czech; prompt instructs one short question,
  no recipe content, no prices, no claims about availability.
- Cost: exactly one flash call per preview turn, zero on accept.

### Frontend — `RecipeRefineChat`

- The "Vyměnit recept" button on `RecipePage` opens the chat panel; the current
  one-shot hint input is removed (its behavior is equivalent to the first chat
  turn).
- Component state (component-local, discarded on close): `messages`,
  `rejectedIds`, `candidate`, `loading`.
- Each assistant turn renders:
  1. A **candidate card**: image, name, one-line `why` note, "Použít tento
     recept" button.
  2. The assistant's follow-up question (omitted when `question` is null).
- Typing a new message implicitly rejects the currently shown candidate (its id
  is appended to `rejectedIds`).
- **8-user-message cap:** once the user has sent 8 messages, the input is
  disabled and the chat shows a closing prompt — accept the shown candidate or
  "Začít znovu" (start over), which clears all state and restarts.
- Accept: calls the endpoint's accept mode, then performs the same react-query
  cache swap + `plan`/`mealInstances` invalidations as `lib/replaceRecipe.ts`.
- All user-facing strings in Czech, authored by Claude with EN glosses for
  user review (per project convention).

## Error handling

| Failure | Behavior |
|---|---|
| Gemini error / bad JSON | Candidate still shown (unsteered), no question rendered; chat continues |
| No eligible candidates left (all rejected) | Czech "no more alternatives" message + "Začít znovu" action clearing `rejectedIds` |
| `hint_matched=false` | Assistant phrases it honestly in-chat ("nothing matched exactly, but how about…") — replaces the current advisory toast |
| Network/API error | Toast; chat state preserved; user can retry the turn |
| Cap reached | Input disabled; accept-or-restart prompt |

## Testing

**Backend (pytest, existing CI gate):**
- Combined facets+question parser: happy path, malformed JSON → empty facets +
  null question, API exception → same.
- Preview turn does not mutate `plan.days`, `Recipe`, or `MealInstance`.
- Accept commits: `Recipe` updated in place, `plan.days` rewritten,
  `is_cooked` reset.
- `rejected_ids` and current recipe excluded from selection.
- History cap: more than 8 user messages → truncated to the last 16 entries.
- Ownership: foreign user's meal id → 404/403.

**Frontend (vitest, existing CI gate):**
- State transitions: send → candidate shown; type again → previous candidate
  enters `rejectedIds`; accept → cache swap invoked; cap at 8 → input disabled.

**Post-deploy:** `/qa-prod` pass over the live chat flow on eatalnicek.eu.

## Out of scope

- Persisting preferences to `DietaryGoal` or the user profile.
- Plan-wide or cross-swap preference memory.
- LLM authoring/editing of recipe content (violates grounding + catalog_id
  pricing coupling).
- Conversation persistence (DB models, resume after reload).
