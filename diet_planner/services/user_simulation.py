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

#: (name, dietary_restrictions free text, extra PromptFacets kwargs). Mirrors
#: the personas in selection_distribution_report so the two harnesses describe
#: the same users.
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


def _strict_hit(term_words: Set[str], recipe) -> bool:
    if not term_words:
        return False
    recipe_words = _significant_words(recipe.name_cs)
    return len(term_words & recipe_words) / len(term_words) >= _STRICT_OVERLAP


def _loose_hit(canonicals: Set[str], recipe) -> bool:
    if not canonicals:
        return False
    recipe_canonicals = {
        (i.get('canonical') or '') for i in (recipe.ingredients or [])
    }
    return bool(canonicals & recipe_canonicals)


def demand_coverage(demand, *, top_n: int) -> Dict[str, object]:
    """How much of the top-N demand the published corpus can serve.

    Returns strict and loose hit counts over IN-SCOPE terms only; out-of-scope
    demand (desserts, drinks) is counted separately and never scored, because
    the planner has no slot for it and failing it would be a false alarm.
    """
    considered = list(demand)[:top_n]
    scored = [row for row in considered if row.get('in_scope')]
    out_of_scope = len(considered) - len(scored)

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
