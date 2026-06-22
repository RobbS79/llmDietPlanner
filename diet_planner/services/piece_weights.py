"""Typical edible piece weights (grams) for count-unit canonicals that stores
sell by weight.

Bridges the dimension gap between how recipes count an ingredient ("2 ks cibule")
and how the catalog prices it ("Cibule žlutá, síť 1 kg @ 19.90"). Without a piece
weight, build_price_book discards the weight-priced product (different dimension)
and the ingredient silently falls out of pricing; the pricer likewise can't cost
a count requirement against a weight-priced book entry. See the piece↔weight
bridge in build_price_book and EstimatePricer._consumed_cost.
"""
from functools import lru_cache
from pathlib import Path
from typing import Dict

import yaml
from django.conf import settings

WEIGHTS_PATH = (
    Path(settings.BASE_DIR) / 'diet_planner' / 'data' / 'typical_unit_weights.yaml'
)


@lru_cache(maxsize=1)
def load_piece_weights() -> Dict[str, float]:
    """Map canonical slug -> typical edible grams per piece. Cached per process."""
    try:
        data = yaml.safe_load(WEIGHTS_PATH.read_text(encoding='utf-8')) or {}
    except FileNotFoundError:
        return {}
    out: Dict[str, float] = {}
    for slug, grams in (data.get('grams_per_piece') or {}).items():
        try:
            g = float(grams)
        except (TypeError, ValueError):
            continue
        if g > 0:
            out[slug] = g
    return out


def clear_cache() -> None:
    """Drop the cached weights (call after editing the YAML in-process)."""
    load_piece_weights.cache_clear()
