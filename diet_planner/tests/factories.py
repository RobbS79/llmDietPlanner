"""
Test factories for the new pricing schema (StoreProduct + PriceRecord +
CanonicalIngredient). Keeps setUps readable while we migrate off
LeafletOffer.
"""
from datetime import timedelta
from decimal import Decimal
from typing import Optional

from django.utils import timezone
from django.utils.text import slugify

from diet_planner.models import (
    CanonicalIngredient,
    GroceryStore,
    PriceRecord,
    PriceSourceType,
    StoreProduct,
)


def make_canonical(name: str, **kwargs) -> CanonicalIngredient:
    return CanonicalIngredient.objects.get_or_create(
        slug=slugify(name)[:255],
        defaults={'name': name, 'name_cs': name, **kwargs},
    )[0]


def make_price(
    *,
    store_code: str,
    normalized_name: str,
    price,
    source_type: str = PriceSourceType.STORE_REGULAR,
    display_name: Optional[str] = None,
    currency: Optional[str] = None,
    package_size=None,
    package_unit: str = '',
    canonical: Optional[CanonicalIngredient] = None,
    original_price=None,
    discount_percentage=None,
    valid_for_days: int = 7,
    confidence: Decimal = Decimal('0.85'),
) -> PriceRecord:
    """
    Create or update a StoreProduct + append a PriceRecord. Mirrors the
    production scraper write path so tests exercise the same code shape.
    """
    store = GroceryStore.objects.get(code=store_code)
    store_product, _ = StoreProduct.objects.update_or_create(
        store=store,
        normalized_name=normalized_name,
        defaults={
            'name': display_name or normalized_name.title(),
            'package_size': Decimal(str(package_size)) if package_size is not None else None,
            'package_unit': package_unit,
            'canonical_ingredient': canonical,
            'is_active': True,
        },
    )
    now = timezone.now()
    return PriceRecord.objects.create(
        store_product=store_product,
        price=Decimal(str(price)),
        currency=currency or store.currency,
        source_type=source_type,
        confidence=confidence,
        valid_from=now,
        valid_until=now + timedelta(days=valid_for_days),
        original_price=Decimal(str(original_price)) if original_price is not None else None,
        discount_percentage=discount_percentage,
        scraped_at=now,
    )
