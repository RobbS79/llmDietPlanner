"""
Price Resolver Service — database-only price resolution with zero LLM fabrication.

Every price shown to the user is either:
1. From a real scraped PriceRecord (LEAFLET_DISCOUNT or STORE_REGULAR)
2. A pantry staple estimate (PANTRY_ESTIMATE) — cheap basics, clearly labeled
3. Found in another store (CROSS_STORE_MATCH) — when selected store doesn't carry it
4. Historical average (HISTORICAL_AVERAGE) — from expired records
5. Explicitly marked as unavailable (NOT_AVAILABLE)

The LLM never sets prices. Period.
"""
import logging
import math
import re
from decimal import Decimal
from enum import Enum
from typing import Dict, Any, List, Optional

from django.utils import timezone

from diet_planner.models import (
    COUNTRY_TO_SHOPS,
    DietaryGoal,
    PriceRecord,
    PriceSourceType,
)
from diet_planner.services.catalog import PANTRY_STAPLES
from diet_planner.services.units import to_base

logger = logging.getLogger(__name__)


class PriceSource(str, Enum):
    LEAFLET_DISCOUNT = 'leaflet_discount'
    STORE_REGULAR = 'store_regular'
    PANTRY_ESTIMATE = 'pantry_estimate'
    CROSS_STORE_MATCH = 'cross_store_match'
    HISTORICAL_AVERAGE = 'historical_average'
    NOT_AVAILABLE = 'not_available'


# User-facing labels per source (Czech)
SOURCE_LABELS_CS = {
    PriceSource.LEAFLET_DISCOUNT: 'Akční cena z letáku',
    PriceSource.STORE_REGULAR: 'Běžná cena',
    PriceSource.PANTRY_ESTIMATE: 'Základní surovina – odhadovaná cena',
    PriceSource.CROSS_STORE_MATCH: 'Cena z jiného obchodu',
    PriceSource.HISTORICAL_AVERAGE: 'Průměrná historická cena',
    PriceSource.NOT_AVAILABLE: 'Cena nedostupná',
}

SOURCE_LABELS_EN = {
    PriceSource.LEAFLET_DISCOUNT: 'Leaflet promotional price',
    PriceSource.STORE_REGULAR: 'Regular store price',
    PriceSource.PANTRY_ESTIMATE: 'Pantry staple – estimated price',
    PriceSource.CROSS_STORE_MATCH: 'Price from another store',
    PriceSource.HISTORICAL_AVERAGE: 'Historical average price',
    PriceSource.NOT_AVAILABLE: 'Price unavailable',
}


class PriceResolver:
    """Resolves shopping list prices from database only."""

    def __init__(self, goal: DietaryGoal):
        self.goal = goal
        self.shop = goal.shop
        self.country = goal.country
        self.currency = goal.currency
        self.language_code = goal.language_code or 'cs'
        self._pantry_map = self._build_pantry_map()

    def resolve_shopping_list(
        self,
        shopping_items: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Resolve prices for all shopping list items from DB.

        Each returned item has:
            price_total, price_source, source_detail, estimated (bool),
            matched_product_name, valid_until
        """
        resolved = []
        stats = {s: 0 for s in PriceSource}
        total = Decimal('0')

        for item in shopping_items:
            r = self._resolve_single_item(item)
            resolved.append(r)
            stats[PriceSource(r['price_source'])] += 1
            if r.get('price_total'):
                total += Decimal(str(r['price_total']))

        priced = sum(1 for r in resolved if r.get('price_total'))
        logger.info(
            f"PriceResolver: {len(resolved)} items, {priced} priced, "
            f"total={total} {self.currency}, sources={dict(stats)}"
        )

        return resolved

    def _resolve_single_item(self, item: Dict[str, Any]) -> Dict[str, Any]:
        result = dict(item)
        ingredient = item.get('ingredient', '')
        catalog_id = item.get('catalog_id')
        is_pantry = item.get('pantry', False)
        quantity = self._parse_quantity(item.get('quantity', 0))
        unit = item.get('unit', 'g')

        # 1. Try catalog_id direct lookup
        if catalog_id:
            offer = self._lookup_by_id(catalog_id)
            if offer:
                return self._build_result(result, offer, quantity, unit)

        # 2. Try name match in selected store
        if self.shop and not is_pantry:
            offer = self._match_by_name(ingredient, self.shop, self.country)
            if offer:
                return self._build_result(result, offer, quantity, unit)

        # 3. Pantry staple
        if is_pantry or self._is_pantry_staple(ingredient):
            return self._build_pantry_result(result, ingredient, quantity, unit)

        # 4. Cross-store match (any store in the country)
        if self.shop:
            all_shops = COUNTRY_TO_SHOPS.get(self.country, [])
            for shop in all_shops:
                if shop == self.shop:
                    continue
                offer = self._match_by_name(ingredient, shop, self.country)
                if offer:
                    r = self._build_result(result, offer, quantity, unit)
                    r['price_source'] = PriceSource.CROSS_STORE_MATCH.value
                    r['source_detail'] = self._label(PriceSource.CROSS_STORE_MATCH)
                    r['cross_store'] = shop
                    return r

        # 5. Historical (expired offers)
        offer = self._match_by_name_historical(ingredient)
        if offer:
            r = self._build_result(result, offer, quantity, unit)
            r['price_source'] = PriceSource.HISTORICAL_AVERAGE.value
            r['source_detail'] = self._label(PriceSource.HISTORICAL_AVERAGE)
            r['estimated'] = True
            return r

        # 6. Not available
        result['price'] = None
        result['price_total'] = None
        result['price_source'] = PriceSource.NOT_AVAILABLE.value
        result['source_detail'] = self._label(PriceSource.NOT_AVAILABLE)
        result['estimated'] = True
        return result

    # ─── Lookup helpers ───────────────────────────────────────────────
    # Lookups return PriceRecord rows (via .current()) joined to their
    # StoreProduct + GroceryStore so _build_result can read display_name,
    # package, and shop code without extra queries.

    def _lookup_by_id(self, record_id: int) -> Optional[PriceRecord]:
        """`catalog_id` from the catalog text now refers to StoreProduct.id."""
        try:
            return (
                PriceRecord.objects.current()
                .filter(store_product_id=record_id, store_product__is_active=True)
                .select_related('store_product', 'store_product__store')
                .order_by('source_type', 'price')  # LEAFLET_DISCOUNT < STORE_REGULAR alphabetically
                .first()
            )
        except Exception:
            return None

    def _match_by_name(self, ingredient: str, shop: str, country: str) -> Optional[PriceRecord]:
        normalized = ingredient.lower().strip()
        if not normalized:
            return None

        base = (
            PriceRecord.objects.current()
            .filter(
                store_product__store__code=shop,
                store_product__store__country=country,
                store_product__is_active=True,
            )
            .select_related('store_product', 'store_product__store')
        )

        # Exact match, prefer discounted
        record = (
            base.filter(store_product__normalized_name=normalized)
            .order_by('source_type', 'price')
            .first()
        )
        if record:
            return record

        # Partial match
        if len(normalized) >= 3:
            record = (
                base.filter(store_product__normalized_name__icontains=normalized)
                .order_by('source_type', 'price', '-scraped_at')
                .first()
            )
            if record:
                return record

        return None

    def _match_by_name_historical(self, ingredient: str) -> Optional[PriceRecord]:
        """Match against any PriceRecord (including expired) for the same country."""
        normalized = ingredient.lower().strip()
        if not normalized or len(normalized) < 3:
            return None

        return (
            PriceRecord.objects
            .filter(
                store_product__store__country=self.country,
                store_product__normalized_name__icontains=normalized,
                store_product__is_active=True,
            )
            .select_related('store_product', 'store_product__store')
            .order_by('-scraped_at')
            .first()
        )

    # ─── Result builders ──────────────────────────────────────────────

    def _build_result(
        self,
        result: Dict[str, Any],
        record: PriceRecord,
        quantity: float,
        unit: str,
    ) -> Dict[str, Any]:
        store_product = record.store_product
        unit_price = float(record.price)
        product_unit = store_product.package_unit or ''
        # Prefer the structured package_size on StoreProduct; fall back to
        # parsing the display name for legacy rows where it's still NULL.
        package_size: Optional[float] = (
            float(store_product.package_size) if store_product.package_size else
            self._extract_package_size(store_product.name or '', product_unit)
        )
        packages_needed = self._calc_packages_needed(quantity, unit, package_size, product_unit)
        price_total = round(unit_price * packages_needed, 2)

        is_discount = record.source_type == PriceSourceType.LEAFLET_DISCOUNT
        source = PriceSource.LEAFLET_DISCOUNT if is_discount else PriceSource.STORE_REGULAR

        result['price'] = unit_price
        result['price_total'] = price_total
        result['currency'] = record.currency
        result['matched_product_name'] = store_product.name
        result['package_size'] = package_size
        result['packages_needed'] = packages_needed
        result['price_source'] = source.value
        result['source_detail'] = self._label(source)
        result['estimated'] = False
        result['shop'] = store_product.store.code

        if is_discount:
            # Phase D: prefer a real STORE_REGULAR baseline for the SAME
            # StoreProduct over inferred / scraped <del> markup. If we have
            # both leaflet discount + a recent regular record, compute the
            # discount % from data instead of trusting the scrape marker.
            baseline = PriceRecord.latest_regular_for(store_product.id)
            if baseline is not None and baseline > record.price:
                computed_pct = int(round(
                    (float(baseline) - float(record.price)) / float(baseline) * 100
                ))
                result['original_price'] = float(baseline)
                result['discount_percentage'] = computed_pct
            else:
                if record.original_price:
                    result['original_price'] = float(record.original_price)
                if record.discount_percentage:
                    result['discount_percentage'] = record.discount_percentage
            if record.valid_until:
                result['valid_until'] = record.valid_until.strftime('%Y-%m-%d')

        return result

    def _build_pantry_result(
        self,
        result: Dict[str, Any],
        ingredient: str,
        quantity: float,
        unit: str,
    ) -> Dict[str, Any]:
        pantry_info = self._pantry_map.get(ingredient.lower().strip())
        if not pantry_info:
            for key, info in self._pantry_map.items():
                if key in ingredient.lower() or ingredient.lower() in key:
                    pantry_info = info
                    break

        if pantry_info:
            price = pantry_info['estimated_price']
        else:
            price = 15.0 if self.currency == 'CZK' else 0.60

        result['price'] = price
        result['price_total'] = price
        result['currency'] = self.currency
        result['price_source'] = PriceSource.PANTRY_ESTIMATE.value
        result['source_detail'] = self._label(PriceSource.PANTRY_ESTIMATE)
        result['estimated'] = True
        return result

    # ─── Utility ──────────────────────────────────────────────────────

    def _parse_quantity(self, q) -> float:
        try:
            return float(q)
        except (ValueError, TypeError):
            return 0.0

    def _extract_package_size(self, display_name: str, unit: str) -> Optional[float]:
        if not display_name:
            return None
        patterns = [
            r'(\d+[\.,]?\d*)\s*(ks|piece|bal)',
            r'(\d+[\.,]?\d*)\s*(kg)',
            r'(\d+[\.,]?\d*)\s*(g)',
            r'(\d+[\.,]?\d*)\s*(l|litr)',
            r'(\d+[\.,]?\d*)\s*(ml)',
        ]
        for pattern in patterns:
            match = re.search(pattern, display_name, re.I)
            if match:
                try:
                    return float(match.group(1).replace(',', '.'))
                except ValueError:
                    continue
        return None

    # Defensive ceiling on package count. With correct unit conversion a real
    # recipe never needs this many of one product; a larger count means the
    # data is malformed (e.g. a missing/garbage unit), so we cap and log rather
    # than bill the user for it. (Prod plan #86: 1047 packs of chicken.)
    MAX_PACKAGES = 50

    def _calc_packages_needed(
        self,
        required_qty: float,
        required_unit: str,
        package_size: Optional[float],
        product_unit: str,
    ) -> int:
        if not package_size or package_size <= 0 or required_qty <= 0:
            return 1

        req_base, req_dim = to_base(required_qty, required_unit)
        pkg_base, pkg_dim = to_base(package_size, product_unit)

        # Only divide when both sides are the same measurement dimension
        # (both mass, both volume, both count). A gram requirement against a
        # per-piece product, or either unit unknown, can't be converted without
        # extra knowledge (e.g. avg weight per piece) — assume one package
        # rather than fabricate a count from incomparable units.
        if pkg_base <= 0 or req_dim is None or req_dim != pkg_dim:
            return 1

        packages = max(1, math.ceil(req_base / pkg_base))
        if packages > self.MAX_PACKAGES:
            logger.warning(
                "PriceResolver: capping %s packages at %s "
                "(need %s%s, package %s%s) — check unit data",
                packages, self.MAX_PACKAGES,
                required_qty, required_unit, package_size, product_unit,
            )
            packages = self.MAX_PACKAGES
        return packages

    def _is_pantry_staple(self, ingredient: str) -> bool:
        ingredient_lower = ingredient.lower().strip()
        return any(
            ingredient_lower in key or key in ingredient_lower
            for key in self._pantry_map
        )

    def _build_pantry_map(self) -> Dict[str, Dict[str, Any]]:
        m = {}
        for name_cs, name_en, cat, unit, price_czk, price_eur in PANTRY_STAPLES:
            price = price_czk if self.currency == 'CZK' else price_eur
            m[name_cs.lower()] = {
                'name': name_cs,
                'estimated_price': price,
                'currency': self.currency,
            }
            m[name_en.lower()] = {
                'name': name_en,
                'estimated_price': price,
                'currency': self.currency,
            }
        return m

    def _label(self, source: PriceSource) -> str:
        labels = SOURCE_LABELS_CS if self.language_code in ('cs', 'sk') else SOURCE_LABELS_EN
        return labels.get(source, source.value)
