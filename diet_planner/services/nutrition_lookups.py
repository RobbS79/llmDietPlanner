"""Catalog tables the nutrition-basis machinery needs, read once per run.

`nutrition_basis_repair` and `nutrition_density` are deliberately pure — they
take these tables as arguments rather than querying. Both callers (the
`repair_nutrition_basis` command and the curation intake gate) need the same
two, so they live here instead of being built twice.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

from diet_planner.models.catalog import CanonicalIngredient
from diet_planner.services.piece_weights import load_piece_weights


def category_table() -> Dict[str, str]:
    """Canonical slug -> catalog category, for the ingredient-energy estimate."""
    return dict(CanonicalIngredient.objects.values_list('slug', 'category'))


def piece_weight_table() -> Dict[str, float]:
    """Canonical slug -> grams per piece, YAML defaults overlaid with the DB."""
    weights = dict(load_piece_weights())
    for canonical in CanonicalIngredient.objects.exclude(avg_piece_weight_g=None).only(
            'slug', 'avg_piece_weight_g'):
        try:
            grams = float(canonical.avg_piece_weight_g)
        except (TypeError, ValueError):
            continue
        if grams > 0:
            weights[canonical.slug] = grams
    return weights


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
