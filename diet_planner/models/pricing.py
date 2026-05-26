# diet_planner/models/pricing.py
"""
Pricing models: append-only price history, freshness policies, and custom managers.

PriceRecord is the single source of truth for all prices.
Every price carries its provenance (source type + confidence).
"""
from decimal import Decimal

from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from django.db.models import F, Q, Window
from django.db.models.functions import RowNumber
from django.utils import timezone


class PriceSourceType(models.TextChoices):
    LEAFLET_DISCOUNT = 'LEAFLET_DISCOUNT', 'Leaflet/Promotional Discount'
    STORE_REGULAR = 'STORE_REGULAR', 'Regular Store Price'
    STORE_API = 'STORE_API', 'Store API/Catalog'
    HISTORICAL_AVERAGE = 'HISTORICAL_AVERAGE', 'Historical Average'
    COMPETITOR_REFERENCE = 'COMPETITOR_REFERENCE', 'Competitor Reference'
    LLM_ESTIMATED = 'LLM_ESTIMATED', 'LLM Estimated'
    USER_REPORTED = 'USER_REPORTED', 'User-Reported'


class PriceRecordQuerySet(models.QuerySet):
    def current(self):
        now = timezone.now()
        return self.filter(
            Q(valid_until__isnull=True) | Q(valid_until__gt=now)
        )

    def best_price(self):
        return self.current().annotate(
            rank=Window(
                expression=RowNumber(),
                partition_by=[F('store_product')],
                order_by=[F('price').asc(), F('confidence').desc()],
            )
        ).filter(rank=1)

    def for_ingredient(self, canonical_ingredient_id):
        return self.current().filter(
            store_product__canonical_ingredient_id=canonical_ingredient_id,
            store_product__is_active=True,
        )

    def for_store(self, store_id):
        return self.current().filter(
            store_product__store_id=store_id,
            store_product__is_active=True,
        )


class PriceRecordManager(models.Manager):
    def get_queryset(self):
        return PriceRecordQuerySet(self.model, using=self._db)

    def current(self):
        return self.get_queryset().current()

    def best_price(self):
        return self.get_queryset().best_price()

    def for_ingredient(self, canonical_ingredient_id):
        return self.get_queryset().for_ingredient(canonical_ingredient_id)

    def for_store(self, store_id):
        return self.get_queryset().for_store(store_id)


class PriceRecord(models.Model):
    """
    Append-only price history. Never delete rows.
    The "current price" is the most recent non-expired record.
    """
    store_product = models.ForeignKey(
        'diet_planner.StoreProduct',
        on_delete=models.CASCADE,
        related_name='price_records',
    )
    price = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3)
    source_type = models.CharField(
        max_length=25,
        choices=PriceSourceType.choices,
        db_index=True,
    )
    confidence = models.DecimalField(
        max_digits=3, decimal_places=2,
        default=Decimal('0.50'),
        validators=[MinValueValidator(0), MaxValueValidator(1)],
    )
    valid_from = models.DateTimeField()
    valid_until = models.DateTimeField(null=True, blank=True)
    original_price = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
    )
    discount_percentage = models.IntegerField(
        null=True, blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    scraped_at = models.DateTimeField()
    scrape_run = models.ForeignKey(
        'diet_planner.ScrapeRun',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='price_records',
    )
    source_url = models.URLField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = PriceRecordManager()

    class Meta:
        ordering = ['-scraped_at']
        indexes = [
            models.Index(
                fields=['store_product', '-scraped_at'],
                name='idx_price_product_latest',
            ),
            models.Index(
                fields=['store_product', 'source_type', '-scraped_at'],
                name='idx_price_source_latest',
            ),
            models.Index(
                fields=['store_product', 'valid_from'],
                name='idx_price_timeseries',
            ),
            models.Index(
                fields=['valid_until', 'source_type'],
                name='idx_price_expiry',
            ),
        ]

    def __str__(self):
        return f"{self.store_product}: {self.price} {self.currency} ({self.source_type})"

    @property
    def is_expired(self):
        if self.valid_until is None:
            return False
        return timezone.now() > self.valid_until

    @property
    def is_discount(self):
        return self.source_type == PriceSourceType.LEAFLET_DISCOUNT


class PriceFreshnessPolicy(models.Model):
    """Per source-type TTL configuration."""

    source_type = models.CharField(
        max_length=25,
        choices=PriceSourceType.choices,
        unique=True,
    )
    ttl_hours = models.IntegerField(
        help_text="Hours before a price of this type is considered stale"
    )
    auto_expire = models.BooleanField(
        default=False,
        help_text="Auto-set valid_until when recording a price"
    )
    default_confidence = models.DecimalField(
        max_digits=3, decimal_places=2,
        default=Decimal('0.50'),
    )

    class Meta:
        verbose_name_plural = "Price Freshness Policies"

    def __str__(self):
        return f"{self.source_type}: {self.ttl_hours}h TTL"
