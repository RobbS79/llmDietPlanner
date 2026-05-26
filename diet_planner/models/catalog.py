# diet_planner/models/catalog.py
"""
Catalog models: store registry, canonical ingredients, store products, and substitutes.

These models form the foundation of the multi-store price intelligence layer.
CanonicalIngredient is store-agnostic (what a recipe needs).
StoreProduct is store-specific (what a store sells), mapped to a canonical ingredient.
"""
from decimal import Decimal

from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from django.utils.text import slugify


class GroceryStore(models.Model):
    """A grocery chain in a specific country. Replaces SHOP_CHOICES CharField pattern."""

    code = models.CharField(
        max_length=30,
        unique=True,
        db_index=True,
        help_text="Machine identifier, e.g. LIDL_CZ, ALBERT_CZ"
    )
    name = models.CharField(max_length=100)
    chain = models.CharField(
        max_length=30,
        db_index=True,
        help_text="Chain family, e.g. LIDL, ALBERT, KAUFLAND"
    )
    country = models.CharField(max_length=2, db_index=True)
    currency = models.CharField(max_length=3)
    website_url = models.URLField(blank=True)
    scrape_url = models.URLField(blank=True)
    is_online_only = models.BooleanField(
        default=False,
        help_text="True for delivery-only stores like Rohlik, Kosik"
    )
    is_active = models.BooleanField(default=True)
    default_price_ttl_hours = models.IntegerField(
        default=168,
        help_text="Default hours before a price is considered stale"
    )

    class Meta:
        ordering = ['chain', 'country']
        indexes = [
            models.Index(fields=['country', 'is_active']),
        ]

    def __str__(self):
        return f"{self.name} ({self.code})"


class CanonicalIngredient(models.Model):
    """Store-agnostic ingredient. What a recipe references."""

    class Category(models.TextChoices):
        MEAT = 'meat', 'Meat & Poultry'
        FISH = 'fish', 'Fish & Seafood'
        DAIRY = 'dairy', 'Dairy'
        VEGETABLES = 'vegetables', 'Vegetables'
        FRUITS = 'fruits', 'Fruits'
        GRAINS = 'grains', 'Grains & Cereals'
        LEGUMES = 'legumes', 'Legumes'
        OILS = 'oils', 'Oils & Fats'
        SPICES = 'spices', 'Spices & Seasonings'
        EGGS = 'eggs', 'Eggs'
        NUTS = 'nuts', 'Nuts & Seeds'
        BEVERAGES = 'beverages', 'Beverages'
        CONDIMENTS = 'condiments', 'Condiments & Sauces'
        BAKING = 'baking', 'Baking'
        CANNED = 'canned', 'Canned & Preserved'
        FROZEN = 'frozen', 'Frozen'
        OTHER = 'other', 'Other'

    name = models.CharField(max_length=255, help_text="Canonical English name")
    name_cs = models.CharField(max_length=255, blank=True, help_text="Czech name")
    name_sk = models.CharField(max_length=255, blank=True, help_text="Slovak name")
    slug = models.SlugField(max_length=255, unique=True, db_index=True)
    category = models.CharField(
        max_length=50,
        choices=Category.choices,
        default=Category.OTHER,
        db_index=True,
    )
    default_unit = models.CharField(max_length=10, default='g')
    typical_unit = models.CharField(max_length=10, blank=True)
    avg_piece_weight_g = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True,
        help_text="Average weight per piece for ks-based items"
    )
    typical_package_sizes = models.JSONField(
        default=list, blank=True,
        help_text="Common package sizes, e.g. [250, 500, 1000]"
    )
    is_pantry_staple = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Always available; does not require a store match"
    )
    estimated_price_czk = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True,
        help_text="Fallback estimated price in CZK for pantry staples"
    )
    estimated_price_eur = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True,
        help_text="Fallback estimated price in EUR for pantry staples"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        indexes = [
            models.Index(fields=['category']),
            models.Index(fields=['is_pantry_staple']),
        ]
        verbose_name = "Canonical Ingredient"

    def __str__(self):
        return self.name

    def get_localized_name(self, language_code='en'):
        return getattr(self, f'name_{language_code}', None) or self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)[:255]
        super().save(*args, **kwargs)


class IngredientAlias(models.Model):
    """
    Alternative names for a canonical ingredient.
    Used to map LLM-generated or scraped names to the canonical form.
    """
    canonical_ingredient = models.ForeignKey(
        CanonicalIngredient,
        on_delete=models.CASCADE,
        related_name='aliases',
    )
    alias = models.CharField(max_length=255, db_index=True)
    language_code = models.CharField(max_length=5, blank=True)

    class Meta:
        unique_together = [['alias', 'language_code']]
        indexes = [
            models.Index(fields=['alias']),
        ]
        verbose_name_plural = "Ingredient Aliases"

    def __str__(self):
        return f"{self.alias} -> {self.canonical_ingredient.name}"


class IngredientSubstitute(models.Model):
    """Substitutability between canonical ingredients."""

    ingredient = models.ForeignKey(
        CanonicalIngredient,
        on_delete=models.CASCADE,
        related_name='substituted_by',
    )
    substitute = models.ForeignKey(
        CanonicalIngredient,
        on_delete=models.CASCADE,
        related_name='substitute_for',
    )
    quality_score = models.DecimalField(
        max_digits=3, decimal_places=2,
        default=Decimal('0.80'),
        validators=[MinValueValidator(0), MaxValueValidator(1)],
        help_text="1.0 = perfect substitute, 0.5 = acceptable"
    )
    conversion_factor = models.DecimalField(
        max_digits=5, decimal_places=3,
        default=Decimal('1.000'),
        help_text="Multiply quantity by this when substituting"
    )

    class Meta:
        unique_together = [['ingredient', 'substitute']]
        indexes = [
            models.Index(fields=['ingredient']),
        ]

    def __str__(self):
        return f"{self.ingredient.name} -> {self.substitute.name} ({self.quality_score})"


class StoreProduct(models.Model):
    """A specific product as sold by a specific store."""

    store = models.ForeignKey(
        GroceryStore,
        on_delete=models.CASCADE,
        related_name='products',
    )
    canonical_ingredient = models.ForeignKey(
        CanonicalIngredient,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='store_products',
    )
    external_id = models.CharField(max_length=255, blank=True)
    name = models.CharField(max_length=255)
    normalized_name = models.CharField(max_length=255, db_index=True)
    brand = models.CharField(max_length=100, blank=True)
    package_size = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        help_text="Size of the package (e.g., 500 for 500g)"
    )
    package_unit = models.CharField(max_length=10, blank=True)
    unit_conversion_factor = models.DecimalField(
        max_digits=10, decimal_places=4,
        default=Decimal('1.0000'),
        help_text="Base units of the canonical ingredient per 1 unit of this product"
    )
    source_url = models.URLField(blank=True, null=True)
    image_url = models.URLField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['store', 'name']
        indexes = [
            models.Index(fields=['store', 'normalized_name']),
            models.Index(fields=['store', 'canonical_ingredient']),
            models.Index(fields=['canonical_ingredient', 'is_active']),
        ]
        unique_together = [['store', 'normalized_name']]

    def __str__(self):
        return f"{self.name} ({self.store.code})"

    def save(self, *args, **kwargs):
        if not self.normalized_name:
            self.normalized_name = self.name.lower().strip()
        super().save(*args, **kwargs)
