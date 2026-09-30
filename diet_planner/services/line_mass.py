"""One ingredient line -> grams. Pure; never raises.

Mass units convert directly; volume units need the ingredient's density;
count units need its piece weight (`ks`) or an ingredient-specific unit weight
(`stroužek`, `plátek`, ...); garnish units carry a fixed default; a missing or
zero quantity is "to taste" = 0 g and never a gap.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from diet_planner.services.nutrition_lookups import NutrientRow
from diet_planner.services.unit_vocab import (
    COUNT_UNITS, GARNISH_G, MASS_G, VOLUME_ML, normalize_unit,
)


@dataclass(frozen=True)
class LineMass:
    grams: Optional[float]
    method: str          # mass | volume | count | unit_weight | garnish | to_taste | none
    reason: Optional[str] = None  # no_density | no_piece_weight | no_unit_weight | unknown_unit


def _quantity(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        q = float(value) if isinstance(value, (int, float)) else float(str(value).strip().replace(',', '.'))
    except (TypeError, ValueError):
        return None
    return q if q > 0 else None


def line_grams(line: dict, row: Optional[NutrientRow]) -> LineMass:
    qty = _quantity((line or {}).get('quantity'))
    if qty is None:
        return LineMass(0.0, 'to_taste')
    code = normalize_unit((line or {}).get('unit'))
    if code in MASS_G:
        return LineMass(round(qty * MASS_G[code], 3), 'mass')
    if code in VOLUME_ML:
        density = row.density if row is not None else None
        if not density:
            return LineMass(None, 'none', 'no_density')
        return LineMass(round(qty * VOLUME_ML[code] * density, 3), 'volume')
    if code in GARNISH_G:
        return LineMass(round(qty * GARNISH_G[code], 3), 'garnish')
    if code in COUNT_UNITS:
        uw = (row.unit_weights if row is not None else {}) or {}
        if code in uw and uw[code] > 0:
            return LineMass(round(qty * uw[code], 3), 'unit_weight')
        if code == 'ks':
            piece = row.piece_weight_g if row is not None else None
            if piece:
                return LineMass(round(qty * piece, 3), 'count')
            return LineMass(None, 'none', 'no_piece_weight')
        return LineMass(None, 'none', 'no_unit_weight')
    if code == '':
        # bare number ("2 vejce" stored as quantity 2, unit null) -> treat as ks
        piece = row.piece_weight_g if row is not None else None
        if piece:
            return LineMass(round(qty * piece, 3), 'count')
        return LineMass(None, 'none', 'no_piece_weight')
    return LineMass(None, 'none', 'unknown_unit')
