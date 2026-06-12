# Real-Recipe Grounded Meal Planning — Plan (Direction B)

**Status:** Plan for execution · **Date:** 2026-06-11 · **Decision:** Replace from-scratch LLM meal invention with **retrieval + adaptation over a curated corpus of real, attributed recipes — sourced worldwide, constrained by CZ/SK catalog availability, presented in Czech** — with novice-clear instructions.

Goal: take the app from "every meal is invented fresh by Gemini with `3 steps maximum`, terse and assumes-you-can-cook" to **plans composed from a vetted library of real dishes** — each linked to a concrete source with credit, rewritten into clear beginner-friendly Czech steps, and re-fitted to the user's macros, budget, dietary needs, and store catalog.

> **Sourcing scope — international, not Czech-only.** The hard constraint is **ingredient availability in the CZ/SK store catalogs**, *not* dish origin. Czechs routinely cook Italian/Asian/Mediterranean/Mexican; international-but-familiar dishes are exactly what fixes the "meals aren't appealing / culturally off" pain (Czech cuisine alone is heavy and repetitive). Origin is a soft preference (weight toward CZ staples + popular international), language is a non-issue (we rewrite every recipe into Czech regardless of source language), so we draw from the much larger worldwide pool. Bonus: most international/English recipe sites publish `schema.org/Recipe` JSON-LD — clean structured extraction vs. scraping messy CZ blog HTML.

> **Why this, not 'just fix the prompt':** the three pains are *clarity*, *cultural appeal*, and *authenticity* — not nutrition accuracy. Better prompting fixes clarity but cannot make meals feel real/trustworthy or reliably appealing. Grounding generation in real, attributed dishes does all three. Constraint-fitting (macros / budget / store catalog / dietary) is preserved because the LLM's job shrinks from *invent* to *select + scale*, and corpus ingredients are pre-mapped to catalog_ids (so recipe↔shopping coherence — the klizka P0 — gets *stronger*, not weaker).

---

## 1. Success metric

A generated week plan where **every meal slot is backed by a `CuratedRecipe`** that:
1. **Links to a concrete real source** with visible credit (`source_url` + `source_name`).
2. Has **novice-clear instructions** — 4–8 steps with technique, temperature, doneness cues, equipment (passes a clarity judge, ≥ the current `PUBLISH_MIN_WORDS` bar and then some).
3. Has ingredients **fully catalog-mapped** (`catalog_id`/canonical) → shopping list coherent by construction.
4. Collectively the day's meals **meet the user's calorie/macro targets within tolerance** (e.g. ±10%).
5. **Respects dietary restrictions and store availability**, and **does not repeat** dishes across the plan.

Provable end-to-end: a test user with a goal → plan generates → every meal shows a real linked source + clear steps → shopping list resolves with real catalog prices → macros land in tolerance.

---

## 2. The core shift: invent → retrieve + adapt

| Today | Direction B |
|---|---|
| `generate_meal_plan_only()` asks Gemini to invent every meal, "3 steps maximum" | Planner **retrieves** candidate `CuratedRecipe`s that satisfy hard constraints, **selects** a set that fits daily macros + variety, and **scales portions** to the per-meal target |
| Instructions: synthetic, terse, on-demand expansion | Instructions: **pre-written, vetted, novice-clear**, served straight from the corpus |
| Nutrition: LLM-estimated per meal | Nutrition: from the corpus record (computed once at curation), scaled by portion |
| Ingredients: invented, mapped at shopping-list time (coherence risk → klizka P0) | Ingredients: **pre-mapped to catalog_id at curation time** → coherence guaranteed |
| No provenance | Every meal **links to a real source** with credit |

LLM stays in the loop but for **selection + portion scaling + optional per-portion note** — a much smaller, lower-variance job than full invention.

---

## 3. Data model — new `CuratedRecipe`

New model (proposed `diet_planner/models/curated.py`). Distinct from the existing per-plan `Recipe` (which is `meal_identifier`-keyed and generated per goal). A plan's meal object references a `CuratedRecipe` via `curated_recipe_id` and stores the **scaled** ingredient quantities for that plan.

| Field | Type | Notes |
|---|---|---|
| `slug` | slug, unique | URL-friendly |
| `name_cs` | str | Czech dish name (real, named dish) |
| `name_en` | str, nullable | optional gloss |
| `description` | text | 1–2 appetizing sentences (CZ) |
| `meal_types` | JSON array | which slots it can fill: `breakfast`/`lunch`/`dinner`/`snack`/`small_meal` |
| `cuisine` | str | `czech`/`italian`/`asian`/`mediterranean`/… — for variety + soft ranking, not a filter |
| `difficulty` | choices | `easy`/`medium` (cap at medium for the novice goal) |
| `dietary_tags` | JSON array | `vegetarian`,`vegan`,`gluten_free`,`dairy_free`,`high_protein`,`low_carb`, … |
| `ingredients` | JSON array | `{name, quantity, unit, catalog_id?, canonical?, optional?}` — **catalog-mapped at curation** |
| `instructions` | JSON array | novice step schema: `{text, time_min?, tip?}` |
| `base_servings` | int | portions the base quantities/nutrition describe |
| `base_nutrition` | JSON | per `base_servings`: `{calories, protein, carbs, fat}` |
| `prep_time` / `cook_time` | int (min) | split, not a single blob |
| **`source_url`** | url | **the concrete linked recipe (credit)** |
| **`source_name`** | str | site/creator name shown to users |
| `source_author` | str, nullable | original author if known |
| `license_note` | str, nullable | e.g. "paraphrased, linked with attribution" |
| `status` | choices | `draft`/`vetted`/`published` |
| `quality_score` | JSON, nullable | clarity / cultural-fit / coherence judge output |
| `usage_count` | int | for variety/popularity ranking |
| `created_at`/`updated_at` | datetime | |

> Relationship to existing `Recipe` + public recipe pages: when a meal references a `CuratedRecipe`, `RecipePage` renders from it directly (steps already match the JSON-array shape). The legacy per-goal `Recipe` path stays as a **fallback** for slots the corpus can't fill (see §6).

---

## 4. Corpus build pipeline (the new asset)

A management command, e.g. `manage.py build_curated_recipes`, that turns a **source-URL index** into vetted records. Per the sourcing decision (author + scrape, **always linked + credited**):

**Input:** a curated index of real source recipes — a list of `{dish_name, source_url, source_name}`. Compiling this index (≈300–500 entries, see §8) is the one genuinely manual/semi-automated input; everything downstream is automated.

**Per-recipe pipeline:**
1. **Fetch** the source page.
2. **Extract** real structure (ingredients, method, timing, servings) — prefer `schema.org/Recipe` JSON-LD when present (common on international/English sites → clean parse, no LLM needed); fall back to LLM-assisted HTML extraction (pattern of `extract_products_from_html()` in `llm_service.py`) for unstructured pages.
3. **Rewrite** into our novice-clear step schema — *paraphrase, never verbatim* — adding technique, temps, doneness cues, equipment; appetizing CZ description. This is what makes it ours + clear.
4. **Map ingredients → catalog_id/canonical**, reusing the pricing catalog resolution (`pricing-catalog-id-resolution`).
5. **Normalize nutrition** to `base_servings` (carry source numbers or compute; low priority per pains).
6. **Attribute + store**: `source_url`/`source_name` set, `status=draft`.

**Vetting gate (reuse the coherence-judge infra):** a Claude **clarity + cultural-fit + coherence** judge (cf. `recipe-coherence-judge`) auto-scores each draft; human spot-checks and promotes `draft → vetted → published`. Only `published` recipes are retrievable by the planner.

---

## 5. Retrieval layer

`select_recipes_for_plan(constraints)` — start simple (SQL filters + greedy macro fit), **no pgvector yet** (premature for a few hundred rows).

- **Hard filters (SQL):** `status=published`; `meal_types` contains the slot; `dietary_tags ⊇` user's restrictions; **all ingredients resolvable in the selected store catalog** — *this is the primary gate that makes worldwide sourcing safe: a recipe is eligible iff every ingredient maps to a buyable catalog product (or an allowed substitute).*
- **Soft ranking:** macro-fit to the per-meal target share; **variety** (penalize dishes/ingredients/cuisines already used in this plan); cuisine balance (weight toward CZ staples + popular international, avoid monotony); `difficulty ≤` user level; `usage_count` for popularity.
- **Week assembly:** greedy per-slot against a running daily macro budget; optional LLM pass to swap for variety/coherence. Deterministic and debuggable.

---

## 6. Planner integration

Modify `tasks.py:process_dietary_goal_task` → step 1 (`generate_meal_plan_only`):
1. `select_recipes_for_plan(constraints)` → chosen `CuratedRecipe` per slot.
2. LLM (light) **scales portions** to per-meal macro target, optional per-portion note. Ingredients keep their `catalog_id`.
3. Build the `days` structure with `curated_recipe_id` + scaled ingredients.
4. Step 2 (shopping list) unchanged in spirit — aggregate from chosen recipes' scaled, pre-mapped ingredients → coherence by construction.
5. **Graceful fallback:** if no published recipe fits a slot (sparse corpus), fall back to today's invent-path for that slot, flagged `source=generated`. Prevents the corpus gaps from blocking generation.

---

## 7. Frontend

- `RecipePage.tsx`: add **source attribution** — "Inspirováno receptem z [{source_name}]({source_url})" — plus a difficulty badge and an "ověřený recept" (vetted) badge. Steps already render from the JSON array; surface per-step `tip`/`time_min` if present.
- Minor: split prep vs cook time; optional "linked source" affordance on the meal card in the plan view.

---

## 8. Phased checklist

- **B0 — Pilot (de-risk, ~30 recipes): ✅ DONE (2026-06-12).** 30 real source URLs curated; pipeline proven (curated=30 errors=0, all JSON-LD). Surfaced + FIXED the mapping blocker (25%→99%, 28/30 pass catalog gate) via resolver normalization + canonical dict 62→164 + `remap_curated_recipes`.
- **B1 — Model + pipeline: ✅ DONE.** `CuratedRecipe` model + migration 0026 + admin; `build_curated_recipes` (fetch→extract→rewrite→map→attribute); clarity/coherence judge gate.
- **B2 — Scale corpus to 300–500:** compile the source-URL index (broad coverage: all meal types × main dietary tags × a cuisine mix — CZ staples + popular Italian/Asian/Mediterranean/Mexican/American, all catalog-buyable); run pipeline; vet/publish.
- **B3 — Retrieval + planner swap: ✅ DONE (2026-06-12).** `recipe_retrieval.py`: `select_recipes_for_plan` (hard catalog/meal/diet gate + soft variety/macro rank + greedy assembly) + `scale_recipe_to_meal` + `overlay_curated_recipes`, wired into `tasks.py` behind `RECIPE_GROUNDING_ENABLED`. Overlay model (LLM full plan + curated overlay on covered slots) — retrieval-first cost cut deferred to post-B2. 14 tests; smoke 42/42 coverage on pilot.
- **B4 — Frontend:** attribution/badges/source links. *(meal object now carries source_name/source_url/source_author; RecipePage.tsx render still TODO.)*
- **B5 — QA + prod:** clarity, cultural fit, recipe↔shopping coherence (klizka-style), macro tolerance (±10%), no-repeat; Playwright on prod per QA workflow.

---

## 9. Open questions / decisions

- **Source-URL index ownership** — who compiles the 300–500 `{dish, url, source}` list, and from which sites? Mix of **international** (prefer ones with `schema.org/Recipe` JSON-LD — e.g. large EN recipe sites) and CZ (recepty.cz, toprecepty.cz, apetitonline, …). Semi-automated search + manual curation. *This is the critical-path input.*
- **Cuisine balance** — target ratio of CZ-traditional vs. international in the corpus (e.g. ~40/60?), and per-plan variety rules so a week isn't all one cuisine. Tuning knob, decide during B2.
- **Nutrition source** — carry source numbers vs. compute from an ingredient nutrition table vs. keep LLM estimate. Lowest priority (not a stated pain); default to carry/compute-light.
- **Vetting workforce** — Claude-judge-gated + human spot-check (recommended, reuses coherence-judge infra) vs. pure human.
- **Attribution policy** — confirm wording/format with each source's terms; paraphrase + backlink + credit is the posture. Keep a per-source note in `license_note`.
- **Multi-market** — corpus is CZ first; SK/PL (existing localized markets) get translated or separate corpora later.
- **Legacy `Recipe` / public recipe pages** — published `CuratedRecipe`s could also power the public recipe SEO pages (a bonus: real, attributed, indexable content).
