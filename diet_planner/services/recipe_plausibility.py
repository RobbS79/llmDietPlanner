"""
Per-portion quantity plausibility detector for curated recipes.

Pure, no I/O, never raises. A recipe's ingredient quantities describe
`base_servings` portions; if `base_servings` is too low for the quantities
(the common curation error — it defaults to 1), every weighable ingredient is
inflated proportionally. We flag a recipe when the total weighable mass per
portion, or any single ingredient per portion, exceeds a plausibility ceiling.

`ml` is treated as `g` (food density ~1; adequate for a sanity gate). Pieces
(`ks`), to-taste rows, and non-numeric/non-positive quantities are ignored —
under-counting only makes the gate more conservative.

Thresholds calibrated against the 372-recipe prod corpus on 2026-06-24 via
`manage.py audit_portion_plausibility`: legit per-portion mass runs p50=118,
p90=357, p95~404, max=700 g. The audit caught one true offender (`domaci-leco`,
base_servings=1 -> 7000 g/portion), since corrected to 18 servings; the corpus
now flags 0. 1200/500 give zero false positives and are kept generous on
purpose — legit recipes reach 700 g/portion and the gate hard-blocks
publishing, so tightening toward p95 would risk rejecting good ones. Re-run the
audit before lowering them.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

SINGLE_CAP_G = 500.0      # max single-ingredient mass per portion (validated 2026-06-24, 0 false positives on 372)
TOTAL_CEILING_G = 1200.0  # max total weighable mass per portion (validated 2026-06-24, p95 legit = 411 g)

_WEIGHABLE_UNITS = {"g", "ml"}


@dataclass(frozen=True)
class PlausibilityResult:
    ok: bool
    reasons: List[str] = field(default_factory=list)
    per_portion_total_g: float = 0.0
    per_portion_max_single_g: float = 0.0
    offenders: List[Dict[str, Any]] = field(default_factory=list)


def _coerce_grams(quantity: Any) -> Optional[float]:
    """Parse a quantity into a positive float, tolerating Czech decimal commas.
    Returns None for missing / non-numeric / non-positive values."""
    if quantity is None or isinstance(quantity, bool):
        return None
    if isinstance(quantity, (int, float)):
        value = float(quantity)
    else:
        try:
            value = float(str(quantity).strip().replace(",", "."))
        except (TypeError, ValueError):
            return None
    return value if value > 0 else None


def check_portion_plausibility(
    ingredients: List[Dict[str, Any]],
    base_servings: int,
) -> PlausibilityResult:
    try:
        servings = int(base_servings)
    except (TypeError, ValueError):
        servings = 1
    if servings <= 0:
        servings = 1

    total_g = 0.0
    max_single_g = 0.0
    offenders: List[Dict[str, Any]] = []
    offender_reasons: List[str] = []

    for ing in ingredients or []:
        if not isinstance(ing, dict):
            continue
        unit = ing.get("unit")
        unit = unit.strip().lower() if isinstance(unit, str) else ""
        if unit not in _WEIGHABLE_UNITS:
            continue
        grams = _coerce_grams(ing.get("quantity"))
        if grams is None:
            continue
        total_g += grams
        per_portion = grams / servings
        if per_portion > max_single_g:
            max_single_g = per_portion
        if per_portion > SINGLE_CAP_G:
            name = ing.get("name") or "<unnamed>"
            offenders.append({
                "name": name,
                "grams_per_portion": round(per_portion, 1),
            })
            offender_reasons.append(
                f"{name}: {per_portion:.1f} g/portion > {SINGLE_CAP_G:.0f}"
            )

    per_portion_total = total_g / servings

    reasons: List[str] = []
    if per_portion_total > TOTAL_CEILING_G:
        reasons.append(f"total {per_portion_total:.1f} g/portion > {TOTAL_CEILING_G:.0f}")
    reasons.extend(offender_reasons)

    return PlausibilityResult(
        ok=not reasons,
        reasons=reasons,
        per_portion_total_g=round(per_portion_total, 1),
        per_portion_max_single_g=round(max_single_g, 1),
        offenders=offenders,
    )
