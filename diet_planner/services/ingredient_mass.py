"""Estimate a recipe's total ingredient mass from mixed Czech recipe units.

Pure, no I/O, never raises. Sibling of `recipe_plausibility`, which counts only
`g`/`ml` because under-counting merely makes *that* gate more conservative.
Here the estimate is used as physical evidence about stored nutrition, so the
count units matter: 36 of the corpus's un-massed lines are `ks` eggs, and a
batch of egg muffins is mostly egg by weight.

Delegates to `line_mass.line_grams` with a neutral row: volume uses density
1.0 (ml ~ g; adequate as a sanity bound), `ks` resolves through the shared
piece-weight table keyed by canonical slug, garnish units use fixed defaults.
Ingredient-specific pieces (stroužek, plátek, ...) have no weight here and
count as unknown.

The result is a LOWER BOUND: unresolvable lines contribute no mass but do lower
`coverage`, so a caller can tell "small recipe" from "mostly unmeasured".
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from diet_planner.services.line_mass import line_grams
from diet_planner.services.nutrition_lookups import NutrientRow


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


def estimate_mass_g(
    ingredients: Optional[List[Any]],
    piece_weights: Optional[Dict[str, float]] = None,
) -> MassEstimate:
    """Lower-bound total mass in grams for `ingredients`."""
    weights = piece_weights or {}
    grams = 0.0
    known = unknown = 0
    for line in (ingredients or []):
        if not isinstance(line, dict):
            unknown += 1
            continue
        slug = line.get('canonical') or ''
        row = NutrientRow(0, 0, 0, 0, density=1.0, piece_weight_g=weights.get(slug) if slug else None,
                          unit_weights={})
        lm = line_grams(line, row)
        if lm.method == 'to_taste' or lm.grams is None:
            unknown += 1
            continue
        grams += lm.grams
        known += 1
    return MassEstimate(grams=round(grams, 2), known_lines=known, unknown_lines=unknown)
