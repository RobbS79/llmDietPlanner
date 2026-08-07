"""
Per-portion nutrition plausibility detector for curated recipes.

Pure, no I/O, never raises. Sibling of `recipe_plausibility`, which gates
implausible per-portion QUANTITIES; this one gates implausible per-portion
CALORIES.

`base_nutrition` is contractually "per base_servings" (see the curation prompt
in llm_service.py), so a portion's calories are `calories / base_servings`.
A large share of the corpus violates that contract: the curation model wrote a
PER-PORTION figure into the field, and dividing it again yields a 30-kcal main
course. That understatement is not cosmetic — `portions_for_target` sizes slots
from per-portion calories, so an understated recipe gets over-served (prod:
Kulajda served as 3 portions, fried rice capped at the whole pan and still
under target).

Calibrated against the 458-recipe published corpus on 2026-08-07:

    per-portion kcal, all roles: p05=24 p25=78 p50=175 p75=302 p95=597
    by dish_role (n, p25/p50/p75):
      main    215   111 / 219 / 360     58 under 120
      light   134    90 / 205 / 288     41 under 120
      side     70    38 /  73 / 164     47 under 120   <- legitimately light
      dessert  27    42 / 172 / 215     11 under 120
      soup     12    58 / 117 / 139      7 under 120

A median main course of 219 kcal is far below a real portion (400-700), which
is what put the corpus under suspicion. Of the 58 multi-portion mains under
120 kcal/portion, 47 have an UNDIVIDED `calories` sitting inside a plausible
single-portion band — direct evidence of the wrong basis rather than merely
optimistic numbers. Those 47 are the ones `suspected_basis` names.

Floors are deliberately set near each role's p25 rather than its median: the
goal is to catch the wrong-basis population without flagging genuinely light
dishes. Re-run `manage.py audit_nutrition_plausibility` before changing them.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# Minimum believable calories in one portion, by dish role.
ROLE_MIN_PORTION_KCAL: Dict[str, float] = {
    'main': 200.0,
    'light': 150.0,
    'soup': 100.0,
    'dessert': 100.0,
    'side': 40.0,
}
DEFAULT_MIN_PORTION_KCAL = 120.0

# Nothing edible is one 1500-kcal portion in this corpus (observed max 1938 is
# itself a wrong-basis artefact in the other direction).
MAX_PORTION_KCAL = 1500.0

# Band in which an undivided `calories` reads as a single sensible portion.
# Used only to explain WHY a recipe failed, never to pass one.
PLAUSIBLE_PORTION_BAND = (250.0, 900.0)

# Atwater factors: kcal per gram.
_KCAL_PER_G = {'protein': 4.0, 'carbs': 4.0, 'fat': 9.0}
# Stated calories may drift from the macro sum via rounding, fibre and alcohol.
ATWATER_TOLERANCE = 0.30


@dataclass(frozen=True)
class NutritionCheck:
    ok: bool
    reasons: List[str] = field(default_factory=list)
    per_portion_kcal: Optional[float] = None
    total_kcal: Optional[float] = None
    atwater_kcal: Optional[float] = None
    # 'per_portion' when base_nutrition appears to hold one portion already.
    suspected_basis: Optional[str] = None


def _num(value: Any) -> Optional[float]:
    """Positive float from a number or a string, tolerating Czech decimal
    commas. None for missing / non-numeric / non-positive."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        parsed = float(value)
    else:
        try:
            parsed = float(str(value).strip().replace(',', '.'))
        except (TypeError, ValueError):
            return None
    return parsed if parsed > 0 else None


def atwater_kcal(base_nutrition: Optional[Dict[str, Any]]) -> Optional[float]:
    """Calories implied by the stored macros, or None if none are usable."""
    if not isinstance(base_nutrition, dict):
        return None
    total = 0.0
    seen = False
    for key, factor in _KCAL_PER_G.items():
        grams = _num(base_nutrition.get(key))
        if grams is not None:
            total += grams * factor
            seen = True
    return total if seen else None


def min_portion_kcal(dish_role: Optional[str]) -> float:
    return ROLE_MIN_PORTION_KCAL.get((dish_role or '').strip().lower(),
                                     DEFAULT_MIN_PORTION_KCAL)


def check_nutrition_plausibility(
    base_nutrition: Optional[Dict[str, Any]],
    base_servings: Any,
    dish_role: Optional[str] = None,
) -> NutritionCheck:
    """Judge one recipe's stored nutrition. Absent data is never a failure —
    only data that is present and wrong."""
    total = _num((base_nutrition or {}).get('calories'))
    implied = atwater_kcal(base_nutrition)
    if total is None:
        return NutritionCheck(ok=True, atwater_kcal=implied)

    servings = max(int(_num(base_servings) or 1), 1)
    per_portion = total / servings
    floor = min_portion_kcal(dish_role)
    reasons: List[str] = []
    basis: Optional[str] = None

    if per_portion < floor:
        reasons.append(
            f'per-portion {per_portion:.0f} kcal is below the {floor:.0f} kcal '
            f'floor for role {dish_role or "unknown"}')
        low, high = PLAUSIBLE_PORTION_BAND
        if servings > 1 and low <= total <= high:
            basis = 'per_portion'
            reasons.append(
                f'stored total {total:.0f} kcal reads as ONE portion — '
                f'base_nutrition looks per-portion, not per {servings} servings')
    elif per_portion > MAX_PORTION_KCAL:
        reasons.append(
            f'per-portion {per_portion:.0f} kcal is above the '
            f'{MAX_PORTION_KCAL:.0f} kcal ceiling')

    if implied is not None and implied > 0:
        drift = abs(total - implied) / implied
        if drift > ATWATER_TOLERANCE:
            reasons.append(
                f'stated {total:.0f} kcal disagrees with macros '
                f'({implied:.0f} kcal from protein/carbs/fat)')

    return NutritionCheck(
        ok=not reasons,
        reasons=reasons,
        per_portion_kcal=round(per_portion, 1),
        total_kcal=total,
        atwater_kcal=round(implied, 1) if implied is not None else None,
        suspected_basis=basis,
    )
