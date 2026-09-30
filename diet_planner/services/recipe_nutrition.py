"""Recipe nutrition from ingredient lines and the per-100 g table. Pure."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, Optional

from diet_planner.services.line_mass import line_grams
from diet_planner.services.nutrition_lookups import NutrientRow


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

    @property
    def coverage(self) -> float:
        return self.lines_converted / self.lines_total if self.lines_total else 0.0


def compute_recipe_nutrition(ingredients: Optional[List[Any]],
                             table: Mapping[str, NutrientRow]) -> RecipeNutrition:
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
        if not slug:
            reason = 'no_canonical'
        elif row is None:
            reason = 'no_nutrition'
        elif lm.grams is None:
            reason = lm.reason or 'unknown_unit'
        else:
            factor = lm.grams / 100.0
            out.calories += row.kcal * factor
            out.protein += row.protein * factor
            out.carbs += row.carbs * factor
            out.fat += row.fat * factor
            out.lines_converted += 1
        if reason:
            out.unconverted.append({'name': line.get('name'), 'canonical': slug or None,
                                    'unit': line.get('unit'), 'reason': reason})
            if not optional:
                out.complete = False
    return out


def computed_base_nutrition(n: RecipeNutrition) -> Dict[str, Any]:
    """The `base_nutrition` dict written to CuratedRecipe (whole recipe for base_servings)."""
    return {
        'calories': int(round(n.calories)),
        'protein': round(n.protein, 1),
        'carbs': round(n.carbs, 1),
        'fat': round(n.fat, 1),
        'source': 'computed',
        'computed_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
    }
