"""Simulated user queries: demand x phrasing x persona.

Three independent axes, deliberately kept apart. WHAT people want comes from
recipe-site rankings, HOW they phrase it from real prod prompts, and the
CONSTRAINTS (diet, slots, days) from the persona set. A hand-written prompt
list would encode our guesses on all three at once, which is how the corpus
came to be measured only against itself.

Generation is seeded and pure: same seed, same queries, so two runs are
comparable across a corpus change.
"""
from __future__ import annotations

import random
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

from diet_planner.models import CuratedRecipe
from diet_planner.models.catalog import Availability
from diet_planner.services import recipe_retrieval as rr
from diet_planner.services.canonical_lookup import fold_diacritics
from diet_planner.services.prompt_facets import PromptFacets

# Diacritics-folded Czech words that mark a dish as animal-based. Hand-authored
# and reviewable, in the spirit of the repo's other hand-authored data (see
# selection_distribution_report.PERSONAS).
#
# This is deliberately a COARSE screen used only to LABEL demand/persona
# pairings for gate-attribution reporting (see pairing_kind below) — it is
# NOT a dietary safety mechanism. The real dietary gate lives in recipe
# retrieval and must never depend on this list.
_ANIMAL_TERMS = frozenset({
    'hovezi', 'veprove', 'kureci', 'kure', 'maso', 'ryba', 'losos', 'tresk',
    'sunka', 'slanina', 'klobasa', 'gulas', 'rizek', 'svickova', 'vejce',
    'syr', 'smetana', 'jogurt', 'tvaroh', 'maslo', 'mleko',
})

#: (name, dietary_restrictions free text, extra PromptFacets kwargs). Same
#: SHAPE as the persona tuples in selection_distribution_report.PERSONAS —
#: NOT the same content: that file has 8 entries curated for plan-selection
#: concentration metrics, this file has 7 curated for demand-farm gate
#: attribution (dietary/cross-diet labeling). Keep them separately curated;
#: they describe different measurement questions, not the same users.
PERSONAS = [
    ('no-preferences', '', {}),
    ('budget-family', '', {}),
    ('time-pressed', '', {'max_time_minutes': 30}),
    ('fitness', '', {'emphases': {'high_protein'}}),
    ('vegetarian', 'vegetariánská strava', {}),
    ('vegan', 'veganská strava', {}),
    ('gluten-free', 'bez lepku', {}),
]

_FALLBACK_TEMPLATES = [{'template': 'Mám {ingredient}, co uvařit?', 'observed': 1}]


@dataclass
class SimulatedQuery:
    persona: str
    prompt_cs: str
    demand_term: str
    demand_rank: int
    slot: str
    dietary_restrictions: str
    facets: PromptFacets
    num_days: int = 5
    canonicals: List[str] = field(default_factory=list)
    pairing: str = 'normal'


def _render(template: str, term: str, num_days: int) -> str:
    return (template
            .replace('{ingredient}', term.lower())
            .replace('{n}', str(num_days))
            .replace('{quality}', 'rychlého')
            .replace('{objective}', 'jíst zdravěji')
            .replace('{free_short}', term.lower()))


def _is_plant_based_restriction(restrictions: str) -> bool:
    folded = fold_diacritics((restrictions or '').lower())
    return 'vegan' in folded or 'vegansk' in folded or 'vegetari' in folded


def _is_animal_based_demand(demand_row) -> bool:
    words = set(fold_diacritics(str(demand_row.get('term', '')).lower()).split())
    for canonical in demand_row.get('canonicals') or []:
        words.add(fold_diacritics(str(canonical).lower()))
    return bool(words & _ANIMAL_TERMS)


def pairing_kind(demand_row, persona_restrictions: str) -> str:
    """'cross-diet' when the dish is animal-based and the persona is not, else 'normal'.

    A coarse LABEL for reporting only (see _ANIMAL_TERMS) — does not affect
    which queries get generated or gated.
    """
    if _is_plant_based_restriction(persona_restrictions) and _is_animal_based_demand(demand_row):
        return 'cross-diet'
    return 'normal'


def generate_queries(demand, templates, personas, *, seed: int, n: int
                     ) -> List[SimulatedQuery]:
    """`n` reproducible queries drawn from in-scope demand.

    Out-of-scope demand (desserts, drinks) is excluded: it is real demand with
    no meal slot, so serving it was never the promise.
    """
    in_scope = [row for row in demand if row.get('in_scope')]
    if not in_scope:
        return []
    templates = templates or _FALLBACK_TEMPLATES

    rng = random.Random(seed)
    queries: List[SimulatedQuery] = []
    for _ in range(n):
        row = rng.choice(in_scope)
        template = rng.choice(templates)['template']
        persona, restrictions, facet_kwargs = rng.choice(personas)
        num_days = rng.choice((3, 5, 7))

        kwargs = dict(facet_kwargs)
        wanted = set(kwargs.pop('wanted_ingredients', set()))
        wanted.add(row['term'].split()[-1].lower())
        facets = PromptFacets(wanted_ingredients=wanted, **kwargs)

        queries.append(SimulatedQuery(
            persona=persona,
            prompt_cs=_render(template, row['term'], num_days),
            demand_term=row['term'],
            demand_rank=int(row['rank']),
            slot=row.get('slot_hint') or 'dinner',
            dietary_restrictions=restrictions,
            facets=facets,
            num_days=num_days,
            canonicals=list(row.get('canonicals') or []),
            pairing=pairing_kind(row, restrictions),
        ))
    return queries


#: Funnel stages in the order retrieval applies them.
_STAGES = ('slot', 'dietary', 'mapped', 'facets')


def gate_funnel(*, slot: str, required_tags: Set[str],
                facets: Optional[PromptFacets]) -> Dict[str, object]:
    """Pool size after each successive gate, plus two distinct readings of the
    damage.

    Calls the real `eligible_recipes_for_slot` with progressively more
    constraints instead of reimplementing its order — the gate list has already
    changed once (the specialty gate) and will change again.

    `killer` is the first gate that emptied the pool entirely — `None` when
    the query is still servable by at least one recipe. `biggest_drop` is the
    gate that removed the most recipes relative to the stage before it,
    fatal or not; ties break toward the earlier gate (retrieval order). The
    two are computed separately and never folded together: a gate can do the
    most damage of the funnel without being fatal (one recipe still gets
    through), and reporting that as a "kill" would be a false claim that the
    query went unserved.
    """
    pool = rr.published_pool(CuratedRecipe.Status.PUBLISHED)

    counts = {'pool': len(pool)}
    counts['slot'] = len(rr.eligible_recipes_for_slot(
        slot, set(), pool=pool, enforce_mapping=False))
    counts['dietary'] = len(rr.eligible_recipes_for_slot(
        slot, required_tags, pool=pool, enforce_mapping=False))
    counts['mapped'] = len(rr.eligible_recipes_for_slot(
        slot, required_tags, pool=pool, enforce_mapping=True))
    counts['facets'] = len(rr.eligible_recipes_for_slot(
        slot, required_tags, pool=pool, enforce_mapping=True, facets=facets))

    # The specialty gate is unconditional inside eligible_recipes_for_slot, so
    # it cannot be toggled off to price it. Count it directly on the slot-and-
    # diet-eligible subset instead.
    specialty_cost = sum(
        1 for r in pool
        if r.shopping_difficulty == Availability.SPECIALTY
        and slot in (r.meal_types or [])
        and required_tags.issubset(set(r.dietary_tags or []))
    )

    # An empty published pool is a distinct, more fundamental failure than any
    # gate emptying a non-empty pool: 'killer' must never read as None
    # (servable) when there was nothing to serve from in the first place. The
    # loop below only fires on a *drop to* zero (previous > 0), so a pool that
    # starts at zero would otherwise pass through it silently.
    if counts['pool'] == 0:
        killer = 'pool'
    else:
        killer = None
        previous = counts['pool']
        for stage in _STAGES:
            if counts[stage] == 0 and previous > 0:
                killer = stage
                break
            previous = counts[stage]

    biggest_drop = None
    biggest_drop_amount = 0
    previous = counts['pool']
    for stage in _STAGES:
        drop = previous - counts[stage]
        if drop > biggest_drop_amount:
            biggest_drop_amount = drop
            biggest_drop = stage
        previous = counts[stage]

    return {
        **counts,
        'specialty_cost': specialty_cost,
        'killer': killer,
        'biggest_drop': biggest_drop,
    }


#: Share of a demand term's significant words that must appear in a recipe
#: name for a STRICT hit. 0.6 keeps "Hovězí guláš" ~ "Guláš hovězí" while
#: rejecting "Kuřecí guláš"-style near misses on a single shared word.
_STRICT_OVERLAP = 0.6

_WORD_SPLIT = re.compile(r'[^0-9a-z]+')


def _significant_words(text: str) -> Set[str]:
    folded = fold_diacritics(text or '').lower()
    return {w for w in _WORD_SPLIT.split(folded) if len(w) > 2}


#: Minimum length of the shared prefix for two folded words to count as the
#: same word under inflection (see _words_match). 5 is a floor, not a
#: startswith: it stops short, unrelated prefixes like "mas" (shared by
#: "maso" and "maslo" — different foods) from collapsing into a match. Do
#: not simplify this to a bare startswith() — that would drop the floor.
#:
#: SAME TWO-PART RULE as `demand_index._fuzzy_canonical_slug` (same
#: constant values, _MIN_STEM_LEN=5 there too): an absolute length floor
#: alone is not enough on its own — see _MIN_COVERAGE_RATIO below for why —
#: so the two floors always travel together. That module has the full
#: worked example (the "cibulová"/"cibule" case); this comment is
#: deliberately the short version so the reasoning lives in one place. Keep
#: the two files' constants in sync if either changes: `_loose_hit`'s
#: canonical-overlap check and this strict-name check both feed the same
#: headline coverage number, and an over-match here inflates it exactly the
#: way an over-match there does.
_MIN_STEM_LEN = 5

#: Minimum fraction of the LONGER of the two words that the shared prefix
#: must cover. Same ratio, same reasoning, as demand_index's
#: _MIN_COVERAGE_RATIO: the absolute floor above lets a short word (as
#: short as 5 characters) claim a prefix match against an arbitrarily long,
#: unrelated word — this guard is what stops that. See demand_index.py for
#: the full write-up.
_MIN_COVERAGE_RATIO = 0.7


def _words_match(a: str, b: str) -> bool:
    """Two folded words match if identical, or if they share a leading
    prefix that clears BOTH _MIN_STEM_LEN (absolute length) and
    _MIN_COVERAGE_RATIO (as a fraction of the longer word's length).

    This is a conservative stand-in for real Czech lemmatization (there is
    no stemmer in canonical_lookup to reuse): it catches case/number
    inflection on the same stem — "hovezi"/"hoveziho" (6 of 8 = 0.75),
    "svickova"/"svickove" (7 of 8 = 0.875) — without merging genuinely
    different words that happen to start alike ("rizek"/"veprovy" share
    nothing; "maso"/"maslo" share only 3 characters, below the floor) and
    without letting a short word claim an arbitrarily long, unrelated word
    just because it happens to be a prefix of it (the ratio guard).
    """
    if a == b:
        return True
    shared = 0
    for ca, cb in zip(a, b):
        if ca != cb:
            break
        shared += 1
    if shared < _MIN_STEM_LEN:
        return False
    return shared / max(len(a), len(b)) >= _MIN_COVERAGE_RATIO


def _strict_hit(term_words: Set[str], recipe) -> bool:
    if not term_words:
        return False
    recipe_words = _significant_words(recipe.name_cs)
    matched = sum(
        1 for tw in term_words if any(_words_match(tw, rw) for rw in recipe_words)
    )
    return matched / len(term_words) >= _STRICT_OVERLAP


def _loose_hit(canonicals: Set[str], recipe) -> bool:
    if not canonicals:
        return False
    recipe_canonicals = {
        (i.get('canonical') or '') for i in (recipe.ingredients or [])
    }
    return bool(canonicals & recipe_canonicals)


def demand_coverage(demand, *, top_n: int) -> Dict[str, object]:
    """How much of the top-N RANKED, IN-SCOPE demand the published corpus can
    serve.

    `top_n` is applied AFTER filtering to in-scope terms and sorting them by
    `rank` ascending (tie-broken by source then term, for reproducibility) —
    NOT by raw position in `demand`. Slicing the raw list would make top_n
    mean "the first source's top N": `build_demand_index.SOURCES` lists a
    dessert-dominated 'global' ranking page first, which is out-of-scope by
    construction, so a raw-position `@20` would score zero in-scope terms on
    every corpus, forever — a metric that always reads 0/0 is worse than no
    metric, since it looks like a finding instead of a bug.

    Ranks are PER-SOURCE and not commensurable: rank 3 on toprecepty's maso
    page is not equivalent to rank 3 on recepty.cz's salads page. Sorting
    across sources by raw rank is a defensible approximation of "most
    wanted," not a true global popularity ordering — treat `@20` as that
    approximation, not a strict ranking. A real cross-source ordering is
    what the deferred pytrends weighting was for.

    Returns strict and loose hit counts over the scored (in-scope, top_n)
    terms; `out_of_scope` counts out-of-scope rows across the WHOLE snapshot,
    not just the scored slice — it describes a property of the demand data
    (how much of it a meal plan has no slot for at all), not of what got
    scored, and the planner has no slot for it so failing it would be a
    false alarm.
    """
    demand = list(demand)
    out_of_scope = sum(1 for row in demand if not row.get('in_scope'))

    in_scope = [row for row in demand if row.get('in_scope')]
    in_scope.sort(key=lambda row: (
        int(row.get('rank') or 0), str(row.get('source') or ''), str(row.get('term') or ''),
    ))
    scored = in_scope[:top_n]

    pool = list(rr.published_pool(CuratedRecipe.Status.PUBLISHED))
    strict_hits = loose_hits = 0
    misses = []

    for row in scored:
        term_words = _significant_words(row['term'])
        canonicals = set(row.get('canonicals') or [])
        strict = any(_strict_hit(term_words, r) for r in pool)
        loose = strict or any(_loose_hit(canonicals, r) for r in pool)
        strict_hits += int(strict)
        loose_hits += int(loose)
        if not loose:
            misses.append(row['term'])

    return {
        'scored': len(scored),
        'out_of_scope': out_of_scope,
        'strict_hits': strict_hits,
        'loose_hits': loose_hits,
        'misses': misses,
    }
