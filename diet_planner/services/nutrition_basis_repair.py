"""Decide whether a curated recipe's `base_nutrition` holds ONE portion, and
whether multiplying it by `base_servings` is a safe repair.

Pure, no I/O, never raises. `nutrition_plausibility` DETECTS the wrong-basis
signature; this module decides what to DO about it, because the signature alone
is not sufficient evidence to rewrite a recipe.

Why the extra evidence. The signature is "per-portion calories below the role
floor, while the stored total reads as one sensible portion". That matches two
different bugs:

  1. the curation model wrote a per-portion figure into a per-recipe field
     (real basis bug — multiplying by base_servings is the fix), and
  2. `base_servings` counts PIECES rather than meals — 4 hard-boiled eggs, 12
     egg muffins — so one "portion" is legitimately below the floor and the
     stored total is already correct (multiplying would invent calories).

Only the recipe's own ingredients can tell these apart, and a fixed kcal/g
ceiling cannot: 4 boiled eggs (1.4 kcal/g) and a granola batch (4.6 kcal/g) are
both legitimate. So we estimate the energy the ingredients actually carry
(`nutrition_density`) and ask which reading of the stored number — as one
portion, or as the whole recipe — that estimate supports. Closeness is measured
as a ratio, since the two readings differ by a factor of `base_servings`.

Two guards sit in front of the estimate:
  * mass coverage — an unmeasured recipe is declined, never guessed at;
  * macro mass — protein + carbs + fat cannot outweigh the raw ingredients,
    a hard physical bound that needs no category data.

`ingredient_mass` returns a LOWER bound, so both guards fail toward "skip for
review" rather than toward a silent rewrite.

Calibrated on the 442-recipe published corpus (2026-08-24): 120 carry the
signature.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from math import log
from typing import Any, Dict, List, Optional

from diet_planner.services.ingredient_mass import estimate_mass_g
from diet_planner.services.nutrition_density import estimate_recipe_kcal
from diet_planner.services.nutrition_plausibility import check_nutrition_plausibility

# Below this share of resolvable ingredient lines the mass bound is too weak to
# judge anything, so we decline rather than guess.
MIN_MASS_COVERAGE = 0.5

# Below this share of estimated mass carrying a known category, the energy
# estimate is not worth comparing against.
MIN_CATEGORY_COVERAGE = 0.6

# How far the multiplied total may sit from the ingredient-energy estimate and
# still be believable. Wide on purpose: the estimate is category-coarse, while
# the readings it separates differ by base_servings (4x-16x).
CORRECTED_ESTIMATE_BAND = (0.5, 2.0)

_MACRO_KEYS = ('protein', 'carbs', 'fat')


@dataclass(frozen=True)
class BasisRepairPlan:
    action: str                                   # 'repair' | 'skip'
    reason: str
    proposed: Optional[Dict[str, Any]] = None     # new base_nutrition, or None
    evidence: Dict[str, Any] = field(default_factory=dict)


def _num(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).strip().replace(',', '.'))
    except (TypeError, ValueError):
        return None


def _scaled(base_nutrition: Dict[str, Any], factor: int) -> Dict[str, Any]:
    """Multiply every numeric nutrient; leave anything else untouched."""
    out: Dict[str, Any] = {}
    for key, value in base_nutrition.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            out[key] = value
            continue
        scaled = value * factor
        out[key] = int(scaled) if float(scaled).is_integer() else round(scaled, 2)
    return out


def _ratio_distance(value: float, estimate: float) -> float:
    """How far `value` sits from `estimate`, measured multiplicatively."""
    if value <= 0 or estimate <= 0:
        return float('inf')
    return abs(log(value / estimate))


def plan_basis_repair(
    base_nutrition: Optional[Dict[str, Any]],
    base_servings: Any,
    dish_role: Optional[str],
    ingredients: Optional[List[Any]],
    piece_weights: Optional[Dict[str, float]] = None,
    categories: Optional[Dict[str, str]] = None,
) -> BasisRepairPlan:
    """Judge one recipe. Only ever proposes `base_nutrition * base_servings`."""
    nutrition = base_nutrition if isinstance(base_nutrition, dict) else {}
    check = check_nutrition_plausibility(nutrition, base_servings, dish_role)
    if check.suspected_basis != 'per_portion':
        return BasisRepairPlan(action='skip', reason='not_a_basis_candidate')

    servings = max(int(_num(base_servings) or 1), 1)
    stored_kcal = _num(nutrition.get('calories')) or 0.0
    corrected_kcal = stored_kcal * servings

    mass = estimate_mass_g(ingredients, piece_weights)
    evidence: Dict[str, Any] = {
        'base_servings': servings,
        'stored_kcal': stored_kcal,
        'corrected_kcal': corrected_kcal,
        'mass_g': mass.grams,
        'coverage': round(mass.coverage, 2),
        'known_lines': mass.known_lines,
        'unknown_lines': mass.unknown_lines,
    }

    if mass.grams <= 0 or mass.coverage < MIN_MASS_COVERAGE:
        return BasisRepairPlan(action='skip', reason='insufficient_mass_evidence',
                               evidence=evidence)

    corrected_macro_g = sum((_num(nutrition.get(k)) or 0.0) for k in _MACRO_KEYS) * servings
    evidence['corrected_macro_g'] = round(corrected_macro_g, 1)
    if corrected_macro_g > mass.grams:
        return BasisRepairPlan(action='skip', reason='macros_exceed_mass', evidence=evidence)

    energy = estimate_recipe_kcal(ingredients, categories, piece_weights)
    evidence['estimated_kcal'] = energy.kcal
    evidence['category_coverage'] = round(energy.coverage, 2)

    if energy.kcal <= 0 or energy.coverage < MIN_CATEGORY_COVERAGE:
        return BasisRepairPlan(action='skip', reason='insufficient_ingredient_data',
                               evidence=evidence)

    evidence['corrected_vs_estimate'] = round(corrected_kcal / energy.kcal, 2)
    evidence['stored_vs_estimate'] = round(stored_kcal / energy.kcal, 2)

    low, high = CORRECTED_ESTIMATE_BAND
    if not (low <= evidence['corrected_vs_estimate'] <= high):
        return BasisRepairPlan(action='skip', reason='corrected_outside_ingredient_energy',
                               evidence=evidence)

    if _ratio_distance(stored_kcal, energy.kcal) <= _ratio_distance(corrected_kcal, energy.kcal):
        return BasisRepairPlan(action='skip', reason='stored_matches_ingredient_energy',
                               evidence=evidence)

    return BasisRepairPlan(
        action='repair',
        reason='ingredient_energy_supports_the_whole_recipe_reading',
        proposed=_scaled(nutrition, servings),
        evidence=evidence,
    )
