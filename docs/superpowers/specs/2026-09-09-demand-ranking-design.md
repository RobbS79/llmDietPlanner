# Demand-driven ranking — design

Date: 2026-09-09. Status: draft for owner review. Companion to the demand map
(private artifact; source data in the session scratchpad, to be committed as
`diet_planner/data/demand_map_cz.yaml` by this work).

## Problem

Plans are assembled from whatever the curation gates admitted, and the ranker
rewards cheap, fast, and ingredient overlap. Nothing in the objective says
"people want this dish". The owner's verdict (2026-09-09): appeal is what
Czech and Slovak households actually look up how to cook, measured by Google
Trends, and that must decide selection *before* a plan is served. Post-hoc
thumbs up/down was rejected.

## Decisions already made by the owner

- Demand (search interest) is the primary appeal signal.
- The owner's hand ratings are kept only as a tiebreaker between recipes of
  the same dish.
- ~150 new mains are acquired against the demand map (separate track:
  source index → curation job). This spec covers only the ranking side and
  the data it needs.

## Data

### `diet_planner/data/demand_map_cz.yaml` (committed)

One row per demand term, produced by the Trends batch scripts and hand-judged
coverage. Only the fields ranking needs are committed:

```yaml
generated: 2026-09-09
anchor: guláš          # = 100
terms:
  - term: svíčková
    demand: 58.1        # cz + 0.5*sk, relative to anchor
    peak_month: 12
    kind: dish          # dish | category | restaurant | intent
    slot: main
    aliases: [sviečková, svíčková na smetaně, hovězí svíčková]
```

`category`, `restaurant`, and `intent` rows are kept for reference but never
attach to a recipe.

### New `CuratedRecipe` fields (migration)

| field | type | meaning |
|---|---|---|
| `demand_term` | CharField, blank | the demand-map term this recipe serves, or blank |
| `demand_score` | FloatField, null | the term's `demand`, copied at attach time |
| `demand_peak_month` | SmallIntegerField, null | 1–12 or null |
| `owner_rating` | SmallIntegerField, null | 1–5 from the rating artifact, else null |

Denormalised on purpose: ranking runs per slot over hundreds of rows and must
not join a YAML file at request time.

### `attach_demand_terms` management command

Matches every `CuratedRecipe` (all statuses) to at most one demand term:

1. an override in `diet_planner/data/demand_overrides.yaml` (`slug: term`)
   wins outright;
2. otherwise the strict name match from `user_simulation._strict_hit` against
   the term and its aliases, choosing the highest-demand term on a tie;
3. otherwise blank (no demand).

Writes the four fields, prints a histogram and every attach it made at
tier 2 so the owner can pin mistakes into the overrides file, and is
idempotent. `--dry-run` prints without writing. Also loads `owner_rating`
from an optional `--ratings ratings.json` (the artifact db export).

This is the only writer of the four fields. Curation of new recipes runs it
implicitly at the end of `build_curated_recipes` so newly acquired dishes are
scored before promotion.

## Ranking change (`recipe_retrieval.score_recipe`)

Insert between the prompt-fit block and the ingredient-reuse block:

```
demand term    : + _DEMAND_WEIGHT * log1p(demand_score) / log1p(100)     # 0 … 8
season bonus   : + _SEASON_BONUS if demand_peak_month within ±1 of now    # 0 or 2
owner tiebreak : + 0.5 * (owner_rating - 3) if owner_rating              # −1 … +1
```

with `_DEMAND_WEIGHT = 8.0`, `_SEASON_BONUS = 2.0`. Rationale for the sizes:

- Below `_WANTED_HIT_WEIGHT` (20): what the user explicitly asked for still
  wins over what is popular.
- Above the ingredient-reuse cap (6): a wanted dish beats a cheap overlap,
  which reverses the lečo mechanism. Reuse becomes what it was meant to be, a
  nudge.
- Log scale: guláš (100) vs svíčková (58) vs lečo (20) must all read as
  "people want this"; a linear scale would make everything below the top 5
  invisible.
- The owner tiebreak is smaller than `_SAMPLING_WINDOW` (1.0) so it only
  decides between near-tied recipes, which is exactly the same-dish case.
- Recipes with no demand term score 0 here. They are not penalised by
  ranking; removing them is a separate, manual unpublish step after the
  acquired dishes are live.

The sampling window stays at 1.0. A demand gap of one log step is about 1.2
points, so two dishes with clearly different demand are ordered
deterministically and two with similar demand still rotate.

## What this does not do

- No per-user taste. Demand is the average household; the onboarding
  preference layer is a later project.
- No judge-based appeal score. Parked by owner decision.
- No automatic unpublishing. `attach_demand_terms` reports the blank set;
  the owner decides.

## Testing

- Unit: `score_recipe` ordering for (a) demand beats reuse, (b) wanted hit
  beats demand, (c) season bonus only in window, (d) owner tiebreak stays
  inside the sampling window, (e) blank demand scores 0.
- Command: attach via override, via strict alias, no match; idempotent
  re-run; `--dry-run` writes nothing; ratings import.
- Fixture: a 12-row demand map slice checked into `tests/data`.
- Prod check after deploy: `selection_distribution_report` before/after, and
  a fresh plan asking for "klasická česká kuchyně" must lead with guláš,
  svíčková, řízek family dishes, not with the cheapest overlap.

## Rollout

1. Migration + command + YAML, behind nothing (fields null = no effect).
2. Run `attach_demand_terms --dry-run` on prod, owner reviews the tier-2
   attaches, pins overrides, then the real run.
3. Ranking constants land in the same PR but read as 0 until the fields are
   populated, so deploy order does not matter.
4. `/qa-prod` on a Czech-classics plan.
