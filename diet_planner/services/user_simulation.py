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
from dataclasses import dataclass, field
from typing import List, Optional

from diet_planner.services.prompt_facets import PromptFacets

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


def _render(template: str, term: str, num_days: int) -> str:
    return (template
            .replace('{ingredient}', term.lower())
            .replace('{n}', str(num_days))
            .replace('{quality}', 'rychlého')
            .replace('{objective}', 'jíst zdravěji')
            .replace('{free_short}', term.lower()))


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
        ))
    return queries
