"""
Static price-book estimator — the serve-time pricing path.

We no longer call individual shops (see [[pricing-pivot-static-book]]). This
estimates the whole-pack checkout cost of a plan's shopping list from a
maintained per-ingredient reference book (CZK per base unit + typical pack),
keyed by canonical ingredient. It is deterministic, needs no live catalog, and
exposes NO shop or brand names — those appear only in the separate leaflet
deals section.

The headline number is an *estimate* and is scoped to items the user actually
needs to buy: pantry staples the user says they already have (the "Mám doma
základy" / fridge-basics toggles) drop out of the total.
"""
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml
from django.conf import settings

from diet_planner.services.canonical_lookup import resolve_canonical
from diet_planner.services.piece_weights import load_piece_weights
from diet_planner.services.pricing_core import consumed_line_cost
from diet_planner.services.shopping_list_pricing import (
    classify_pantry_level,
    item_is_excluded,
)

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


class EstimatePricer:
    """Whole-pack cost estimator backed by the static price book."""

    def __init__(self, goal):
        self.goal = goal
        self.currency = getattr(goal, 'currency', 'CZK') or 'CZK'
        self.num_days = getattr(goal, 'num_days', None) or None
        book = _load_book()
        self.book = book['prices']
        self.book_currency = book.get('currency', 'CZK')

    # ── public API ────────────────────────────────────────────────────

    def price(
        self,
        items: List[Dict[str, Any]],
        *,
        basics_on: bool = True,
        fridge_on: bool = False,
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """Return (resolved_items, estimate). Each resolved item carries
        price_total/price_source/estimated and pantry metadata; the estimate
        summarises only the items that count toward the buy total."""
        resolved = [self._price_item(it) for it in items]

        counted_total = 0.0
        counted_items = priced_items = 0
        for r in resolved:
            excluded = item_is_excluded(r.get('pantry_level'), basics_on, fridge_on)
            r['pantry_excluded'] = excluded
            if excluded:
                continue
            counted_items += 1
            if r.get('price_total') is not None:
                counted_total += r['price_total']
                priced_items += 1

        total = round(counted_total, 2)
        estimate = {
            'total': total,
            'per_day': round(total / self.num_days, 2) if self.num_days else None,
            'per_portion': None,  # servings not modelled yet; never fabricate
            'currency': self.currency,
            'is_estimate': True,
            'priced_items': priced_items,
            'total_items': counted_items,
        }
        return resolved, estimate

    # ── internals ─────────────────────────────────────────────────────

    def _price_item(self, item: Dict[str, Any]) -> Dict[str, Any]:
        out = dict(item)
        name = (item.get('ingredient') or '').strip()
        canonical = resolve_canonical(name) if name else None
        # Prefer the canonical slug pre-mapped at curation: it travels with the
        # item and survives even when the free-text name can't be re-resolved
        # (type-adjective variants like "červené zelí" / "hnědá rýže"). Name
        # resolution is only a fallback. See [[pricing-catalog-id-resolution]].
        slug = item.get('canonical') or (canonical.slug if canonical else None)
        out['pantry_level'] = classify_pantry_level(name, canonical)
        # Strip any legacy shop/brand identity — no shop names leave this layer
        # (deals are the only place stores appear). Also drop stale fields left
        # by the old catalog resolver on re-priced plans.
        for k in ('matched_product_name', 'shop', 'assigned_store',
                  'assigned_store_name', 'cross_store', 'source_detail',
                  'packages_needed'):
            out.pop(k, None)

        entry = self.book.get(slug) if slug else None
        qty = self._num(item.get('quantity'))
        grams = load_piece_weights().get(slug) if slug else None
        cost = (self._consumed_cost(entry, qty, item.get('unit', ''), grams)
                if entry else None)

        if cost is not None:
            out['price_total'] = round(cost * self._fx(), 2)
            out['price'] = out['price_total']
            out['price_source'] = ('pantry_estimate'
                                   if out['pantry_level'] else 'estimate')
            out['estimated'] = True
        else:
            out['price_total'] = None
            out['price'] = None
            out['price_source'] = 'not_available'
            out['estimated'] = True
        return out

    def _consumed_cost(self, entry, qty, unit, grams=None) -> Optional[float]:
        """Pro-rated cost for one line — see pricing_core.consumed_line_cost."""
        return consumed_line_cost(entry, qty, unit, grams)

    def _fx(self) -> float:
        if self.currency == self.book_currency:
            return 1.0
        return _FX_FROM_CZK.get(self.currency, 1.0)

    @staticmethod
    def _num(v) -> Optional[float]:
        try:
            return float(v)
        except (TypeError, ValueError):
            return None
