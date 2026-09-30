"""Grams per "1 ks" for count-unit canonicals, read from CanonicalIngredient.
avg_piece_weight_g (seeded from data/canonical_ingredients.yaml `nutrition.piece_weight_g`).
Bridges recipe counts ("2 ks cibule") and weight-priced catalog rows."""
from typing import Dict


def load_piece_weights() -> Dict[str, float]:
    from diet_planner.models.catalog import CanonicalIngredient
    out: Dict[str, float] = {}
    rows = CanonicalIngredient.objects.exclude(avg_piece_weight_g=None).values_list(
        'slug', 'avg_piece_weight_g')
    for slug, grams in rows:
        try:
            g = float(grams)
        except (TypeError, ValueError):
            continue
        if g > 0:
            out[slug] = g
    return out


def clear_cache() -> None:
    """No-op, kept for compatibility. load_piece_weights() is deliberately
    uncached: seed_canonical_ingredients runs after the workers start on prod,
    so a process-wide cache would freeze a stale/empty map."""
