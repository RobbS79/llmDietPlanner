# diet_planner/models.py
"""
Diet Planner Models - Handles user dietary goals and plans with GDPR compliance.
Updated to support Historic Nutrition Context integration via the Genesis Sequence.
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
]

SHOP_TO_SOURCE_URL = {
    'LIDL_CZ': 'kupi.cz',
    'ROHLIK': 'rohlik.cz',
    'LIDL_SK': 'kupino.sk',
    'LUNYS': 'lunys.sk',
}

COUNTRY_TO_SHOPS = {
    'CZ': ['LIDL_CZ', 'ROHLIK'],
    'SK': ['LIDL_SK', 'LUNYS'],
}


def get_shops_for_country(country_code: str) -> list:
    """Get available shops for a given country code."""
    return COUNTRY_TO_SHOPS.get(country_code, [])


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
        help_text="User's dietary prompt, instructions, or main historic plan (encrypted)"
    )
    dietary_restrictions = EncryptedTextField(
        blank=True,
        null=True,
        help_text="Dietary restrictions or allergies (encrypted)"
    )

    # NEW FIELD: Authoritative Historic Plan context
    historic_plan_context = EncryptedTextField(
        blank=True, 
        null=True, 
        help_text="Full baseline nutrition history provided by the user for AI analysis (encrypted)"
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
    
    # Shop selection
    shop = models.CharField(
        max_length=20,
        choices=SHOP_CHOICES,
        blank=True,
        null=True,
        help_text="Shop where user wants to source ingredients"
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
        """
        _debug_log("B", "models.py:DietaryGoal.delete", "Delete method entry", {
            "goal_id": self.id,
            "user_id": self.user_id
        })
        
        try:
            if hasattr(self, 'dietary_plan'):
                try:
                    self.dietary_plan.delete()
                except Exception as e:
                    logger.warning(f"Error deleting related DietaryPlan: {str(e)}")
        except Exception as e:
            logger.warning(f"Error checking for related DietaryPlan: {str(e)}")
        
        # Access check for encryption sanity
        try:
            _ = self.prompt
            if self.dietary_restrictions:
                _ = self.dietary_restrictions
            if self.historic_plan_context:
                _ = self.historic_plan_context
        except Exception as e:
            logger.warning(f"Decryption error during deletion for Goal {self.id}: {str(e)}")
        
        super().delete(*args, **kwargs)


@receiver(pre_delete, sender=DietaryGoal)
def handle_dietary_goal_deletion(sender, instance, **kwargs):
    """
    Signal handler to ensure OneToOne relation cleanup.
    """
    try:
        if hasattr(instance, 'dietary_plan'):
            instance.dietary_plan.delete()
    except Exception as e:
        logger.warning(f"Signal cleanup error for Goal {instance.id}: {str(e)}")


class DietaryPlan(models.Model):
    """
    Generated dietary plan linked to a dietary goal.
    Contains meal ideas and shopping list (generated by LLM).
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
    
    class Meta:
        ordering = ['-scraped_at']
        indexes = [
            models.Index(fields=['shop', 'country', 'expires_at']),
            models.Index(fields=['ingredient_name', 'shop', 'country']),
        ]
    
    def __str__(self) -> str:
        return f"{self.display_name} ({self.shop}, {self.country})"


class Recipe(models.Model):
    """
    Detailed recipe information for a meal.
    Recipes are linked to meals via a unique meal identifier.
    """
    # Unique identifier for the meal (format: goal_id:day_number:meal_type:meal_index)
    meal_identifier = models.CharField(
        max_length=255,
        unique=True,
        db_index=True,
        help_text="Unique identifier for the meal (format: goal_id:day_number:meal_type:meal_index)"
    )
    
    # Link to the dietary goal for easy querying
    dietary_goal = models.ForeignKey(
        DietaryGoal,
        on_delete=models.CASCADE,
        related_name='recipes',
        help_text="The dietary goal this recipe belongs to"
    )
    
    # Recipe details
    name = models.CharField(
        max_length=255,
        help_text="Recipe name"
    )
    description = models.TextField(
        blank=True,
        null=True,
        help_text="Recipe description"
    )
    
    # Instructions (stored as JSON for structured steps)
    instructions = models.JSONField(
        default=list,
        help_text="Step-by-step cooking instructions (list of strings)"
    )
    
    # Ingredients (stored as JSON to match meal structure)
    ingredients = models.JSONField(
        default=list,
        help_text="List of ingredients with quantities"
    )
    
    # Additional recipe information
    preparation_time = models.IntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
        help_text="Preparation time in minutes"
    )
    cooking_time = models.IntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
        help_text="Cooking time in minutes"
    )
    servings = models.IntegerField(
        default=1,
        validators=[MinValueValidator(1)],
        help_text="Number of servings"
    )
    
    # Nutritional information (stored as JSON for flexibility)
    nutritional_info = models.JSONField(
        default=dict,
        blank=True,
        help_text="Nutritional information (calories, protein, carbs, fat, etc.)"
    )
    
    # Timestamps
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When the recipe was created (ISO-8601)"
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text="When the recipe was last updated (ISO-8601)"
    )
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['dietary_goal', '-created_at'], name='diet_plann_recipe_goal_idx'),
            models.Index(fields=['meal_identifier'], name='diet_plann_recipe_meal_id_idx'),
        ]
    
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