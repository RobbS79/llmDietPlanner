"""One ingredient line -> grams. Pure; never raises on well-formed table rows.

Mass units convert directly; volume units need the ingredient's density;
count units need its piece weight (`ks`) or an ingredient-specific unit weight
(`stroužek`, `plátek`, ...); garnish units carry a fixed default; a missing or
zero quantity is "to taste" = 0 g and never a gap.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Optional

from diet_planner.services.unit_vocab import (
    COUNT_UNITS, GARNISH_G, MASS_G, VOLUME_ML, normalize_unit,
)

if TYPE_CHECKING:
    from diet_planner.services.nutrition_lookups import NutrientRow


@dataclass(frozen=True)
class LineMass:
    grams: Optional[float]
    method: str          # mass | volume | count | unit_weight | garnish | to_taste | none
    reason: Optional[str] = None  # no_density | no_piece_weight | no_unit_weight | unknown_unit | bad_quantity


_BAD = object()


def _quantity(value: Any):
    """Positive float; None for to-taste (None, blank, <= 0); _BAD if unparseable."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        q = float(value)
    else:
        text = str(value).strip()
        if not text:
            return None
        text = ''.join(text.split()).replace('\u202f', '').replace('\u00a0', '').replace(',', '.')
        try:
            q = float(text)
        except ValueError:
            return _BAD
    return q if q > 0 else None


def line_grams(line: dict, row: "Optional[NutrientRow]") -> LineMass:
    qty = _quantity((line or {}).get('quantity'))
    if qty is _BAD:
        return LineMass(None, 'none', 'bad_quantity')
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
