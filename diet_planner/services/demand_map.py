"""The demand map: what CZ/SK households search for, relative to guláš = 100.

Data lives in diet_planner/data/demand_map_cz.yaml (Google Trends, refreshed
by hand, see docs/demand-ranking-ops.md). This module only reads it and
matches recipes to terms; writing the result onto CuratedRecipe is the
attach_demand_terms command's job.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import yaml

from diet_planner.services.user_simulation import _significant_words, _strict_hit

DATA_DIR = Path(__file__).resolve().parents[1] / 'data'
DEFAULT_MAP = DATA_DIR / 'demand_map_cz.yaml'
DEFAULT_OVERRIDES = DATA_DIR / 'demand_overrides.yaml'

#: Only these rows may attach to a recipe. Generic words ("salát"), delivery
#: searches ("pizza") and diet queries ("keto recepty") describe intent, not a dish.
ATTACHABLE_KINDS = {'dish'}


@dataclass(frozen=True)
class DemandTerm:
    term: str
    demand: float
    kind: str
    slot: str
    peak_month: Optional[int] = None
    aliases: List[str] = field(default_factory=list)

    @property
    def names(self) -> List[str]:
        return [self.term, *self.aliases]


def load_demand_map(path: Path = DEFAULT_MAP) -> Dict[str, DemandTerm]:
    doc = yaml.safe_load(Path(path).read_text(encoding='utf-8')) or {}
    out: Dict[str, DemandTerm] = {}
    for row in doc.get('terms') or []:
        term = (row.get('term') or '').strip()
        if not term or row.get('demand') is None:
            raise ValueError(f'demand map row needs term and demand: {row!r}')
        peak = row.get('peak_month')
        out[term] = DemandTerm(
            term=term, demand=float(row['demand']), kind=row.get('kind') or 'dish',
            slot=row.get('slot') or 'main', peak_month=int(peak) if peak else None,
            aliases=[str(a) for a in (row.get('aliases') or [])],
        )
    return out


def load_overrides(path: Path = DEFAULT_OVERRIDES) -> Dict[str, str]:
    if not Path(path).exists():
        return {}
    doc = yaml.safe_load(Path(path).read_text(encoding='utf-8')) or {}
    return {str(k): str(v) for k, v in doc.items()}


def match_demand_term(
    recipe, terms: Dict[str, DemandTerm], overrides: Dict[str, str],
) -> Tuple[Optional[DemandTerm], str]:
    """(DemandTerm | None, how) for one recipe. how ∈ {'override', 'name', ''}.

    An override pins a slug to a term and wins outright. Otherwise the recipe
    name must strictly match the term or one of its aliases (the query farm's
    rule: ≥ 60% of the term's significant words, inflection-tolerant); when
    several terms match, the higher demand wins.
    """
    if recipe.slug in overrides:
        pinned = overrides[recipe.slug]
        # An empty value pins the recipe to NO term ("Květákový steak" is not
        # what people searching "steak" want).
        return (terms.get(pinned) if pinned else None), 'override'
    best: Optional[DemandTerm] = None
    for term in terms.values():
        if term.kind not in ATTACHABLE_KINDS:
            continue
        if any(_name_hits(name, recipe) for name in term.names):
            if best is None or term.demand > best.demand:
                best = term
    return best, ('name' if best else '')


def _name_hits(name: str, recipe) -> bool:
    """Does the recipe name carry this term?

    Multi-word terms use the query farm's strict rule (≥ 60% of significant
    words, inflection-tolerant). A single-word term gets a tighter rule: the
    recipe must contain the same word up to one trailing character, because
    the farm's stem rule (5 shared characters, 70% coverage) let "bramboráky"
    claim every potato dish on the first prod dry-run.
    """
    words = _significant_words(name)
    if len(words) != 1:
        return _strict_hit(words, recipe)
    needle = next(iter(words))
    for w in _significant_words(recipe.name_cs):
        shared = 0
        for a, b in zip(needle, w):
            if a != b:
                break
            shared += 1
        if shared >= 5 and shared >= max(len(needle), len(w)) - 1:
            return True
    return False


def attach_demand_term(
    recipe, terms: Dict[str, DemandTerm], overrides: Dict[str, str],
) -> Optional[DemandTerm]:
    """Write the three demand fields for one saved recipe. Used by curation so
    a newly acquired dish is scored before promotion."""
    term, _ = match_demand_term(recipe, terms, overrides)
    recipe.demand_term = term.term if term else ''
    recipe.demand_score = term.demand if term else None
    recipe.demand_peak_month = term.peak_month if term else None
    recipe.save(update_fields=['demand_term', 'demand_score', 'demand_peak_month'])
    return term
