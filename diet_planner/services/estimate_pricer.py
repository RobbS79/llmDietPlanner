"""
Static price-book loader — shared pricing primitives.

We no longer call individual shops (see [[pricing-pivot-static-book]]). This
module loads the maintained per-ingredient reference book (CZK per base unit +
typical pack), keyed by canonical ingredient, and exposes the currency-
conversion table. The per-recipe pricing engine (`recipe_pricing`) consumes
these; the old whole-plan `EstimatePricer` has been removed.
"""
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict

import yaml
from django.conf import settings

logger = logging.getLogger(__name__)

BOOK_PATH = Path(settings.BASE_DIR) / 'diet_planner' / 'data' / 'canonical_prices.yaml'

# Rough FX so non-CZK plans still get an estimate (the book is CZK). It's an
# estimate anyway; refine if a EUR book is ever maintained.
_FX_FROM_CZK = {'CZK': 1.0, 'EUR': 1 / 25.0}

@lru_cache(maxsize=1)
def _load_book() -> Dict[str, Any]:
    """Load and cache the YAML price book. Returns {'currency','prices':{slug:..}}."""
    try:
        data = yaml.safe_load(BOOK_PATH.read_text(encoding='utf-8')) or {}
    except FileNotFoundError:
        logger.error("Price book missing at %s — estimates will be empty", BOOK_PATH)
        data = {}
    data.setdefault('currency', 'CZK')
    data.setdefault('prices', {})
    return data


def reload_book():
    """Drop the cache (tests / after re-seeding)."""
    _load_book.cache_clear()
