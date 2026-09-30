"""
The fixed příloha (side) table.

A Czech main is eaten WITH something — guláš with knedlík or bread, lečo with
bread, řízek with potatoes — but source recipes carry that only in prose, so
the corpus lost it (spec 2026-09-06). Rather than curate side recipes, the
planner attaches one of these five rows to a main whose `side_options` name
it. The row becomes an ordinary ingredient (`role: 'side'`) plus nutrition on
the meal, so the shopping list, deals headline and every other reader pick it
up without knowing sides exist.

Quantities are the PURCHASED form per portion (raw potatoes, dry rice/pasta,
bought bread/knedlík). Nutrients are NOT stored here: `side_nutrition`
computes them from the canonical's per-100 g row in the nutrition table, the
same table every curated recipe is computed from.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Dict, FrozenSet, Iterable, Mapping, Optional

if TYPE_CHECKING:
    from diet_planner.services.nutrition_lookups import NutrientRow

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Side:
    key: str
    name_cs: str        # ingredient-list name
    with_cs: str        # card line: "s chlebem"
    canonical: str      # must resolve in data/canonical_ingredients.yaml
    grams: float        # purchased-form grams per portion
    display: str        # per-portion display: "2 krajíce"
    breaks_tags: FrozenSet[str]  # dietary_tags this side would violate


SIDES: Dict[str, Side] = {
    'chleb': Side('chleb', 'chléb', 's chlebem', 'bread-loaf',
                  80, '2 krajíce', frozenset({'gluten_free'})),
    'brambory': Side('brambory', 'vařené brambory', 's vařenými bramborami', 'potatoes',
                     250, '250 g', frozenset()),
    'ryze': Side('ryze', 'rýže', 's rýží', 'rice-basmati',
                 60, '60 g suché rýže', frozenset()),
    'knedlik': Side('knedlik', 'houskový knedlík', 's houskovým knedlíkem', 'bread-dumpling',
                    120, '3 plátky', frozenset({'gluten_free', 'vegan'})),
    'testoviny': Side('testoviny', 'těstoviny', 's těstovinami', 'pasta',
                      70, '70 g suchých těstovin', frozenset({'gluten_free'})),
}
SIDE_KEYS = tuple(SIDES)


def pick_side(recipe: Any, required_tags: Iterable[str]) -> Optional[Side]:
    """First `side_options` entry the plan's dietary tags allow, else None.
    Unknown keys are skipped (a stale tag must not crash a plan)."""
    tags = set(required_tags or ())
    for key in (getattr(recipe, 'side_options', None) or []):
        side = SIDES.get(str(key))
        if side is None or (side.breaks_tags & tags):
            continue
        return side
    return None


def side_ingredient(side: Side, *, portions: int) -> Dict[str, Any]:
    """The side as a meal ingredient row, in the same shape `scale_recipe_to_meal`
    emits, marked `role: 'side'` so the frontend can group it."""
    return {
        'name': side.name_cs,
        'quantity': round(side.grams * portions, 2),
        'unit': 'g',
        'canonical': side.canonical,
        'catalog_id': None,
        'optional': False,
        'role': 'side',
    }


def side_nutrition(side: Side, *, portions: int,
                   table: "Mapping[str, NutrientRow]") -> Dict[str, float]:
    """Nutrients of `portions` portions of the side, from the canonical's
    per-100 g row. A canonical without nutrition contributes zeros (logged) —
    the side is still served, it just adds nothing to the totals."""
    row = table.get(side.canonical)
    if row is None:
        logger.warning("Side %s: canonical %s has no nutrition row — counted as 0",
                       side.key, side.canonical)
        return {'calories': 0.0, 'protein': 0.0, 'carbs': 0.0, 'fat': 0.0}
    factor = side.grams * portions / 100.0
    return {
        'calories': round(row.kcal * factor, 1),
        'protein': round(row.protein * factor, 1),
        'carbs': round(row.carbs * factor, 1),
        'fat': round(row.fat * factor, 1),
    }


def side_meta(side: Side) -> Dict[str, str]:
    """The `meal['side']` object the plan card reads."""
    return {'key': side.key, 'name_cs': side.name_cs, 'with_cs': side.with_cs, 'display': side.display}
