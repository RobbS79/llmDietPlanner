"""
Helpers for upserting StoreProduct rows and writing PriceRecord rows from
scraper output. Phase A of the LeafletOffer → PriceRecord migration: both
scrape paths dual-write here so readers can be migrated incrementally.
"""
import logging
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Optional

from django.utils import timezone

from ..models import (
    GroceryStore,
    PriceRecord,
    PriceSourceType,
    ScrapeRun,
    StoreProduct,
)
from .utils import normalize_ingredient_name

logger = logging.getLogger(__name__)


# Per-source confidence on write. PriceFreshnessPolicy.default_confidence
# is the catalog default; these values override based on the evidence we
# actually observed during the scrape.
CONFIDENCE_VERIFIED_DISCOUNT = Decimal('0.90')   # <del>/<s> markup detected
CONFIDENCE_CATALOG_DIRECT = Decimal('0.85')      # direct from store catalog page (Rohlik, Košík)
CONFIDENCE_LEAFLET_REGULAR = Decimal('0.70')     # leaflet but no discount markup
CONFIDENCE_LLM_ONLY = Decimal('0.50')            # extracted by LLM, no HTML cross-check


def _coerce_decimal(value: Any) -> Optional[Decimal]:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (ValueError, InvalidOperation):
        return None


def _resolve_store(shop_code: str) -> Optional[GroceryStore]:
    return GroceryStore.objects.filter(code=shop_code).first()


def _source_type_for(price_type: Optional[str]) -> str:
    if price_type == 'DISCOUNTED':
        return PriceSourceType.LEAFLET_DISCOUNT
    if price_type == 'LLM_ESTIMATED':
        return PriceSourceType.LLM_ESTIMATED
    return PriceSourceType.STORE_REGULAR


def _confidence_for(price_type: Optional[str], has_del_evidence: bool) -> Decimal:
    if price_type == 'DISCOUNTED' and has_del_evidence:
        return CONFIDENCE_VERIFIED_DISCOUNT
    if price_type == 'LLM_ESTIMATED':
        return CONFIDENCE_LLM_ONLY
    return CONFIDENCE_LEAFLET_REGULAR


def upsert_price_record(
    *,
    shop_code: str,
    offer_data: Dict[str, Any],
    valid_from,
    valid_until,
    scrape_run: Optional[ScrapeRun] = None,
    confidence: Optional[Decimal] = None,
) -> Optional[PriceRecord]:
    """
    Mirror an offer dict (the shape produced by both scrape paths) into the
    new PriceRecord schema. Idempotent on (store, normalized_name): the
    StoreProduct is `update_or_create`d, the PriceRecord is appended.

    Returns the PriceRecord or None if input was insufficient.
    """
    store = _resolve_store(shop_code)
    if not store:
        logger.warning(
            "upsert_price_record: no GroceryStore for shop_code=%s, skipping",
            shop_code,
        )
        return None

    raw_name = offer_data.get('ingredient_name') or offer_data.get('display_name') or ''
    normalized_name = normalize_ingredient_name(raw_name)
    if not normalized_name:
        return None

    price = _coerce_decimal(offer_data.get('price'))
    if price is None or price <= 0:
        return None

    display_name = (offer_data.get('display_name') or normalized_name)[:255]
    package_size = _coerce_decimal(offer_data.get('package_size'))
    package_unit = (offer_data.get('unit') or '')[:10]
    source_url = offer_data.get('source_url') or ''
    external_id = (offer_data.get('external_id') or '')[:255]

    store_product, _ = StoreProduct.objects.update_or_create(
        store=store,
        normalized_name=normalized_name[:255],
        defaults={
            'name': display_name,
            'package_size': package_size,
            'package_unit': package_unit,
            'source_url': source_url or None,
            'external_id': external_id,
            'is_active': True,
        },
    )

    price_type = offer_data.get('price_type')
    has_del_evidence = offer_data.get('original_price') is not None and price_type == 'DISCOUNTED'

    source_type = _source_type_for(price_type)
    if confidence is None:
        confidence = _confidence_for(price_type, has_del_evidence)

    original_price = _coerce_decimal(offer_data.get('original_price'))
    discount_percentage = offer_data.get('discount_percentage')
    if discount_percentage is not None:
        try:
            discount_percentage = int(discount_percentage)
            if discount_percentage < 0 or discount_percentage > 100:
                discount_percentage = None
        except (ValueError, TypeError):
            discount_percentage = None

    record = PriceRecord.objects.create(
        store_product=store_product,
        price=price,
        currency=offer_data.get('currency') or store.currency,
        source_type=source_type,
        confidence=confidence,
        valid_from=valid_from,
        valid_until=valid_until,
        original_price=original_price,
        discount_percentage=discount_percentage,
        scraped_at=timezone.now(),
        scrape_run=scrape_run,
        source_url=source_url or None,
    )

    return record
