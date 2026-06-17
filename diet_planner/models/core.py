# diet_planner/models.py
"""
Diet Planner Models - Handles user dietary goals and plans with GDPR compliance.
Updated to support a library of Historic Nutrition Plans for selection in the UI.
"""
from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator, MaxValueValidator
from encrypted_model_fields.fields import EncryptedCharField, EncryptedTextField
from django.utils import timezone
from django.db.models.signals import pre_delete
from django.dispatch import receiver
import logging
import json
import traceback
from pathlib import Path

logger = logging.getLogger(__name__)
DEBUG_LOG_PATH = Path(__file__).parent.parent.parent / '.cursor' / 'debug.log'


def _debug_log(hypothesis_id, location, message, data=None):
    """Write debug log entry to both file and Django logger."""
    import sys
    try:
        log_entry = {
            "sessionId": "debug-session",
            "runId": "run1",
            "hypothesisId": hypothesis_id,
            "location": location,
            "message": message,
            "data": data or {},
            "timestamp": __import__('time').time() * 1000
        }
        # Write to file (for local debugging)
        try:
            with open(DEBUG_LOG_PATH, 'a') as f:
                f.write(json.dumps(log_entry) + '\n')
        except Exception:
            pass
        # Log to Django logger at ERROR level (always visible)
        log_msg = f"[DEBUG {hypothesis_id}] {location}: {message} | Data: {json.dumps(data or {})}"
        logger.error(log_msg)  # Use ERROR level so it's always visible
        # Also print to stderr (captured by Gunicorn/DigitalOcean)
        print(f"[DEBUG {hypothesis_id}] {location}: {message} | Data: {json.dumps(data or {})}", file=sys.stderr, flush=True)
    except Exception:
        pass  # Don't break execution if logging fails


# Country to currency mapping
COUNTRY_CURRENCY_MAP = {
    'DE': 'EUR',  # Germany
    'AT': 'EUR',  # Austria
    'PL': 'PLN',  # Poland
    'CZ': 'CZK',  # Czech Republic
    'SK': 'EUR',  # Slovakia
    'HU': 'HUF',  # Hungary
    'RO': 'RON',  # Romania
    'BG': 'BGN',  # Bulgaria
}


def get_currency_for_country(country_code: str) -> str:
    """Get currency code for a given country code."""
    return COUNTRY_CURRENCY_MAP.get(country_code, 'EUR')


# Shop configuration
SHOP_CHOICES = [
    ('LIDL_CZ', 'Lidl (Czech Republic)'),
    ('ROHLIK', 'Rohlik.cz'),
    ('LIDL_SK', 'Lidl (Slovakia)'),
    ('LUNYS', 'Lunys.sk'),
    ('ALBERT_CZ', 'Albert (Czech Republic)'),
    ('KAUFLAND_CZ', 'Kaufland (Czech Republic)'),
    ('KAUFLAND_SK', 'Kaufland (Slovakia)'),
    ('PENNY_CZ', 'Penny (Czech Republic)'),
    ('TESCO_CZ', 'Tesco (Czech Republic)'),
    ('KOSIK_CZ', 'Košík.cz'),
]

SHOP_TO_SOURCE_URL = {
    'LIDL_CZ': 'kupi.cz',
    'ROHLIK': 'rohlik.cz',
    'LIDL_SK': 'kupino.sk',
    'LUNYS': 'lunys.sk',
    'ALBERT_CZ': 'kupi.cz',
    'KAUFLAND_CZ': 'kupi.cz',
    'KAUFLAND_SK': 'kupino.sk',
    'PENNY_CZ': 'kupi.cz',
    'TESCO_CZ': 'kupi.cz',
    'KOSIK_CZ': 'kosik.cz',
}

COUNTRY_TO_SHOPS = {
    'CZ': ['LIDL_CZ', 'ROHLIK', 'ALBERT_CZ', 'KAUFLAND_CZ', 'PENNY_CZ', 'TESCO_CZ', 'KOSIK_CZ'],
    'SK': ['LIDL_SK', 'LUNYS', 'KAUFLAND_SK'],
}


def get_shops_for_country(country_code: str) -> list:
    """Get available shops for a given country code."""
    return COUNTRY_TO_SHOPS.get(country_code, [])


class HistoricNutritionPlan(models.Model):
    """
    A library of nutrition plans uploaded by the user.
    Allows selection and reuse across different goals.
    GDPR compliant with encrypted content.
    """

    class ProcessingStatus(models.TextChoices):
        PENDING = 'pending', 'Pending'
        PROCESSING = 'processing', 'Processing'
        COMPLETED = 'completed', 'Completed'
        FAILED = 'failed', 'Failed'

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='historic_plans',
        help_text="User who owns this historic plan record"
    )
    name = models.CharField(
        max_length=255,
        help_text="A friendly name for this plan (e.g., 'Winter 2024 Clinical Diet')"
    )
    content = EncryptedTextField(
        blank=True,
        default='',
        help_text="The actual clinical document or past plan text (encrypted)"
    )

    # PDF upload fields
    pdf_file = models.BinaryField(
        null=True,
        blank=True,
        help_text="Raw PDF bytes stored in PostgreSQL"
    )
    pdf_filename = models.CharField(
        max_length=255,
        blank=True,
        default='',
        help_text="Original uploaded filename"
    )
    pdf_size_bytes = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="PDF file size in bytes"
    )

    # Extracted / processed data
    extracted_text = EncryptedTextField(
        blank=True,
        default='',
        help_text="Raw text extracted from PDF (encrypted)"
    )
    structured_constraints = EncryptedTextField(
        blank=True,
        default='',
        help_text="Gemini-summarized JSON of dietary constraints (encrypted)"
    )

    # Processing state
    processing_status = models.CharField(
        max_length=20,
        choices=ProcessingStatus.choices,
        default=ProcessingStatus.PENDING,
        help_text="PDF processing status"
    )
    processing_error = models.TextField(
        blank=True,
        default='',
        help_text="Error message if processing failed"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Historic Nutrition Plan"
        verbose_name_plural = "Historic Nutrition Plans"

    def __str__(self):
        return f"{self.name} ({self.user.username})"


class DietaryGoal(models.Model):
    """
    Stores user dietary goals with encrypted PII data.
    GDPR compliant with encrypted sensitive information.
    """
    class StatusChoices(models.TextChoices):
        PENDING = 'pending', 'Pending'
        AWAITING_PAYMENT = 'awaiting_payment', 'Awaiting Payment'
        PAYMENT_PENDING = 'payment_pending', 'Payment Pending'
        PAYMENT_CONFIRMED = 'payment_confirmed', 'Payment Confirmed'
        PROCESSING = 'processing', 'Processing'
        PROCESSING_MEAL_PLAN = 'processing_meal_plan', 'Generating Meal Plan'
        PROCESSING_SHOPPING_LIST = 'processing_shopping_list', 'Creating Shopping List'
        VALIDATING = 'validating', 'Validating'
        COMPLETED = 'completed', 'Completed'
        FAILED = 'failed', 'Failed'
        REFUND_ELIGIBLE = 'refund_eligible', 'Refund Eligible'
    
    # User reference (not encrypted - needed for queries)
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='dietary_goals',
        help_text="User who created this dietary goal"
    )
    
    # Encrypted fields for GDPR compliance (health/diet PII)
    prompt = EncryptedTextField(
        help_text="User's dietary prompt with goals/requirements (encrypted)"
    )
    dietary_restrictions = EncryptedTextField(
        blank=True,
        null=True,
        help_text="Dietary restrictions or allergies (encrypted)"
    )

    # NEW: Reference to a specific historic plan from the user's library
    historic_plan_reference = models.ForeignKey(
        HistoricNutritionPlan,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name='referenced_goals',
        help_text="The historic plan to be used as a baseline for this new goal"
    )
    
    # Non-sensitive metadata
    status = models.CharField(
        max_length=30,
        choices=StatusChoices.choices,
        default=StatusChoices.PENDING,
        help_text="Processing status of the dietary goal"
    )

    # Payment tracking fields
    is_free_generation = models.BooleanField(
        default=False,
        help_text="Whether this was a free generation (not charged)"
    )
    shopify_checkout_id = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="Shopify checkout ID if payment required"
    )
    shopify_order_id = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="Shopify order ID after payment (for fulfillment tracking)"
    )
    payment_confirmed_at = models.DateTimeField(
        blank=True,
        null=True,
        help_text="When payment was confirmed via webhook (ISO-8601)"
    )

    # Validation tracking
    validation_passed = models.BooleanField(
        default=False,
        help_text="Whether the generated plan passed validation"
    )
    validation_errors = models.JSONField(
        blank=True,
        null=True,
        help_text="List of validation errors if validation failed"
    )
    error_message = models.TextField(
        blank=True,
        null=True,
        help_text="User-friendly error message if generation failed"
    )
    
    # Location support (country/city determine currency automatically)
    country = models.CharField(
        max_length=2,
        choices=[
            ('DE', 'Germany'),
            ('PL', 'Poland'),
            ('CZ', 'Czech Republic'),
            ('SK', 'Slovakia'),
            ('HU', 'Hungary'),
            ('RO', 'Romania'),
            ('BG', 'Bulgaria'),
            ('AT', 'Austria'),
        ],
        help_text="Country where user wants to buy ingredients"
    )
    city = models.CharField(
        max_length=100,
        help_text="City where user wants to buy ingredients"
    )
    currency = models.CharField(
        max_length=3,
        default='CZK',
        choices=[
            ('PLN', 'Polish Złoty'),
            ('CZK', 'Czech Koruna'),
            ('HUF', 'Hungarian Forint'),
            ('EUR', 'Euro'),
            ('RON', 'Romanian Leu'),
            ('BGN', 'Bulgarian Lev'),
        ],
        help_text="Currency for price calculations (auto-determined from country)"
    )
    language_code = models.CharField(
        max_length=5,
        default='cs',
        help_text="Language code (ISO 639-1) for i18n support"
    )
    
    # Shop selection (CharField kept for backward compat; new code should use grocery_store FK)
    shop = models.CharField(
        max_length=20,
        choices=SHOP_CHOICES,
        blank=True,
        null=True,
        help_text="Shop where user wants to source ingredients"
    )
    grocery_store = models.ForeignKey(
        'diet_planner.GroceryStore',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='dietary_goals',
        help_text="Grocery store FK (preferred over shop CharField)"
    )

    class StoreMode(models.TextChoices):
        SINGLE = 'single', 'Single Store'
        MIX_COST = 'mix_cost', 'Mix - Minimize Cost'
        MIX_TRIPS = 'mix_trips', 'Mix - Minimize Trips'

    store_mode = models.CharField(
        max_length=20,
        choices=StoreMode.choices,
        default=StoreMode.SINGLE,
        help_text="Single store or cross-store optimization (premium)"
    )

    # Meal plan configuration (day-by-day plan)
    num_days = models.IntegerField(
        default=7,
        validators=[MinValueValidator(1), MaxValueValidator(30)],
        help_text="Number of days for the meal plan"
    )
    # Main meals (breakfast, lunch, dinner)
    breakfast = models.BooleanField(
        default=True,
        help_text="Include breakfast in the meal plan"
    )
    lunch = models.BooleanField(
        default=True,
        help_text="Include lunch in the meal plan"
    )
    dinner = models.BooleanField(
        default=True,
        help_text="Include dinner in the meal plan"
    )
    small_meals_per_day = models.IntegerField(
        default=2,
        validators=[MinValueValidator(0), MaxValueValidator(5)],
        help_text="Number of small meals per day"
    )
    snacks_per_day = models.IntegerField(
        default=1,
        validators=[MinValueValidator(0), MaxValueValidator(3)],
        help_text="Number of snacks per day"
    )
    
    # Timestamps (ISO-8601 compliant)
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When the goal was created (ISO-8601)"
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text="When the goal was last updated (ISO-8601)"
    )
    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When processing completed (ISO-8601)"
    )
    
    # Celery task tracking
    celery_task_id = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="Celery task ID for async processing"
    )
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['status']),
            models.Index(fields=['country']),
            models.Index(fields=['country', 'shop']),
        ]
    
    def save(self, *args, **kwargs):
        """Auto-set currency based on country before saving."""
        if self.country:
            self.currency = get_currency_for_country(self.country)
        super().save(*args, **kwargs)
    
    def __str__(self) -> str:
        """String representation - handles cases where user might be deleted."""
        try:
            username = self.user.username if self.user_id else "Unknown User"
        except Exception:
            username = f"User {self.user_id}" if self.user_id else "Unknown User"
        return f"Dietary Goal {self.id} - {username} - {self.status}"
    
    def delete(self, *args, **kwargs):
        """
        Override delete to handle encrypted fields gracefully.
        This prevents errors when deleting users with encrypted dietary goals.
        """
        # #region agent log
        _debug_log("B", "models.py:DietaryGoal.delete", "Delete method entry", {
            "goal_id": self.id,
            "user_id": self.user_id
        })
        # #endregion
        
        try:
            # Delete related DietaryPlan first to avoid constraint issues
            if hasattr(self, 'dietary_plan'):
                try:
                    self.dietary_plan.delete()
                except Exception as e:
                    logger.warning(f"Error deleting related DietaryPlan for DietaryGoal {self.id}: {str(e)}")
        except Exception as e:
            logger.warning(f"Error checking for related DietaryPlan for DietaryGoal {self.id}: {str(e)}")
        
        # Try to access encrypted fields before deletion to catch any decryption errors
        try:
            _ = self.prompt
            if self.dietary_restrictions:
                _ = self.dietary_restrictions
        except Exception as e:
            logger.warning(
                f"Error accessing encrypted fields for DietaryGoal {self.id} during deletion: {str(e)}. "
                "Continuing with deletion anyway."
            )
        
        super().delete(*args, **kwargs)


@receiver(pre_delete, sender=DietaryGoal)
def handle_dietary_goal_deletion(sender, instance, **kwargs):
    """
    Signal handler to gracefully handle DietaryGoal deletion.
    Ensures related DietaryPlan is deleted first to avoid constraint issues.
    """
    try:
        if hasattr(instance, 'dietary_plan'):
            instance.dietary_plan.delete()
    except Exception as e:
        logger.warning(
            f"Error deleting related DietaryPlan for DietaryGoal {instance.id}: {str(e)}"
        )


class DietaryPlan(models.Model):
    """
    Generated dietary plan linked to a dietary goal.
    Contains meal ideas and shopping list (generated by LLM).
    Prices are matched by LLM from available_ingredients. Shopping list includes matched product details.
    """
    dietary_goal = models.OneToOneField(
        DietaryGoal,
        on_delete=models.CASCADE,
        related_name='dietary_plan',
        help_text="The dietary goal this plan fulfils"
    )
    
    # LLM-generated content (structured data)
    days = models.JSONField(
        default=list,
        help_text="Day-by-day meal plan with main courses, small meals, and snacks (JSON structure)"
    )
    meal_ideas = models.JSONField(
        default=list,
        help_text="Legacy field: meal ideas (deprecated, use days instead)"
    )
    shopping_list = models.JSONField(
        default=list,
        help_text="LLM-generated shopping list with ingredients (JSON structure)"
    )
    
    # Django-calculated fields (not from LLM)
    total_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
        help_text="Total price calculated from database (not LLM guess)"
    )
    pantry_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
        help_text="Pro-rated share of pantry staples included in total_price"
    )
    currency = models.CharField(
        max_length=3,
        default='PLN',
        help_text="Currency of the total price"
    )
    
    # LLM usage tracking
    llm_input_tokens = models.IntegerField(
        null=True,
        blank=True,
        help_text="Number of input tokens used by LLM"
    )
    llm_output_tokens = models.IntegerField(
        null=True,
        blank=True,
        help_text="Number of output tokens used by LLM"
    )
    llm_total_tokens = models.IntegerField(
        null=True,
        blank=True,
        help_text="Total tokens used by LLM"
    )
    llm_cost_usd = models.DecimalField(
        max_digits=10,
        decimal_places=6,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
        help_text="Cost of LLM API call in USD"
    )
    llm_model_used = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        help_text="OpenAI model used for generation (e.g., gpt-4o-mini)"
    )
    
    # Shopping-list pricing pantry toggles (see SHOPPING_LIST_PRICING_PLAN.md §6).
    # When ON, that level of pantry staple is excluded from the regular-price
    # range (the user already has it at home).
    pantry_basics_on = models.BooleanField(
        default=True,
        help_text="User has dry basics (salt, oil, spices, ...) at home; exclude from price range"
    )
    pantry_fridge_on = models.BooleanField(
        default=False,
        help_text="User has fridge basics (milk, butter, eggs) at home; exclude from price range"
    )

    discount_optimization = models.JSONField(
        null=True,
        blank=True,
        help_text="LLM-suggested discount-based ingredient swaps with before/after comparison"
    )
    discount_optimization_applied = models.BooleanField(
        default=False,
        help_text="Whether the user has accepted and applied discount optimization"
    )

    grounding_debug = models.JSONField(
        null=True,
        blank=True,
        help_text="Recipe-grounding diagnostics: {facets, coverage} for this plan",
    )

    # Timestamps
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When the plan was generated (ISO-8601)"
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text="When the plan was last updated (ISO-8601)"
    )

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['dietary_goal']),
        ]

    def __str__(self) -> str:
        return f"Dietary Plan for Goal {self.dietary_goal.id}"


class LeafletOffer(models.Model):
    """
    Stores scraped leaflet offers from shops.
    Cached with expiry time to reduce scraping frequency.
    """
    shop = models.CharField(
        max_length=20,
        choices=SHOP_CHOICES,
        help_text="Shop identifier"
    )
    country = models.CharField(
        max_length=2,
        choices=[
            ('DE', 'Germany'),
            ('PL', 'Poland'),
            ('CZ', 'Czech Republic'),
            ('SK', 'Slovakia'),
            ('HU', 'Hungary'),
            ('RO', 'Romania'),
            ('BG', 'Bulgaria'),
            ('AT', 'Austria'),
        ],
        help_text="Country code"
    )
    ingredient_name = models.CharField(
        max_length=255,
        db_index=True,
        help_text="Normalized ingredient name (lowercase, for matching)"
    )
    display_name = models.CharField(
        max_length=255,
        help_text="Original display name from source"
    )
    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
        help_text="Price (optional, for price matching later)"
    )
    currency = models.CharField(
        max_length=3,
        help_text="Currency code"
    )

    # Price type tracking
    PRICE_TYPE_CHOICES = [
        ('DISCOUNTED', 'Discounted/Promotional'),
        ('REGULAR', 'Regular Price'),
        ('LLM_ESTIMATED', 'LLM Estimated'),
    ]
    price_type = models.CharField(
        max_length=20,
        choices=PRICE_TYPE_CHOICES,
        default='REGULAR',
        help_text="Type of price (from leaflet promotion, regular, or estimated)"
    )
    original_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        blank=True,
        null=True,
        validators=[MinValueValidator(0)],
        help_text="Original price before discount (for discounted items)"
    )
    discount_percentage = models.IntegerField(
        blank=True,
        null=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Discount percentage (for discounted items)"
    )

    unit = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        help_text="Unit of measurement (kg, piece, etc.)"
    )
    scraped_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When the offer was scraped (ISO-8601)"
    )
    expires_at = models.DateTimeField(
        db_index=True,
        help_text="When the cached data expires (ISO-8601, typically scraped_at + 24h)"
    )
    source_url = models.URLField(
        blank=True,
        null=True,
        help_text="Source URL (optional, for debugging)"
    )

    # Freshness lifecycle
    class FreshnessState(models.TextChoices):
        FRESH = 'fresh', 'Fresh'
        STALE = 'stale', 'Stale'
        EXPIRED = 'expired', 'Expired'

    freshness_state = models.CharField(
        max_length=10,
        choices=FreshnessState.choices,
        default=FreshnessState.FRESH,
        db_index=True,
    )
    stale_at = models.DateTimeField(null=True, blank=True)

    # Link to new schema (nullable during migration)
    store_product = models.ForeignKey(
        'diet_planner.StoreProduct',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='leaflet_offers',
        help_text="Link to StoreProduct in new catalog schema"
    )

    class Meta:
        ordering = ['-scraped_at']
        indexes = [
            models.Index(fields=['shop', 'country', 'expires_at']),
            models.Index(fields=['ingredient_name', 'shop', 'country']),
            models.Index(fields=['freshness_state']),
        ]

    def __str__(self) -> str:
        return f"{self.display_name} ({self.shop}, {self.country})"


class Recipe(models.Model):
    """
    Detailed recipe information for a meal.
    Recipes are linked to meals via a unique meal identifier.
    """
    meal_identifier = models.CharField(
        max_length=255,
        unique=True,
        db_index=True,
        help_text="Unique identifier for the meal (format: goal_id:day_number:meal_type:meal_index)"
    )
    dietary_goal = models.ForeignKey(
        DietaryGoal,
        on_delete=models.CASCADE,
        related_name='recipes',
        help_text="The dietary goal this recipe belongs to"
    )
    name = models.CharField(max_length=255, help_text="Recipe name")
    slug = models.SlugField(max_length=255, blank=True, db_index=True, help_text="URL-friendly name")
    food_category = models.CharField(max_length=50, blank=True, default='', db_index=True, help_text="Food category slug for stock image mapping")
    description = models.TextField(blank=True, null=True, help_text="Recipe description")
    instructions = models.JSONField(default=list, help_text="Step-by-step cooking instructions")
    ingredients = models.JSONField(default=list, help_text="List of ingredients with quantities")
    preparation_time = models.IntegerField(null=True, blank=True, validators=[MinValueValidator(0)])
    cooking_time = models.IntegerField(null=True, blank=True, validators=[MinValueValidator(0)])
    servings = models.IntegerField(default=1, validators=[MinValueValidator(1)])
    nutritional_info = models.JSONField(default=dict, blank=True)
    is_public = models.BooleanField(default=False, db_index=True, help_text="Visible on public recipe pages")
    # Recipe-grounding (B3/B4): provenance when this meal was served from the
    # curated real-recipe corpus. Blank for LLM-generated meals.
    source_name = models.CharField(max_length=200, blank=True, default='', help_text="Source site/creator for attribution")
    source_url = models.URLField(max_length=500, blank=True, default='', help_text="Linked source recipe (credit/backlink)")
    source_author = models.CharField(max_length=200, blank=True, default='', help_text="Original author if known")
    curated_recipe_slug = models.SlugField(max_length=255, blank=True, default='', help_text="CuratedRecipe.slug this was sourced from")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['dietary_goal', '-created_at'], name='diet_plann_recipe_goal_idx'),
            models.Index(fields=['meal_identifier'], name='diet_plann_recipe_meal_id_idx'),
            models.Index(fields=['is_public', '-created_at'], name='diet_plann_recipe_public_idx'),
        ]

    # A "recipe" with fewer than this many words across its instructions
    # is not substantive enough to feature publicly — it's a label, not a
    # cooking guide. Tuned to catch one-liners like "eat a small piece of
    # chocolate" while letting through real 4–8 step recipes.
    PUBLISH_MIN_WORDS = 25

    @staticmethod
    def count_instruction_words(instructions) -> int:
        if not instructions:
            return 0
        return sum(len(str(step).split()) for step in instructions)

    def has_substantive_instructions(self) -> bool:
        return self.count_instruction_words(self.instructions) >= self.PUBLISH_MIN_WORDS

    def save(self, *args, **kwargs):
        from django.utils.text import slugify
        if not self.slug and self.name:
            self.slug = slugify(self.name)[:255]
        # Auto-promote to public only when there's enough cooking guidance
        # to be worth indexing. Never auto-demote — admins / the backfill
        # command flip is_public off explicitly when they need to.
        if self.has_substantive_instructions():
            self.is_public = True
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return f"/recepty/{self.pk}/{self.slug}/"

    def __str__(self) -> str:
        return f"Recipe: {self.name} ({self.meal_identifier})"


class MealInstance(models.Model):
    """
    Tracks individual meal instances from a dietary plan.
    Allows users to mark meals as cooked and track cooking history.
    """
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='meal_instances',
        help_text="User who cooked this meal"
    )
    
    dietary_goal = models.ForeignKey(
        DietaryGoal,
        on_delete=models.CASCADE,
        related_name='meal_instances',
        help_text="The dietary goal this meal belongs to"
    )
    
    recipe = models.ForeignKey(
        Recipe,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='instances',
        help_text="The recipe for this meal (optional, can be null if recipe not yet created)"
    )
    
    # Meal identifier (same format as Recipe.meal_identifier)
    meal_identifier = models.CharField(
        max_length=255,
        db_index=True,
        help_text="Unique identifier for the meal (format: goal_id:day_number:meal_type:meal_index)"
    )
    
    # Meal metadata (stored for reference even if meal structure changes)
    meal_name = models.CharField(
        max_length=255,
        help_text="Name of the meal"
    )
    day_number = models.IntegerField(
        help_text="Day number in the meal plan"
    )
    meal_type = models.CharField(
        max_length=50,
        help_text="Type of meal (breakfast, lunch, dinner, small_meal, snack)"
    )
    
    # Cooking status
    is_cooked = models.BooleanField(
        default=False,
        help_text="Whether this meal has been cooked"
    )
    cooked_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the meal was marked as cooked (ISO-8601)"
    )
    
    # Optional notes from user
    notes = models.TextField(
        blank=True,
        null=True,
        help_text="User notes about cooking this meal"
    )
    
    # Timestamps
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When the meal instance was created (ISO-8601)"
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text="When the meal instance was last updated (ISO-8601)"
    )
    
    class Meta:
        ordering = ['-cooked_at', '-created_at']
        indexes = [
            models.Index(fields=['user', '-cooked_at'], name='dp_mealinst_user_idx'),
            models.Index(fields=['dietary_goal', 'day_number'], name='dp_mealinst_goal_idx'),
            models.Index(fields=['meal_identifier'], name='dp_mealinst_mealid_idx'),
            models.Index(fields=['is_cooked'], name='dp_mealinst_cooked_idx'),
        ]
        # Ensure a user can only have one instance per meal identifier
        unique_together = [['user', 'meal_identifier']]
    
    def __str__(self) -> str:
        cooked_status = "✓ Cooked" if self.is_cooked else "Not cooked"
        return f"{self.meal_name} - {cooked_status} (User: {self.user.username})"


class PriceFeedback(models.Model):
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='price_feedbacks',
    )
    dietary_plan = models.ForeignKey(
        DietaryPlan,
        on_delete=models.CASCADE,
        related_name='price_feedbacks',
    )
    estimated_total = models.DecimalField(max_digits=10, decimal_places=2)
    actual_total = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3)
    note = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self) -> str:
        diff = self.actual_total - self.estimated_total
        return f"Price feedback: {diff:+} {self.currency} (Plan {self.dietary_plan_id})"


@receiver(pre_delete, sender=User)
def handle_user_deletion(sender, instance, **kwargs):
    """
    Handle User deletion gracefully.
    Pre-deletes related DietaryGoal objects to avoid cascade issues with encrypted fields.
    """
    _debug_log("A", "signals.py:handle_user_deletion", "Signal handler entry", {
        "user_id": instance.id,
        "username": instance.username
    })
    
    try:
        # Get all dietary goals for this user
        dietary_goals = DietaryGoal.objects.filter(user=instance)
        goal_count = dietary_goals.count()
        
        if goal_count > 0:
            logger.info(
                f"Deleting {goal_count} dietary goal(s) for user {instance.username} (ID: {instance.id})"
            )
            
            # Delete each goal individually to handle encrypted fields gracefully
            for goal in dietary_goals:
                try:
                    goal.delete()
                except Exception as e:
                    logger.error(
                        f"Error deleting DietaryGoal {goal.id} for user {instance.username}: {str(e)}"
                    )
                    continue
            
            logger.info(
                f"Successfully handled deletion of dietary goals for user {instance.username}"
            )
    except Exception as e:
        logger.error(
            f"Error in handle_user_deletion signal for user {instance.username}: {str(e)}"
        )