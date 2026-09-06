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
bought bread/knedlík). Nutrients are standard food-table values rounded to
10 kcal — labeled estimates, like every other number in the product. Keep
this table the only place they live.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, FrozenSet, Iterable, Optional


@dataclass(frozen=True)
class Side:
    key: str
    name_cs: str        # ingredient-list name
    with_cs: str        # card line: "s chlebem"
    canonical: str      # must resolve in data/canonical_ingredients.yaml
    grams: float        # purchased-form grams per portion
    display: str        # per-portion display: "2 krajíce"
    calories: float     # per portion
    protein: float      # g per portion
    carbs: float
    fat: float
    breaks_tags: FrozenSet[str]  # dietary_tags this side would violate


SIDES: Dict[str, Side] = {
    'chleb': Side('chleb', 'chléb', 's chlebem', 'bread-loaf',
                  80, '2 krajíce', 200, 7, 38, 2, frozenset({'gluten_free'})),
    'brambory': Side('brambory', 'vařené brambory', 's vařenými bramborami', 'potatoes',
                     250, '250 g', 190, 5, 42, 0, frozenset()),
    'ryze': Side('ryze', 'rýže', 's rýží', 'rice-basmati',
                 60, '60 g suché rýže', 210, 4, 47, 0, frozenset()),
    'knedlik': Side('knedlik', 'houskový knedlík', 's houskovým knedlíkem', 'bread-dumpling',
                    120, '3 plátky', 240, 8, 48, 2, frozenset({'gluten_free', 'vegan'})),
    'testoviny': Side('testoviny', 'těstoviny', 's těstovinami', 'pasta',
                      70, '70 g suchých těstovin', 250, 9, 50, 1, frozenset({'gluten_free'})),
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


def side_nutrition(side: Side, *, portions: int) -> Dict[str, float]:
    return {
        'calories': side.calories * portions,
        'protein': side.protein * portions,
        'carbs': side.carbs * portions,
        'fat': side.fat * portions,
    }


def side_meta(side: Side) -> Dict[str, str]:
    """The `meal['side']` object the plan card reads."""
    return {'key': side.key, 'name_cs': side.name_cs, 'with_cs': side.with_cs, 'display': side.display}
