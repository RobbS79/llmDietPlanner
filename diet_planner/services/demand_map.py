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
    pinned = overrides.get(recipe.slug)
    if pinned:
        return terms.get(pinned), 'override'
    best: Optional[DemandTerm] = None
    for term in terms.values():
        if term.kind not in ATTACHABLE_KINDS:
            continue
        if any(_strict_hit(_significant_words(name), recipe) for name in term.names):
            if best is None or term.demand > best.demand:
                best = term
    return best, ('name' if best else '')
