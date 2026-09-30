"""The per-100 g nutrition table, read once per run.

`recipe_nutrition` is deliberately pure: it takes this table as an argument
rather than querying. Callers (curation intake, `remap_curated_recipes`) build
it here once and pass it in.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

from diet_planner.models.catalog import CanonicalIngredient


@dataclass(frozen=True)
class NutrientRow:
    kcal: float
    protein: float
    carbs: float
    fat: float
    density: Optional[float]          # g per ml, None = volume units not convertible
    piece_weight_g: Optional[float]   # grams per "1 ks"
    unit_weights: Dict[str, float]    # ingredient-specific count units


def nutrition_table() -> Dict[str, NutrientRow]:
    """Canonical slug -> NutrientRow for every canonical with complete nutrients."""
    out: Dict[str, NutrientRow] = {}
    fields = ('slug', 'kcal_per_100g', 'protein_per_100g', 'carbs_per_100g',
              'fat_per_100g', 'density_g_per_ml', 'avg_piece_weight_g', 'unit_weights')
    for slug, kcal, protein, carbs, fat, density, piece, uw in (
            CanonicalIngredient.objects.values_list(*fields)):
        if None in (kcal, protein, carbs, fat):
            continue
        out[slug] = NutrientRow(
            kcal=float(kcal), protein=float(protein), carbs=float(carbs), fat=float(fat),
            density=float(density) if density is not None else None,
            piece_weight_g=float(piece) if piece is not None else None,
            unit_weights={str(k): float(v) for k, v in (uw or {}).items()},
        )
    return out
