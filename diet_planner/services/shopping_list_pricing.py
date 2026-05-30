"""
Shopping-list pricing: honest price range + factual leaflet deals.

Replaces the old per-item "whole pack for a pinch" pricing with two honest
signals (see SHOPPING_LIST_PRICING_PLAN.md):

1. A regular-price RANGE across single-store baskets
   (X = cheapest store basket, Y = priciest), excluding pantry items the
   user says they already have.
2. Factual leaflet DEALS for items actually in the plan, bucketed into
   `current` and `upcoming`, and only when the discount is the cheapest
   source for that item across all stores.

This is deterministic (a direct query over scraped PriceRecord rows) and is
distinct from the LLM-driven `DietaryPlan.discount_optimization` advisor.

The DB-touching layer is thin; the decision logic (`classify_pantry_level`,
`qualify_deal`, `store_basket_total`) is pure and unit-tested without a DB.
"""
import logging
from collections import defaultdict
from decimal import Decimal
from typing import Any, Dict, List, Optional

from diet_planner.models import (
    COUNTRY_TO_SHOPS,
    GroceryStore,
    PriceRecord,
    PriceSourceType,
)
from diet_planner.services.canonical_lookup import resolve_canonical

logger = logging.getLogger(__name__)

# Fridge basics (decision #2/#4): the "Mám doma mléko, máslo, vejce" toggle.
# Curated rather than category-derived: not all DAIRY is a basic (a recipe
# cheese is not), only plain milk/butter/eggs. Multilingual (EN/CS/SK).
FRIDGE_BASIC_NAMES = {
    'milk', 'butter', 'egg', 'eggs',
    'mléko', 'mleko', 'máslo', 'maslo', 'vejce', 'vejce m', 'vajíčko', 'vajicko',
    'mlieko', 'vajcia', 'vajíčka', 'vajicka',
}

# A store must carry at least this fraction of the (non-pantry) basket to be
# ranked in the range — otherwise a store stocking 2 of 30 items would look
# "cheapest". Items it lacks are imputed at the cross-store average so the
# baskets being compared cover the same goods.
MIN_STORE_COVERAGE = 0.5


# --------------------------------------------------------------------------- #
# Pure decision logic (no DB) — unit-tested directly.
# --------------------------------------------------------------------------- #

def classify_pantry_level(ingredient_name: str, canonical) -> Optional[str]:
    """Classify an ingredient as a pantry basic, or None if it's a real buy.

    Returns 'fridge' (milk/butter/eggs), 'dry' (seeded pantry staple), or None.
    `canonical` is a CanonicalIngredient or None.
    """
    name = (ingredient_name or '').lower().strip()
    if name in FRIDGE_BASIC_NAMES:
        return 'fridge'
    if canonical is not None:
        for cand in (canonical.name, getattr(canonical, 'name_cs', ''), getattr(canonical, 'name_sk', '')):
            if cand and cand.lower().strip() in FRIDGE_BASIC_NAMES:
                return 'fridge'
        if canonical.is_pantry_staple:
            return 'dry'
    return None


def item_is_excluded(level: Optional[str], basics_on: bool, fridge_on: bool) -> bool:
    """Whether an item drops out of the basket given the pantry toggles."""
    if level == 'dry':
        return basics_on
    if level == 'fridge':
        return fridge_on
    return False


def store_basket_total(
    store: str,
    item_prices: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Total a single store's basket over the given items, imputing the
    cross-store average for items the store doesn't carry.

    `item_prices` is a list of {'avg': Decimal|None, 'by_store': {store: Decimal}}.
    Returns {'total': Decimal, 'covered': int, 'imputed': int, 'n': int} or None
    when the store carries nothing.
    """
    total = Decimal('0')
    covered = imputed = 0
    for entry in item_prices:
        by_store = entry['by_store']
        if store in by_store:
            total += by_store[store]
            covered += 1
        elif entry['avg'] is not None:
            total += entry['avg']
            imputed += 1
    if covered == 0:
        return None
    return {'total': total, 'covered': covered, 'imputed': imputed, 'n': len(item_prices)}


def qualify_deal(deal_price: Decimal, cheapest_elsewhere: Optional[Decimal]) -> bool:
    """Decision #3: a leaflet discount is a real deal only if it's the cheapest
    source for that item across all stores. `cheapest_elsewhere` is the lowest
    current price for the item at any *other* source (None if none exists)."""
    if cheapest_elsewhere is None:
        return True
    return deal_price <= cheapest_elsewhere


# --------------------------------------------------------------------------- #
# DB layer — load live prices for the plan's ingredients.
# --------------------------------------------------------------------------- #

def _ingredient_names(items: List[Dict[str, Any]]) -> List[str]:
    names = []
    for item in items:
        name = (item.get('ingredient') or '').lower().strip()
        if name:
            names.append(name)
    return names


def _best_current_per_store(ingredient: str, shops: List[str], country: str) -> Dict[str, Decimal]:
    """Cheapest currently-valid price for `ingredient` at each store."""
    base = (
        PriceRecord.objects.current()
        .filter(
            store_product__store__code__in=shops,
            store_product__store__country=country,
            store_product__is_active=True,
            price__gt=0,
        )
        .select_related('store_product', 'store_product__store')
    )
    rows = list(base.filter(store_product__normalized_name=ingredient))
    if not rows and len(ingredient) >= 3:
        rows = list(base.filter(store_product__normalized_name__icontains=ingredient))

    cheapest: Dict[str, Decimal] = {}
    for r in rows:
        code = r.store_product.store.code
        if code not in cheapest or r.price < cheapest[code]:
            cheapest[code] = r.price
    return cheapest


def _discount_records(ingredient: str, shops: List[str], country: str, bucket: str):
    """Current or upcoming LEAFLET_DISCOUNT records for an ingredient."""
    qs = PriceRecord.objects.upcoming() if bucket == 'upcoming' else PriceRecord.objects.current()
    qs = qs.filter(
        source_type=PriceSourceType.LEAFLET_DISCOUNT,
        store_product__store__code__in=shops,
        store_product__store__country=country,
        store_product__is_active=True,
        price__gt=0,
    ).select_related('store_product', 'store_product__store')
    rows = list(qs.filter(store_product__normalized_name=ingredient))
    if not rows and len(ingredient) >= 3:
        rows = list(qs.filter(store_product__normalized_name__icontains=ingredient))
    return rows


# --------------------------------------------------------------------------- #
# Public API.
# --------------------------------------------------------------------------- #

def compute_pricing(
    items: List[Dict[str, Any]],
    *,
    country: str,
    currency: str,
    basics_on: bool = True,
    fridge_on: bool = False,
) -> Dict[str, Any]:
    """Build the honest pricing payload for a plan's shopping list.

    Returns {'price_range': {...}|None, 'deals': [...], 'pantry_toggles': {...}}.
    """
    shops = COUNTRY_TO_SHOPS.get(country, [])
    store_names = dict(
        GroceryStore.objects.filter(code__in=shops).values_list('code', 'name')
    )

    # Resolve + classify each item once.
    resolved = []
    for item in items:
        name = (item.get('ingredient') or '').lower().strip()
        if not name:
            continue
        canonical = resolve_canonical(name)
        level = classify_pantry_level(name, canonical)
        resolved.append({'name': name, 'level': level, 'item': item})

    # ---- Range: per-store baskets over non-excluded items ----
    basket_entries = []
    for r in resolved:
        if item_is_excluded(r['level'], basics_on, fridge_on):
            continue
        by_store = _best_current_per_store(r['name'], shops, country)
        if not by_store:
            continue
        avg = sum(by_store.values()) / Decimal(len(by_store))
        basket_entries.append({'avg': avg, 'by_store': by_store})

    price_range = _build_range(basket_entries, shops, store_names, currency)

    # ---- Deals: current + upcoming, cheapest-source, grouped by store ----
    deals = _build_deals(resolved, shops, country, store_names, currency)

    return {
        'price_range': price_range,
        'deals': deals,
        'pantry_toggles': {'basics_on': basics_on, 'fridge_on': fridge_on},
    }


def _build_range(basket_entries, shops, store_names, currency) -> Optional[Dict[str, Any]]:
    if not basket_entries:
        return None
    n = len(basket_entries)
    baskets = {}
    for shop in shops:
        result = store_basket_total(shop, basket_entries)
        if result and (result['covered'] / n) >= MIN_STORE_COVERAGE:
            baskets[shop] = result
    if not baskets:
        return None

    low_store = min(baskets, key=lambda s: baskets[s]['total'])
    high_store = max(baskets, key=lambda s: baskets[s]['total'])
    return {
        'low': float(baskets[low_store]['total'].quantize(Decimal('0.01'))),
        'high': float(baskets[high_store]['total'].quantize(Decimal('0.01'))),
        'currency': currency,
        'store_low': low_store,
        'store_low_name': store_names.get(low_store, low_store),
        'store_high': high_store,
        'store_high_name': store_names.get(high_store, high_store),
        'items_counted': n,
    }


def _build_deals(resolved, shops, country, store_names, currency) -> List[Dict[str, Any]]:
    # store -> bucket -> list of item deals
    grouped: Dict[tuple, Dict[str, Any]] = {}

    for r in resolved:
        ingredient = r['name']
        current_prices = _best_current_per_store(ingredient, shops, country)
        cheapest_current = min(current_prices.values()) if current_prices else None

        for bucket in ('current', 'upcoming'):
            for rec in _discount_records(ingredient, shops, country, bucket):
                shop = rec.store_product.store.code
                # "Cheapest source" compares against the cheapest price at any
                # OTHER store (a discount being the cheapest in its own store is
                # not enough — it must beat the field).
                others = [p for s, p in current_prices.items() if s != shop]
                cheapest_elsewhere = min(others) if others else None
                if not qualify_deal(rec.price, cheapest_elsewhere):
                    continue

                baseline = rec.original_price or PriceRecord.latest_regular_for(rec.store_product_id)
                savings = None
                if baseline and baseline > rec.price:
                    savings = float((baseline - rec.price).quantize(Decimal('0.01')))

                key = (shop, bucket)
                if key not in grouped:
                    grouped[key] = {
                        'store': shop,
                        'store_name': store_names.get(shop, shop),
                        'status': bucket,
                        'valid_from': rec.valid_from,
                        'valid_until': rec.valid_until,
                        'currency': currency,
                        'items': [],
                        'store_total_savings': 0.0,
                    }
                group = grouped[key]
                group['items'].append({
                    'ingredient': r['item'].get('ingredient', ingredient),
                    'matched_product_name': rec.store_product.name,
                    'sale': float(rec.price.quantize(Decimal('0.01'))),
                    'original': float(baseline.quantize(Decimal('0.01'))) if baseline else None,
                    'savings': savings,
                })
                if savings:
                    group['store_total_savings'] = round(group['store_total_savings'] + savings, 2)
                # Track the widest validity window seen for the group header.
                if rec.valid_until and (group['valid_until'] is None or rec.valid_until > group['valid_until']):
                    group['valid_until'] = rec.valid_until

    # Serialize datetimes; current first, then upcoming; biggest savings first.
    deals = []
    for group in grouped.values():
        group['valid_from'] = group['valid_from'].isoformat() if group['valid_from'] else None
        group['valid_until'] = group['valid_until'].isoformat() if group['valid_until'] else None
        deals.append(group)
    deals.sort(key=lambda g: (g['status'] != 'current', -g['store_total_savings']))
    return deals
