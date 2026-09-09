# Demand ranking — operations

## What it is

`diet_planner/data/demand_map_cz.yaml` holds search demand per dish (Google
Trends, CZ + 0.5×SK, rescaled so guláš = 100, last 12 months). The
`attach_demand_terms` command copies each recipe's term, score and peak month
onto `CuratedRecipe` (`demand_term`, `demand_score`, `demand_peak_month`);
`score_recipe` then adds up to +8 (log demand), +2 (peak month ±1) and ±1
(the owner's rating, `owner_rating`, a same-dish tiebreak only). Recipes with
no term get 0 from this block and rank exactly as before.

Design: `docs/superpowers/specs/2026-09-09-demand-ranking-design.md`.

## Apply on prod (after deploy)

1. `python manage.py attach_demand_terms --dry-run` — read the by-name
   attaches it prints (one line per recipe: slug → term (demand)).
2. Wrong attach? Add `slug: term` to `diet_planner/data/demand_overrides.yaml`,
   commit, deploy, repeat step 1. An override always wins over the name rule.
3. `python manage.py attach_demand_terms` (add `--ratings ratings.json` to load
   the owner's ratings: a JSON list of `{slug, score}` exported from the
   rating artifact's `ratings` collection).
4. `python manage.py selection_distribution_report` before and after, and one
   fresh plan asking for Czech classics: it should lead with guláš, svíčková,
   řízek family dishes rather than the cheapest ingredient overlap.

Newly curated recipes get their term automatically at the end of
`build_curated_recipes`; the command above is only needed for the backfill
and after a map or overrides change.

## Refresh the map

Re-run the Trends batch (scripts documented in the spec; query 4 terms per call
with guláš as the anchor so scores are comparable), regenerate the YAML,
commit, deploy, run step 3 above. Quarterly is enough; peak months do not move.

## Kill switch

Run `attach_demand_terms --map empty.yaml` where `empty.yaml` contains only
`terms: []`. Every row goes blank and ranking behaves as before the feature.
No deploy needed to turn it back on: re-run with the default map.
