"""
Diet Planner Models - Handles user dietary goals and plans with GDPR compliance.
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
    """Write debug log entry."""
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
        with open(DEBUG_LOG_PATH, 'a') as f:
            f.write(json.dumps(log_entry) + '\n')
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


class DietaryGoal(models.Model):
    """
    Stores user dietary goals with encrypted PII data.
    GDPR compliant with encrypted sensitive information.
    """
    class StatusChoices(models.TextChoices):
        PENDING = 'pending', 'Pending'
        PROCESSING = 'processing', 'Processing'
        COMPLETED = 'completed', 'Completed'
        FAILED = 'failed', 'Failed'
    
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
    
    # Non-sensitive metadata
    status = models.CharField(
        max_length=20,
        choices=StatusChoices.choices,
        default=StatusChoices.PENDING,
        help_text="Processing status of the dietary goal"
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
        default='PLN',
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
        default='pl',
        help_text="Language code (ISO 639-1) for i18n support"
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
        ]
    
    def save(self, *args, **kwargs):
        """Auto-set currency based on country before saving."""
        if self.country and not self.currency:
            self.currency = get_currency_for_country(self.country)
        elif self.country:
            # Always update currency to match country
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
            # #region agent log
            _debug_log("B", "models.py:DietaryGoal.delete", "Checking for related DietaryPlan")
            # #endregion
            
            # Delete related DietaryPlan first to avoid constraint issues
            if hasattr(self, 'dietary_plan'):
                # #region agent log
                _debug_log("B", "models.py:DietaryGoal.delete", "DietaryPlan exists, deleting it")
                # #endregion
                
                try:
                    self.dietary_plan.delete()
                    # #region agent log
                    _debug_log("B", "models.py:DietaryGoal.delete", "DietaryPlan deleted successfully")
                    # #endregion
                except Exception as e:
                    error_msg = str(e)
                    error_trace = traceback.format_exc()
                    
                    # #region agent log
                    _debug_log("B", "models.py:DietaryGoal.delete", "Error deleting DietaryPlan", {
                        "error": error_msg,
                        "traceback": error_trace
                    })
                    # #endregion
                    
                    logger.warning(
                        f"Error deleting related DietaryPlan for DietaryGoal {self.id}: {error_msg}"
                    )
            else:
                # #region agent log
                _debug_log("B", "models.py:DietaryGoal.delete", "No DietaryPlan to delete")
                # #endregion
        except Exception as e:
            error_msg = str(e)
            error_trace = traceback.format_exc()
            
            # #region agent log
            _debug_log("B", "models.py:DietaryGoal.delete", "Error checking for DietaryPlan", {
                "error": error_msg,
                "traceback": error_trace
            })
            # #endregion
            
            logger.warning(
                f"Error checking for related DietaryPlan for DietaryGoal {self.id}: {error_msg}"
            )
        
        # Try to access encrypted fields before deletion to catch any decryption errors
        # This ensures we fail early if there's an encryption key issue
        # #region agent log
        _debug_log("C", "models.py:DietaryGoal.delete", "Before accessing encrypted fields")
        # #endregion
        
        try:
            _ = self.prompt
            # #region agent log
            _debug_log("C", "models.py:DietaryGoal.delete", "Successfully accessed prompt field")
            # #endregion
            
            if self.dietary_restrictions:
                _ = self.dietary_restrictions
                # #region agent log
                _debug_log("C", "models.py:DietaryGoal.delete", "Successfully accessed dietary_restrictions field")
                # #endregion
        except Exception as e:
            error_msg = str(e)
            error_trace = traceback.format_exc()
            
            # #region agent log
            _debug_log("C", "models.py:DietaryGoal.delete", "Error accessing encrypted fields", {
                "error": error_msg,
                "traceback": error_trace
            })
            # #endregion
            
            # Log the error but continue with deletion
            # This handles cases where encryption key might be missing or corrupted
            logger.warning(
                f"Error accessing encrypted fields for DietaryGoal {self.id} during deletion: {error_msg}. "
                "Continuing with deletion anyway."
            )
        
        # #region agent log
        _debug_log("B", "models.py:DietaryGoal.delete", "Before calling super().delete()")
        # #endregion
        
        # Proceed with normal deletion
        try:
            super().delete(*args, **kwargs)
            # #region agent log
            _debug_log("B", "models.py:DietaryGoal.delete", "super().delete() completed successfully")
            # #endregion
        except Exception as e:
            error_msg = str(e)
            error_trace = traceback.format_exc()
            
            # #region agent log
            _debug_log("B", "models.py:DietaryGoal.delete", "Error in super().delete()", {
                "error": error_msg,
                "traceback": error_trace
            })
            # #endregion
            
            raise  # Re-raise to see the actual error


@receiver(pre_delete, sender=DietaryGoal)
def handle_dietary_goal_deletion(sender, instance, **kwargs):
    """
    Signal handler to gracefully handle DietaryGoal deletion.
    Ensures related DietaryPlan is deleted first to avoid constraint issues.
    """
    try:
        # Delete related DietaryPlan if it exists (OneToOne relationship)
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
    Prices and availability are calculated by Django (not LLM).
    """
    dietary_goal = models.OneToOneField(
        DietaryGoal,
        on_delete=models.CASCADE,
        related_name='dietary_plan',
        help_text="The dietary goal this plan fulfils"
    )
    
    # LLM-generated content (structured data)
    meal_ideas = models.JSONField(
        default=list,
        help_text="LLM-generated meal ideas and recipes (JSON structure)"
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
