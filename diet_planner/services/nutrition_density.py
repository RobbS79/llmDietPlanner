"""Estimate a recipe's total energy from the ingredients it actually contains.

Pure, no I/O, never raises. Coarse by design: one energy density per catalog
category, applied to the mass estimate from `ingredient_mass`.

Why this is good enough for its job. It exists to tell whether a stored
calorie figure describes ONE PORTION or the WHOLE RECIPE — two readings that
differ by `base_servings` (4x to 16x in this corpus). A category-level density
is wrong by tens of percent, nowhere near enough to confuse a 4x gap, and it
succeeds exactly where a fixed kcal/g ceiling fails: 4 hard-boiled eggs
(1.4 kcal/g) and a granola batch (4.6 kcal/g) are both legitimate, so only an
estimate that knows what the dish is made of can tell a real basis bug from a
recipe whose `base_servings` counts pieces.

Values are per gram AS THE RECIPE BUYS IT — dry pasta and rice are weighed dry,
vegetables raw. `legumes` deliberately sits between dry (3.3) and canned (0.9)
because the corpus writes both; `other` is a mid-range fallback. Anything whose
canonical slug has no category contributes mass but no energy, and lowers
`coverage` so a caller can decline to judge.

NOT a nutrition facts source. Never show these numbers to a user; they exist to
compare two candidate readings of a stored value.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from diet_planner.services.ingredient_mass import estimate_mass_g

# kcal per gram, by CanonicalIngredient.Category value.
CATEGORY_KCAL_PER_G: Dict[str, float] = {
    'meat': 2.0,
    'fish': 1.5,
    'dairy': 1.2,        # milk/yoghurt dominate mass; cheese is the tail
    'vegetables': 0.35,
    'fruits': 0.55,
    'grains': 3.5,       # weighed dry
    'legumes': 2.0,      # between dry 3.3 and canned 0.9
    'oils': 8.8,
    'spices': 3.0,       # negligible mass either way
    'eggs': 1.4,
    'nuts': 6.0,
    'beverages': 0.3,    # stock, water, wine
    'condiments': 2.0,
    'baking': 3.8,       # flour, sugar
    'canned': 0.9,       # tomatoes/beans packed in liquid
    'frozen': 0.8,
    'other': 1.5,
}


@dataclass(frozen=True)
class RecipeEnergyEstimate:
    kcal: float
    mass_g: float
    categorised_mass_g: float

    @property
    def coverage(self) -> float:
        """Share of the estimated mass whose energy we could attribute."""
        return (self.categorised_mass_g / self.mass_g) if self.mass_g else 0.0


def estimate_recipe_kcal(
    ingredients: Optional[List[Any]],
    categories: Optional[Dict[str, str]] = None,
    piece_weights: Optional[Dict[str, float]] = None,
) -> RecipeEnergyEstimate:
    """Coarse whole-recipe energy for `ingredients`.

    `categories` maps canonical slug -> CanonicalIngredient.Category value.
    """
    lookup = categories or {}
    kcal = 0.0
    categorised = 0.0

    for row in (ingredients or []):
        if not isinstance(row, dict):
            continue
        line_mass = estimate_mass_g([row], piece_weights).grams
        if line_mass <= 0:
            continue
        density = CATEGORY_KCAL_PER_G.get(lookup.get(row.get('canonical') or ''))
        if density is None:
            continue
        kcal += line_mass * density
        categorised += line_mass

    total_mass = estimate_mass_g(ingredients, piece_weights).grams
    return RecipeEnergyEstimate(
        kcal=round(kcal, 2),
        mass_g=total_mass,
        categorised_mass_g=round(categorised, 2),
    )
