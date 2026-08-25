"""Catalog tables the nutrition-basis machinery needs, read once per run.

`nutrition_basis_repair` and `nutrition_density` are deliberately pure — they
take these tables as arguments rather than querying. Both callers (the
`repair_nutrition_basis` command and the curation intake gate) need the same
two, so they live here instead of being built twice.
"""
from __future__ import annotations

from typing import Dict

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
