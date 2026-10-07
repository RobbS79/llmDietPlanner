"""Recipe nutrition from ingredient lines and the per-100 g table. Pure.

Frying oil rule: a recipe that deep-fries lists the whole pan of oil
("200 ml oleje na smažení"), but most of it stays in the pan. A line is
"frying fat" when its canonical is in FRYING_FATS and its name matches
FRYING_MARKERS. When such a line weighs DEEP_FRY_MIN_G or more, only
FRYING_OIL_ABSORPTION of its grams counts toward nutrition. 25 % is a typical
deep-frying absorption share and is tunable. Below the threshold (shallow
frying, "2 lžíce oleje na smažení") the oil counts in full. Lines where the
factor applied are counted in `absorbed_lines`, and `computed_base_nutrition`
records `frying_oil_factor` so the stored data says so.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, List, Mapping, Optional

from diet_planner.services.line_mass import line_grams

if TYPE_CHECKING:
    from diet_planner.services.nutrition_lookups import NutrientRow

FRYING_FATS = {'sunflower-oil', 'rapeseed-oil', 'olive-oil', 'avocado-oil', 'coconut-oil',
               'sesame-oil', 'lard', 'butter', 'ghee', 'margarine'}
FRYING_MARKERS = (r'na smažení|na fritování|k smažení|na osmažení|na opečení|'
                  r'na pánev|na fritézu')
_FRYING_RE = re.compile(FRYING_MARKERS, re.IGNORECASE)
DEEP_FRY_MIN_G = 60
FRYING_OIL_ABSORPTION = 0.25


@dataclass
class RecipeNutrition:
    calories: float = 0.0
    protein: float = 0.0
    carbs: float = 0.0
    fat: float = 0.0
    lines_total: int = 0
    lines_converted: int = 0
    unconverted: List[Dict[str, Any]] = field(default_factory=list)
    complete: bool = True
    absorbed_lines: int = 0

    @property
    def coverage(self) -> float:
        return self.lines_converted / self.lines_total if self.lines_total else 0.0


def compute_recipe_nutrition(ingredients: Optional[List[Any]],
                             table: "Mapping[str, NutrientRow]") -> RecipeNutrition:
    """Whole-recipe totals over every line with a quantity. A line with no
    quantity ("dle chuti") converts to 0 g and never needs a table row.
    `complete` is False when any NON-optional line could not convert;
    optional lines that fail are listed but never block."""
    out = RecipeNutrition()
    for line in (ingredients or []):
        if not isinstance(line, dict):
            continue
        out.lines_total += 1
        slug = line.get('canonical') or ''
        row = table.get(slug) if slug else None
        optional = bool(line.get('optional'))
        # to-taste lines need no nutrition row: line_grams says so first
        lm = line_grams(line, row)
        reason: Optional[str] = None
        if lm.method == 'to_taste':
            out.lines_converted += 1
            continue
        if lm.reason == 'bad_quantity':
            reason = 'bad_quantity'
        elif not slug:
            reason = 'no_canonical'
        elif row is None:
            reason = 'no_nutrition'
        elif lm.grams is None:
            reason = lm.reason or 'unknown_unit'
        else:
            grams = lm.grams
            if (slug in FRYING_FATS and grams >= DEEP_FRY_MIN_G
                    and _FRYING_RE.search(str(line.get('name') or ''))):
                grams *= FRYING_OIL_ABSORPTION
                out.absorbed_lines += 1
            factor = grams / 100.0
            out.calories += row.kcal * factor
            out.protein += row.protein * factor
            out.carbs += row.carbs * factor
            out.fat += row.fat * factor
            out.lines_converted += 1
        if reason:
            out.unconverted.append({'name': line.get('name'), 'canonical': slug or None,
                                    'unit': line.get('unit'), 'reason': reason,
                                    'optional': optional})
            if not optional:
                out.complete = False
    return out


def computed_base_nutrition(n: RecipeNutrition) -> Dict[str, Any]:
    """The `base_nutrition` dict written to CuratedRecipe (whole recipe for base_servings)."""
    base = {
        'calories': int(round(n.calories)),
        'protein': round(n.protein, 1),
        'carbs': round(n.carbs, 1),
        'fat': round(n.fat, 1),
        'source': 'computed',
        'computed_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
    }
    if n.absorbed_lines > 0:
        base['frying_oil_factor'] = FRYING_OIL_ABSORPTION
    return base
