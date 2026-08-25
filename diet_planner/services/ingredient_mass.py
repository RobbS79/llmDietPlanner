"""Estimate a recipe's total ingredient mass from mixed Czech recipe units.

Pure, no I/O, never raises. Sibling of `recipe_plausibility`, which counts only
`g`/`ml` because under-counting merely makes *that* gate more conservative.
Here the estimate is used as physical evidence about stored nutrition, so the
count units matter: 36 of the corpus's un-massed lines are `ks` eggs, and a
batch of egg muffins is mostly egg by weight.

`ml` is treated as `g` (food density ~1; adequate as a sanity bound). Count
units resolve through the shared piece-weight table keyed by canonical slug —
the same bridge `build_price_book` uses for "2 ks cibule" vs "1 kg net".
Spoon/pinch units use conventional Czech kitchen weights.

The result is a LOWER BOUND: unresolvable lines contribute no mass but do lower
`coverage`, so a caller can tell "small recipe" from "mostly unmeasured".
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

# Direct weight/volume units, in grams per unit.
DIRECT_UNITS: Dict[str, float] = {
    'g': 1.0, 'gram': 1.0, 'gramu': 1.0, 'gramy': 1.0, 'gramů': 1.0,
    'kg': 1000.0, 'ml': 1.0, 'l': 1000.0, 'dl': 100.0, 'cl': 10.0,
}

# Conventional Czech kitchen measures, in grams. Inflected forms are listed
# because the corpus stores whatever the curation model wrote.
SPOON_UNITS: Dict[str, float] = {
    'lžíce': 15.0, 'lžíci': 15.0, 'lžic': 15.0, 'lzice': 15.0,
    'polévková lžíce': 15.0,
    'lžička': 5.0, 'lžičky': 5.0, 'lžiček': 5.0, 'lzicka': 5.0,
    'čajová lžička': 5.0,
    'špetka': 1.0, 'špetky': 1.0, 'spetka': 1.0,
    'stroužek': 5.0, 'stroužky': 5.0, 'stroužků': 5.0, 'strouzek': 5.0,
    'hrst': 30.0, 'hrstka': 30.0, 'malá hrst': 30.0,
    'plátek': 20.0, 'plátky': 20.0, 'platek': 20.0,
    'snítka': 2.0, 'snítky': 2.0, 'lístek': 1.0, 'lístků': 1.0, 'lístky': 1.0,
    'svazek': 30.0, 'svazky': 30.0,
    'šálek': 240.0, 'salek': 240.0, 'hrnek': 240.0,
    'konzerva': 400.0, 'plechovka': 400.0, 'sklenice': 300.0,
}

COUNT_UNITS = {'ks', 'kus', 'kusy', 'kusů', 'kusu', 'ks.'}


@dataclass(frozen=True)
class MassEstimate:
    """A lower bound on a recipe's raw ingredient mass."""
    grams: float
    known_lines: int
    unknown_lines: int

    @property
    def coverage(self) -> float:
        """Fraction of ingredient lines whose mass we could resolve."""
        total = self.known_lines + self.unknown_lines
        return (self.known_lines / total) if total else 0.0


def _quantity(value: Any) -> Optional[float]:
    """Positive float from a number or string, tolerating Czech decimal commas."""
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


def estimate_mass_g(
    ingredients: Optional[List[Any]],
    piece_weights: Optional[Dict[str, float]] = None,
) -> MassEstimate:
    """Lower-bound total mass in grams for `ingredients`."""
    weights = piece_weights or {}
    grams = 0.0
    known = unknown = 0

    for row in (ingredients or []):
        if not isinstance(row, dict):
            unknown += 1
            continue
        quantity = _quantity(row.get('quantity'))
        unit = row.get('unit')
        unit = unit.strip().lower() if isinstance(unit, str) else ''
        if quantity is None:
            unknown += 1
            continue
        if unit in DIRECT_UNITS:
            grams += quantity * DIRECT_UNITS[unit]
        elif unit in SPOON_UNITS:
            grams += quantity * SPOON_UNITS[unit]
        elif unit in COUNT_UNITS:
            per_piece = weights.get(row.get('canonical') or '')
            if not per_piece:
                unknown += 1
                continue
            grams += quantity * per_piece
        else:
            unknown += 1
            continue
        known += 1

    return MassEstimate(grams=round(grams, 2), known_lines=known, unknown_lines=unknown)
