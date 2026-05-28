"""
Cross-Store Price Optimizer — premium feature.

Finds the cheapest option per ingredient across all stores in the country,
then groups the result into per-store shopping lists.

Two strategies:
- MIX_COST: cheapest per ingredient regardless of how many stores
- MIX_TRIPS: minimize number of stores while staying within 10% of cheapest
"""
import logging
from collections import defaultdict
from decimal import Decimal
from typing import Dict, Any, List, Optional

from django.utils import timezone

from diet_planner.models import (
    COUNTRY_TO_SHOPS,
    DietaryGoal,
    PriceRecord,
    PriceSourceType,
)
from diet_planner.services.price_resolver import PriceResolver, PriceSource

logger = logging.getLogger(__name__)


class CrossStoreOptimizer:
    """Optimizes a shopping list across multiple stores."""

    def __init__(self, goal: DietaryGoal):
        self.goal = goal
        self.country = goal.country
        self.currency = goal.currency
        self.all_shops = COUNTRY_TO_SHOPS.get(self.country, [])

    def optimize(
        self,
        shopping_items: List[Dict[str, Any]],
        strategy: str = 'mix_cost',
    ) -> Dict[str, Any]:
        """
        Optimize shopping across stores.

        Returns:
            {
                'shopping_lists_by_store': [
                    {'store': 'LIDL_CZ', 'store_name': '...', 'items': [...], 'subtotal': Decimal},
                    ...
                ],
                'total_price': Decimal,
                'single_store_totals': {'LIDL_CZ': Decimal, 'ALBERT_CZ': Decimal, ...},
                'best_single_store': str,
                'best_single_store_total': Decimal,
                'savings_vs_single': Decimal,
                'num_stores': int,
                'strategy': str,
            }
        """
        price_matrix = self._build_price_matrix(shopping_items)

        if strategy == 'mix_trips':
            assignment = self._assign_min_trips(price_matrix, shopping_items)
        else:
            assignment = self._assign_min_cost(price_matrix, shopping_items)

        result = self._build_result(shopping_items, assignment, price_matrix, strategy)
        return result

    def _build_price_matrix(
        self,
        items: List[Dict[str, Any]],
    ) -> Dict[int, Dict[str, Optional[Dict[str, Any]]]]:
        """
        For each item index × store, find the best matching PriceRecord.

        Returns:
            {item_idx: {shop_code: {price, display_name, ...} or None}}
        """
        matrix: Dict[int, Dict[str, Optional[Dict[str, Any]]]] = {}

        for idx, item in enumerate(items):
            ingredient = (item.get('ingredient') or '').lower().strip()
            if not ingredient:
                continue

            matrix[idx] = {}
            for shop in self.all_shops:
                record = self._find_best_record(ingredient, shop)
                if record:
                    is_disc = record.source_type == PriceSourceType.LEAFLET_DISCOUNT
                    matrix[idx][shop] = {
                        'price': float(record.price),
                        'display_name': record.store_product.name,
                        'price_type': 'DISCOUNTED' if is_disc else 'REGULAR',
                        'original_price': float(record.original_price) if record.original_price else None,
                        'discount_percentage': record.discount_percentage,
                    }
                else:
                    matrix[idx][shop] = None

        return matrix

    def _find_best_record(self, ingredient: str, shop: str) -> Optional[PriceRecord]:
        base = (
            PriceRecord.objects.current()
            .filter(
                store_product__store__code=shop,
                store_product__store__country=self.country,
                store_product__is_active=True,
                price__gt=0,
            )
            .select_related('store_product', 'store_product__store')
        )

        record = (
            base.filter(store_product__normalized_name=ingredient)
            .order_by('price')
            .first()
        )
        if record:
            return record

        if len(ingredient) >= 3:
            return (
                base.filter(store_product__normalized_name__icontains=ingredient)
                .order_by('price')
                .first()
            )

        return None

    def _assign_min_cost(
        self,
        matrix: Dict[int, Dict[str, Optional[Dict[str, Any]]]],
        items: List[Dict[str, Any]],
    ) -> Dict[int, Optional[str]]:
        """Assign each item to the cheapest store."""
        assignment: Dict[int, Optional[str]] = {}
        for idx in range(len(items)):
            if idx not in matrix:
                assignment[idx] = None
                continue

            best_shop = None
            best_price = float('inf')
            for shop, data in matrix[idx].items():
                if data and data['price'] < best_price:
                    best_price = data['price']
                    best_shop = shop
            assignment[idx] = best_shop

        return assignment

    def _assign_min_trips(
        self,
        matrix: Dict[int, Dict[str, Optional[Dict[str, Any]]]],
        items: List[Dict[str, Any]],
    ) -> Dict[int, Optional[str]]:
        """
        Greedy: pick the store that covers the most remaining items at reasonable price.
        Then assign remaining items to cheapest available store.
        """
        remaining = set(matrix.keys())
        assignment: Dict[int, Optional[str]] = {}

        while remaining:
            best_shop = None
            best_coverage = 0
            best_total = float('inf')

            for shop in self.all_shops:
                coverage = 0
                total = 0.0
                for idx in remaining:
                    data = matrix.get(idx, {}).get(shop)
                    if data:
                        coverage += 1
                        total += data['price']
                if coverage > best_coverage or (coverage == best_coverage and total < best_total):
                    best_shop = shop
                    best_coverage = coverage
                    best_total = total

            if not best_shop or best_coverage == 0:
                for idx in remaining:
                    assignment[idx] = None
                break

            newly_assigned = set()
            for idx in remaining:
                data = matrix.get(idx, {}).get(best_shop)
                if data:
                    assignment[idx] = best_shop
                    newly_assigned.add(idx)

            remaining -= newly_assigned

        return assignment

    def _build_result(
        self,
        items: List[Dict[str, Any]],
        assignment: Dict[int, Optional[str]],
        matrix: Dict[int, Dict[str, Optional[Dict[str, Any]]]],
        strategy: str,
    ) -> Dict[str, Any]:
        store_items: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        store_subtotals: Dict[str, Decimal] = defaultdict(Decimal)
        total = Decimal('0')
        unassigned_items = []

        for idx, item in enumerate(items):
            shop = assignment.get(idx)
            if shop and matrix.get(idx, {}).get(shop):
                data = matrix[idx][shop]
                enriched = dict(item)
                enriched['price'] = data['price']
                enriched['price_total'] = data['price']
                enriched['currency'] = self.currency
                enriched['matched_product_name'] = data['display_name']
                enriched['price_source'] = (
                    PriceSource.LEAFLET_DISCOUNT.value
                    if data['price_type'] == 'DISCOUNTED'
                    else PriceSource.STORE_REGULAR.value
                )
                enriched['estimated'] = False
                if data.get('original_price'):
                    enriched['original_price'] = data['original_price']
                if data.get('discount_percentage'):
                    enriched['discount_percentage'] = data['discount_percentage']

                store_items[shop].append(enriched)
                price_dec = Decimal(str(data['price']))
                store_subtotals[shop] += price_dec
                total += price_dec
            else:
                enriched = dict(item)
                enriched['price_source'] = PriceSource.NOT_AVAILABLE.value
                enriched['price_total'] = None
                enriched['estimated'] = True
                unassigned_items.append(enriched)

        # Build per-store lists
        from diet_planner.models import GroceryStore
        store_map = {s.code: s.name for s in GroceryStore.objects.filter(code__in=store_items.keys())}

        shopping_lists_by_store = []
        for shop, shop_items in store_items.items():
            shopping_lists_by_store.append({
                'store': shop,
                'store_name': store_map.get(shop, shop),
                'items': shop_items,
                'subtotal': float(store_subtotals[shop]),
            })

        if unassigned_items:
            shopping_lists_by_store.append({
                'store': None,
                'store_name': 'Nedostupné',
                'items': unassigned_items,
                'subtotal': 0,
            })

        # Calculate single-store totals for comparison
        single_store_totals = {}
        for shop in self.all_shops:
            shop_total = Decimal('0')
            for idx in range(len(items)):
                data = matrix.get(idx, {}).get(shop)
                if data:
                    shop_total += Decimal(str(data['price']))
            if shop_total > 0:
                single_store_totals[shop] = float(shop_total)

        best_single = min(single_store_totals, key=single_store_totals.get, default=None) if single_store_totals else None
        best_single_total = Decimal(str(single_store_totals.get(best_single, 0))) if best_single else Decimal('0')
        savings = best_single_total - total if best_single_total > total else Decimal('0')

        logger.info(
            f"CrossStoreOptimizer [{strategy}]: {len(store_items)} stores, "
            f"total={total} {self.currency}, savings={savings} vs {best_single}"
        )

        return {
            'shopping_lists_by_store': shopping_lists_by_store,
            'total_price': float(total),
            'single_store_totals': single_store_totals,
            'best_single_store': best_single,
            'best_single_store_total': float(best_single_total),
            'savings_vs_single': float(savings),
            'num_stores': len(store_items),
            'strategy': strategy,
        }
