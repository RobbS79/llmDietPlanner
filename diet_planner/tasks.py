"""
Diet Planner Tasks Module
=========================

This module holds the meal-pool generation task plus scraping/freshness,
research and protocol-PDF Celery tasks.

## Data Flow Overview:
1. User creates a DietaryGoal with per-slot counts.
2. `generate_meal_pool_task` → `services.meal_pool.build_meal_pool` (corpus
   first, Gemini for gaps).
3. DietaryPlan.meals is stored; shopping/pricing live per-recipe.

## Unit Handling:
- Standard units: g, kg, ml, l, ks (pieces)
- Base units for calculation: g (mass), ml (volume), ks (count)
- Conversions: kg -> g (*1000), l -> ml (*1000)
"""

from llm_diet_planner_project.celery_compat import shared_task
from django.db import transaction
from django.utils import timezone
from typing import Dict, Any, List, Optional
import logging
import re
import uuid
from decimal import Decimal
from collections import Counter

from .models import DietaryGoal, DietaryPlan
from .scrapers.scraper_service import ScraperService
from .services.meal_pool import build_meal_pool

try:
    from billiard.exceptions import SoftTimeLimitExceeded
except ImportError:  # pragma: no cover — billiard ships with celery
    class SoftTimeLimitExceeded(Exception):
        """Stand-in so the except clause stays valid without billiard."""
from analytics.events import track_plan_generated

logger = logging.getLogger(__name__)


# =============================================================================
# INGREDIENT PACKAGE KNOWLEDGE BASE
# =============================================================================
# Information about how ingredients are typically sold, their average weights/sizes,
# and common package sizes. Used for unit conversion and package size inference.

INGREDIENT_PACKAGE_INFO = {
    # Fruits sold per piece
    'avokádo': {'typical_unit': 'ks', 'avg_weight_g': 150, 'typical_packages': [1]},
    'avocado': {'typical_unit': 'ks', 'avg_weight_g': 150, 'typical_packages': [1]},
    'banán': {'typical_unit': 'ks', 'avg_weight_g': 120, 'typical_packages': [1]},
    'banana': {'typical_unit': 'ks', 'avg_weight_g': 120, 'typical_packages': [1]},
    'jablko': {'typical_unit': 'ks', 'avg_weight_g': 180, 'typical_packages': [1]},
    'apple': {'typical_unit': 'ks', 'avg_weight_g': 180, 'typical_packages': [1]},
    'pomeranč': {'typical_unit': 'ks', 'avg_weight_g': 200, 'typical_packages': [1]},
    'orange': {'typical_unit': 'ks', 'avg_weight_g': 200, 'typical_packages': [1]},
    'citron': {'typical_unit': 'ks', 'avg_weight_g': 100, 'typical_packages': [1]},
    'lemon': {'typical_unit': 'ks', 'avg_weight_g': 100, 'typical_packages': [1]},
    'rajče': {'typical_unit': 'ks', 'avg_weight_g': 150, 'typical_packages': [1]},
    'tomato': {'typical_unit': 'ks', 'avg_weight_g': 150, 'typical_packages': [1]},
    'okurka': {'typical_unit': 'ks', 'avg_weight_g': 300, 'typical_packages': [1]},
    'cucumber': {'typical_unit': 'ks', 'avg_weight_g': 300, 'typical_packages': [1]},
    
    # Oils and liquids - common bottle sizes
    'olivový olej': {'typical_unit': 'ml', 'typical_packages': [250, 500, 700, 1000]},
    'olive oil': {'typical_unit': 'ml', 'typical_packages': [250, 500, 700, 1000]},
    'slunečnicový olej': {'typical_unit': 'ml', 'typical_packages': [500, 1000]},
    'sunflower oil': {'typical_unit': 'ml', 'typical_packages': [500, 1000]},
    'řepkový olej': {'typical_unit': 'ml', 'typical_packages': [500, 1000]},
    'canola oil': {'typical_unit': 'ml', 'typical_packages': [500, 1000]},
    
    # Eggs - sold per piece (typically in packages of 6, 10, 15)
    'vejce': {'typical_unit': 'ks', 'avg_weight_g': 50, 'typical_packages': [6, 10, 15]},
    'egg': {'typical_unit': 'ks', 'avg_weight_g': 50, 'typical_packages': [6, 10, 15]},
    
    # Vegetables with typical package sizes
    'špenát': {'typical_unit': 'g', 'typical_packages': [150, 250, 300]},
    'spinach': {'typical_unit': 'g', 'typical_packages': [150, 250, 300]},
    'salát': {'typical_unit': 'g', 'typical_packages': [150, 200, 300]},
    'lettuce': {'typical_unit': 'g', 'typical_packages': [150, 200, 300]},
    'mix listové zeleniny': {'typical_unit': 'g', 'typical_packages': [150, 200, 300]},
    'leafy green mix': {'typical_unit': 'g', 'typical_packages': [150, 200, 300]},
    
    # Dairy products
    'mléko': {'typical_unit': 'ml', 'typical_packages': [500, 1000]},
    'milk': {'typical_unit': 'ml', 'typical_packages': [500, 1000]},
    'tvaroh': {'typical_unit': 'g', 'typical_packages': [250, 500]},
    'cottage cheese': {'typical_unit': 'g', 'typical_packages': [250, 500]},
    'jogurt': {'typical_unit': 'g', 'typical_packages': [150, 200, 250]},
    'yogurt': {'typical_unit': 'g', 'typical_packages': [150, 200, 250]},
    
    # Meat and fish - usually sold by weight but can have packages
    'kuřecí prsa': {'typical_unit': 'g', 'typical_packages': [500, 1000]},
    'chicken breast': {'typical_unit': 'g', 'typical_packages': [500, 1000]},
    'losos': {'typical_unit': 'g', 'typical_packages': [200, 300, 500]},
    'salmon': {'typical_unit': 'g', 'typical_packages': [200, 300, 500]},
    'tuňák': {'typical_unit': 'g', 'typical_packages': [100, 150, 200]},
    'tuna': {'typical_unit': 'g', 'typical_packages': [100, 150, 200]},
}


# =============================================================================
# QUANTITY VALIDATION CONSTANTS
# =============================================================================
# Maximum reasonable quantities per ingredient category for a weekly meal plan.
# These limits help catch LLM errors where quantities are wildly off.
# Format: 'category': {'max_<unit>': value, 'keywords': [...]}

QUANTITY_LIMITS = {
    'spices': {
        'max_g': 100,  # Max 100g of any spice for a week
        'keywords': ['salt', 'pepper', 'paprika', 'cumin', 'oregano', 'basil',
                     'thyme', 'rosemary', 'cinnamon', 'nutmeg', 'clove', 'ginger',
                     'sul', 'pepr', 'koření', 'sůl', 'pepř', 'kmín', 'bazalka']
    },
    'oils': {
        'max_ml': 500,  # Max 500ml of oil for a week
        'keywords': ['oil', 'olive', 'sunflower', 'canola', 'vegetable oil',
                     'olej', 'olivový', 'slunečnicový', 'řepkový']
    },
    'meat': {
        'max_g': 5000,  # Max 5kg of any single meat type
        'keywords': ['chicken', 'beef', 'pork', 'turkey', 'lamb', 'fish', 'salmon',
                     'kuře', 'hovězí', 'vepřové', 'krůta', 'jehně', 'ryba', 'losos',
                     'kuřecí', 'maso']
    },
    'eggs': {
        'max_ks': 30,  # Max 30 eggs for a week
        'keywords': ['egg', 'vejce', 'vajíčko', 'vajíčka']
    },
    'dairy': {
        'max_ml': 3000,  # Max 3L of milk/cream
        'max_g': 1000,  # Max 1kg of cheese/yogurt
        'keywords': ['milk', 'cream', 'yogurt', 'cheese', 'butter',
                     'mléko', 'smetana', 'jogurt', 'sýr', 'máslo', 'tvaroh']
    },
    'vegetables': {
        'max_g': 5000,  # Max 5kg of any vegetable
        'keywords': ['tomato', 'potato', 'carrot', 'onion', 'garlic', 'pepper',
                     'rajče', 'brambor', 'mrkev', 'cibule', 'česnek', 'paprika',
                     'salát', 'okurka', 'brokolice', 'špenát']
    },
    'fruits': {
        'max_g': 3000,  # Max 3kg of any fruit
        'keywords': ['apple', 'banana', 'orange', 'lemon', 'berry',
                     'jablko', 'banán', 'pomeranč', 'citron', 'jahoda', 'malina']
    },
    'grains': {
        'max_g': 2000,  # Max 2kg of rice/pasta/flour
        'keywords': ['rice', 'pasta', 'flour', 'bread', 'oat',
                     'rýže', 'těstoviny', 'mouka', 'chléb', 'ovesné']
    },
    'liquids': {
        'max_ml': 2000,  # Max 2L of sauces/vinegar/etc
        'keywords': ['sauce', 'vinegar', 'soy', 'broth', 'stock',
                     'omáčka', 'ocet', 'sójová', 'vývar', 'bujón']
    }
}


# =============================================================================
# VALIDATION FUNCTIONS
# =============================================================================

def get_ingredient_category(ingredient_name: str) -> Optional[str]:
    """
    Determine the category of an ingredient based on its name.

    Args:
        ingredient_name: Name of the ingredient (can be in any language)

    Returns:
        Category name (e.g., 'spices', 'meat') or None if not categorized

    Example:
        >>> get_ingredient_category('salt')
        'spices'
        >>> get_ingredient_category('chicken breast')
        'meat'
    """
    name_lower = ingredient_name.lower()
    for category, config in QUANTITY_LIMITS.items():
        for keyword in config.get('keywords', []):
            if keyword.lower() in name_lower:
                return category
    return None


@shared_task(bind=True, max_retries=3)
def scrape_leaflet_task(self, shop: str, country: str) -> Dict[str, Any]:
    """
    Async Celery task to scrape leaflet data for a shop/country.
    
    Checks cache first, scrapes if needed.
    
    Args:
        shop: Shop code (e.g., 'LIDL_CZ')
        country: Country code (e.g., 'CZ')
        
    Returns:
        Dict with scraping result information
    """
    try:
        logger.info(f"Scraping leaflet task started for {shop} ({country})")
        
        # Use ScraperService to get available ingredients (handles caching)
        ingredients = ScraperService.get_available_ingredients(shop, country)
        
        return {
            'status': 'success',
            'shop': shop,
            'country': country,
            'ingredient_count': len(ingredients),
        }
    except Exception as exc:
        logger.error(f"Error in scrape_leaflet_task for {shop} ({country}): {exc}", exc_info=True)
        raise self.retry(exc=exc, countdown=60)


@shared_task(bind=True, max_retries=0)
def research_recipe_task(self, job_id: int) -> Dict[str, Any]:
    """Refine-chat web recipe research (spec 2026-07-27). No Celery retries:
    the runner is internally fail-soft and always leaves the job in a terminal
    ready/failed state the chat can render honestly."""
    from diet_planner.services import recipe_research
    return recipe_research.run_research_job(job_id)


@shared_task(bind=True, max_retries=2)
def process_protocol_pdf_task(self, plan_id: int) -> Dict[str, Any]:
    try:
        from .services.protocol_processor import ProtocolProcessorService
        ProtocolProcessorService().process_protocol(plan_id)
        return {'status': 'success', 'plan_id': plan_id}
    except Exception as exc:
        logger.error(f"Error processing protocol PDF {plan_id}: {exc}", exc_info=True)
        raise self.retry(exc=exc, countdown=30)


LEGACY_GOAL_MESSAGE = (
    "This goal predates the meal pool model and cannot be regenerated; create a new plan."
)


class EmptyPoolError(ValueError):
    """build_meal_pool found nothing to serve — terminal, retrying won't help."""


def _mark_failed(goal_id: int, message: str) -> None:
    """Record a generation failure on the goal (REFUND_ELIGIBLE when payment is pending)."""
    try:
        goal = DietaryGoal.objects.get(id=goal_id)
        goal.error_message = message
        if goal.status == DietaryGoal.StatusChoices.PAYMENT_PENDING:
            goal.status = DietaryGoal.StatusChoices.REFUND_ELIGIBLE
            logger.warning(f"Goal {goal_id} marked REFUND_ELIGIBLE (order {goal.shopify_order_id})")
        else:
            goal.status = DietaryGoal.StatusChoices.FAILED
        goal.save(update_fields=['status', 'error_message'])
    except Exception as inner_exc:
        logger.error(f"Failed to update goal {goal_id} status: {inner_exc}")


def generate_meal_pool(goal_id: int, log_prefix: Optional[str] = None) -> Dict[str, Any]:
    """Pool-model generation (spec docs/superpowers/specs/2026-09-29-meal-pool-design.md).
    Corpus first, Gemini for gaps; stores DietaryPlan.meals.

    Plain function (no Celery). Returns {'status': 'success', 'plan_id'} or
    {'status': 'failed', 'reason'} for handled terminal cases. Any other failure
    marks the goal FAILED and re-raises (EmptyPoolError for an empty pool,
    SoftTimeLimitExceeded on timeout) so the caller decides whether to retry.
    """
    log_prefix = log_prefix or f"[POOL:{goal_id}:{str(uuid.uuid4())[:8]}]"
    try:
        goal = DietaryGoal.objects.get(id=goal_id)

        # Idempotency: a redelivered/retried task must not create a second plan.
        existing = DietaryPlan.objects.filter(dietary_goal_id=goal_id).order_by('id').first()
        if existing is not None:
            goal.status = DietaryGoal.StatusChoices.COMPLETED
            fields = ['status']
            if goal.completed_at is None:
                goal.completed_at = timezone.now()
                fields.append('completed_at')
            goal.save(update_fields=fields)
            logger.info(f"{log_prefix} plan already exists (plan {existing.id}); nothing to do")
            return {'status': 'success', 'plan_id': existing.id}

        counts = goal.pool_counts()
        if not any(counts.values()):
            logger.warning(f"{log_prefix} legacy goal without pool counts; refusing to generate")
            _mark_failed(goal_id, LEGACY_GOAL_MESSAGE)
            return {'status': 'failed', 'reason': 'legacy_goal'}

        goal.status = DietaryGoal.StatusChoices.PROCESSING
        goal.save(update_fields=['status'])
        logger.info(f"{log_prefix} Building pool {counts}")

        try:
            result = build_meal_pool(goal)
        except ValueError as exc:
            raise EmptyPoolError(str(exc)) from exc
        usage = result.llm_usage or {}
        with transaction.atomic():
            plan = DietaryPlan.objects.create(
                dietary_goal=goal,
                meals=result.meals,
                days=[],
                currency=goal.currency,
                llm_model_used=usage.get('model'),
                llm_input_tokens=usage.get('input_tokens'),
                llm_output_tokens=usage.get('output_tokens'),
                llm_total_tokens=usage.get('total_tokens'),
                llm_cost_usd=usage.get('cost_usd'),
                grounding_debug=result.grounding_debug,
            )
            goal.status = DietaryGoal.StatusChoices.COMPLETED
            goal.completed_at = timezone.now()
            goal.save(update_fields=['status', 'completed_at'])
        try:
            track_plan_generated(goal.user, goal.id)
        except Exception:
            logger.exception("track_plan_generated failed (non-fatal)")
        cov = result.grounding_debug.get('coverage', {})
        logger.info(f"{log_prefix} Plan {plan.id}: {len(result.meals)} meals, "
                    f"curated {cov.get('filled')}/{cov.get('total')}, "
                    f"shortfall {result.grounding_debug.get('shortfall')}")
        return {'status': 'success', 'plan_id': plan.id}

    except SoftTimeLimitExceeded:
        logger.error(f"{log_prefix} soft time limit exceeded")
        _mark_failed(goal_id, "Meal plan generation failed: timed out")
        raise
    except Exception as exc:
        logger.error(f"{log_prefix} failed: {exc}", exc_info=True)
        _mark_failed(goal_id, f"Meal plan generation failed: {exc}")
        raise


@shared_task(bind=True, max_retries=3)
def generate_meal_pool_task(self, goal_id: int) -> Dict[str, Any]:
    """Celery wrapper around generate_meal_pool. Empty pool and soft time limit
    are terminal (goal already FAILED, no retry); anything else retries with backoff."""
    try:
        return generate_meal_pool(goal_id)
    except SoftTimeLimitExceeded:
        return {'status': 'failed', 'reason': 'soft_time_limit'}
    except EmptyPoolError:
        return {'status': 'failed', 'reason': 'empty_pool'}
    except Exception as exc:
        raise self.retry(exc=exc, countdown=30 * (2 ** self.request.retries))


# =============================================================================
# UNIT CONVERSION FUNCTIONS
# =============================================================================

def normalize_unit(unit: str) -> str:
    """
    Standardize units for comparison across different languages and formats.

    Supported units:
    - Mass: g (grams), kg (kilograms)
    - Volume: ml (milliliters), l (liters)
    - Count: ks (pieces/kusy)

    Args:
        unit: Unit string in any format (e.g., 'kilogram', 'g.', 'kusů')

    Returns:
        Normalized unit code (g, kg, ml, l, ks) or original if unknown

    Examples:
        >>> normalize_unit('kilogramy')
        'kg'
        >>> normalize_unit('pcs')
        'ks'
    """
    if not unit:
        return ''
    u = str(unit).lower().strip()

    # Comprehensive mapping for multiple languages (Czech, Slovak, Polish, English)
    mapping = {
        # Mass - kilograms
        'kg': 'kg', 'kilogram': 'kg', 'kilogramy': 'kg', 'kilogramů': 'kg',
        'kilogramow': 'kg', 'kg.': 'kg',
        # Mass - grams
        'g': 'g', 'gram': 'g', 'gramy': 'g', 'gramů': 'g', 'gramow': 'g', 'g.': 'g',
        # Volume - liters
        'l': 'l', 'litr': 'l', 'litry': 'l', 'litrů': 'l', 'litrow': 'l',
        'liter': 'l', 'litre': 'l', 'l.': 'l',
        # Volume - milliliters
        'ml': 'ml', 'mililitr': 'ml', 'mililitry': 'ml', 'mililitrů': 'ml',
        'milliliter': 'ml', 'millilitre': 'ml', 'ml.': 'ml',
        # Count - pieces
        'ks': 'ks', 'kus': 'ks', 'kusy': 'ks', 'kusů': 'ks', 'kusow': 'ks',
        'piece': 'ks', 'pieces': 'ks', 'pcs': 'ks', 'pc': 'ks', 'szt': 'ks',
        'sztuk': 'ks', 'sztuki': 'ks',
    }
    return mapping.get(u, u)


def convert_to_base_value(val: Decimal, unit: str) -> Decimal:
    """
    Convert value to base metric unit for calculations.

    Base units:
    - Mass: grams (g)
    - Volume: milliliters (ml)
    - Count: pieces (ks) - no conversion

    Args:
        val: Numeric value to convert
        unit: Unit string (will be normalized)

    Returns:
        Value converted to base unit

    Examples:
        >>> convert_to_base_value(Decimal('1.5'), 'kg')
        Decimal('1500')  # 1.5kg = 1500g
        >>> convert_to_base_value(Decimal('2'), 'l')
        Decimal('2000')  # 2l = 2000ml
    """
    u = normalize_unit(unit)
    if u == 'kg':
        return val * 1000  # kg -> g
    if u == 'l':
        return val * 1000  # l -> ml
    return val  # g, ml, ks remain unchanged


# =============================================================================
# PACKAGE SIZE INFERENCE AND UNIT CONVERSION
# =============================================================================

def get_ingredient_package_info(ingredient_name: str) -> Optional[Dict[str, Any]]:
    """
    Lookup package information for an ingredient from knowledge base.
    
    Handles normalized names and aliases (e.g., 'avokádo' and 'avocado').
    
    Args:
        ingredient_name: Ingredient name (can be in any language)
        
    Returns:
        Dict with package info or None if not found:
        {
            'typical_unit': 'ks' | 'g' | 'ml',
            'avg_weight_g': float (for piece-based items),
            'typical_packages': [list of common package sizes]
        }
    """
    if not ingredient_name:
        return None
    
    name_lower = ingredient_name.lower().strip()
    
    # Direct lookup
    if name_lower in INGREDIENT_PACKAGE_INFO:
        return INGREDIENT_PACKAGE_INFO[name_lower]
    
    # Try normalized lookup (remove accents, special chars)
    normalized = re.sub(r'[^a-z0-9\s]', '', name_lower.lower())
    normalized = re.sub(r'\s+', ' ', normalized).strip()
    
    if normalized in INGREDIENT_PACKAGE_INFO:
        return INGREDIENT_PACKAGE_INFO[normalized]
    
    # Try partial match (e.g., "avokádo bio" matches "avokádo")
    for key, info in INGREDIENT_PACKAGE_INFO.items():
        if key in name_lower or name_lower in key:
            return info
    
    return None


def infer_package_size(ingredient_name: str, product_unit: str, matched_offers: List[Dict[str, Any]], context_id: str = "", goal_id: int = 0) -> Optional[Decimal]:
    """
    Infer package size when it's missing from the matched product.
    
    Strategy:
    1. Check ingredient knowledge base
    2. Look at actual offers to see what packages exist
    3. Return most reasonable package size
    
    Args:
        ingredient_name: Name of the ingredient
        product_unit: Unit from the shop product (e.g., 'ks', 'g', 'ml')
        matched_offers: List of matched offers (can be empty)
        context_id: Context ID for logging
        goal_id: Goal ID for logging
        
    Returns:
        Decimal package size or None if can't infer
    """
    log_prefix = f"[SHOPPING_LIST:{goal_id}:{context_id}]" if context_id and goal_id else ""
    
    # Strategy 1: Check actual offers first - most reliable
    if matched_offers:
        package_sizes = []
        for offer in matched_offers:
            pkg_size = offer.get('package_size')
            unit = offer.get('unit', '')
            if pkg_size and normalize_unit(unit) == normalize_unit(product_unit):
                package_sizes.append(Decimal(str(pkg_size)))
        
        if package_sizes:
            # Return most common package size
            size_counts = Counter(package_sizes)
            most_common = size_counts.most_common(1)[0][0]
            if log_prefix:
                logger.debug(f"{log_prefix} DETAIL: Inferred package_size={most_common} for '{ingredient_name}' from {len(package_sizes)} offers")
            return most_common
    
    # Strategy 2: Check knowledge base
    info = get_ingredient_package_info(ingredient_name)
    if info:
        typical_unit = info.get('typical_unit', '')
        if normalize_unit(typical_unit) == normalize_unit(product_unit):
            typical_packages = info.get('typical_packages', [])
            if typical_packages:
                # For piece-based items, return 1 piece
                if typical_unit == 'ks':
                    if log_prefix:
                        logger.debug(f"{log_prefix} DETAIL: Inferred package_size=1 piece for '{ingredient_name}' from knowledge base")
                    return Decimal('1')
                # For other units, return most common package size
                else:
                    most_common = Decimal(str(typical_packages[0]))
                    if log_prefix:
                        logger.debug(f"{log_prefix} DETAIL: Inferred package_size={most_common} for '{ingredient_name}' from knowledge base")
                    return most_common
    
    # Strategy 3: Default inference based on unit
    if normalize_unit(product_unit) == 'ks':
        # Piece-based items default to 1 piece
        if log_prefix:
            logger.debug(f"{log_prefix} DETAIL: Default inference: package_size=1 for piece-based '{ingredient_name}'")
        return Decimal('1')
    elif normalize_unit(product_unit) in ['g', 'ml']:
        # For g/ml without package size, assume it's per unit (1g or 1ml)
        # This is a fallback - ideally we'd have better data
        if log_prefix:
            logger.debug(f"{log_prefix} DETAIL: Default inference: package_size=1 for '{ingredient_name}' (unit: {product_unit})")
        return Decimal('1')
    
    if log_prefix:
        logger.warning(f"{log_prefix} WARNING: Could not infer package_size for '{ingredient_name}' (unit: {product_unit})")
    return None


def find_appropriate_package_size(required_qty: Decimal, required_unit: str, available_packages: List[Decimal], product_unit: str, context_id: str = "", goal_id: int = 0) -> Optional[Decimal]:
    """
    Find the smallest package size that satisfies the requirement.
    
    Always rounds UP - if need 450ml and packages are [250ml, 500ml, 700ml],
    returns 700ml (smallest that fits, since 500ml isn't enough).
    
    Args:
        required_qty: Required quantity
        required_unit: Unit of required quantity
        available_packages: List of available package sizes
        product_unit: Unit of product packages
        context_id: Context ID for logging
        goal_id: Goal ID for logging
        
    Returns:
        Decimal package size or None if no suitable package found
    """
    log_prefix = f"[SHOPPING_LIST:{goal_id}:{context_id}]" if context_id and goal_id else ""
    
    if not available_packages:
        return None
    
    # Convert required quantity to base unit
    req_base = convert_to_base_value(required_qty, required_unit)
    
    # Sort packages ascending
    sorted_packages = sorted(available_packages)
    
    # Find smallest package that satisfies requirement
    for pkg_size in sorted_packages:
        pkg_base = convert_to_base_value(pkg_size, product_unit)
        if pkg_base >= req_base:
            if log_prefix:
                logger.debug(
                    f"{log_prefix} DETAIL: Selected package {pkg_size}{product_unit} "
                    f"(need {required_qty}{required_unit} = {req_base} base units)"
                )
            return pkg_size
    
    # If no package is large enough, return largest available (user will need multiple)
    largest = sorted_packages[-1]
    if log_prefix:
        logger.debug(
            f"{log_prefix} DETAIL: No single package satisfies {required_qty}{required_unit}, "
            f"using largest available: {largest}{product_unit}"
        )
    return largest


def parse_numeric(val: Any) -> Optional[Decimal]:
    """
    Extract decimal number from various formats.

    Handles:
    - Numbers: int, float, Decimal
    - Strings: "123", "123.45", "123,45" (European format)
    - Mixed strings: "about 500g" -> 500

    Args:
        val: Value to parse (any type)

    Returns:
        Decimal value or None if parsing fails

    Examples:
        >>> parse_numeric(500)
        Decimal('500')
        >>> parse_numeric("123,45")
        Decimal('123.45')
        >>> parse_numeric("about 500g")
        Decimal('500')
    """
    if val is None or val == '':
        return None
    if isinstance(val, Decimal):
        return val
    if isinstance(val, (int, float)):
        return Decimal(str(val))

    # Try to extract number from string
    match = re.search(r'([\d,\.]+)', str(val))
    if match:
        try:
            # Handle European comma decimal separator
            num_str = match.group(1).replace(',', '.')
            # Handle cases like "1.500" (thousand separator) vs "1.5" (decimal)
            # If there are multiple dots, remove all but last
            parts = num_str.split('.')
            if len(parts) > 2:
                num_str = ''.join(parts[:-1]) + '.' + parts[-1]
            return Decimal(num_str)
        except Exception:
            return None
    return None


# =============================================================================
# SCRAPING & FRESHNESS LIFECYCLE TASKS (Phase 3)
# =============================================================================

@shared_task(bind=True, max_retries=3)
def scrape_store_task(self, shop_code: str) -> Dict[str, Any]:
    """
    Proactive scraping task triggered by Celery Beat schedule.

    Scrapes a single store, stores results in LeafletOffer,
    and creates a ScrapeRun audit record.
    """
    import time
    from datetime import timedelta
    from .models import LeafletOffer, GroceryStore, ScrapeRun
    from .scrapers.price_recording import upsert_price_record

    started = time.time()
    log_prefix = f"[SCRAPE:{shop_code}]"

    try:
        store = GroceryStore.objects.filter(code=shop_code, is_active=True).first()
        if not store:
            logger.warning(f"{log_prefix} Store not found or inactive, skipping")
            return {'status': 'skipped', 'reason': 'store_not_found'}

        scrape_run = ScrapeRun.objects.create(
            store=store,
            status=ScrapeRun.Status.RUNNING,
            method=ScrapeRun.Method.HYBRID,
        )

        logger.info(f"{log_prefix} Starting scrape (run {scrape_run.pk})")

        scraper = ScraperService.get_scraper(shop_code)
        products = scraper.scrape()

        if not products:
            logger.warning(f"{log_prefix} Structured scraping returned 0 products")

        # Store in LeafletOffer (same pattern as existing scrape_and_store)
        from .scrapers.utils import normalize_ingredient_name
        now = timezone.now()
        ttl_hours = store.default_price_ttl_hours or 168
        expires_at = now + timedelta(hours=ttl_hours)
        country = store.country
        currency = store.currency

        created = 0
        updated = 0
        for product in products:
            ingredient_name = normalize_ingredient_name(
                product.get('ingredient_name', product.get('display_name', ''))
            )
            if not ingredient_name:
                continue

            price = product.get('price')
            if not price or float(price) <= 0:
                continue

            # Honor the leaflet's real validity window when the scraper parsed
            # one; otherwise fall back to the store's generic TTL. A future
            # valid_from marks an upcoming (not-yet-active) deal.
            prod_valid_from = product.get('valid_from') or now
            prod_valid_until = product.get('valid_until') or expires_at

            _, was_created = LeafletOffer.objects.update_or_create(
                shop=shop_code,
                country=country,
                ingredient_name=ingredient_name,
                defaults={
                    'display_name': product.get('display_name', ingredient_name),
                    'price': price,
                    'currency': product.get('currency', currency),
                    'unit': product.get('unit', ''),
                    'price_type': product.get('price_type', 'REGULAR'),
                    'original_price': product.get('original_price'),
                    'discount_percentage': product.get('discount_percentage'),
                    'source_url': product.get('source_url', ''),
                    'expires_at': prod_valid_until,
                    'freshness_state': 'fresh',
                    'stale_at': None,
                },
            )
            if was_created:
                created += 1
            else:
                updated += 1

            # Phase A dual-write: mirror into PriceRecord + StoreProduct.
            try:
                upsert_price_record(
                    shop_code=shop_code,
                    offer_data={
                        'ingredient_name': ingredient_name,
                        'display_name': product.get('display_name', ingredient_name),
                        'price': price,
                        'currency': product.get('currency', currency),
                        'unit': product.get('unit', ''),
                        'package_size': product.get('package_size'),
                        'price_type': product.get('price_type', 'REGULAR'),
                        'original_price': product.get('original_price'),
                        'discount_percentage': product.get('discount_percentage'),
                        'source_url': product.get('source_url', ''),
                    },
                    valid_from=prod_valid_from,
                    valid_until=prod_valid_until,
                    scrape_run=scrape_run,
                )
            except Exception as dual_exc:
                logger.warning(
                    f"{log_prefix} PriceRecord dual-write failed for {ingredient_name}: {dual_exc}"
                )

        duration = time.time() - started
        scrape_run.status = ScrapeRun.Status.COMPLETED
        scrape_run.completed_at = timezone.now()
        scrape_run.duration_seconds = duration
        scrape_run.products_found = len(products)
        scrape_run.products_created = created
        scrape_run.products_updated = updated
        scrape_run.prices_recorded = created + updated
        scrape_run.save()

        logger.info(
            f"{log_prefix} Complete: {len(products)} found, {created} created, "
            f"{updated} updated in {duration:.1f}s"
        )
        return {
            'status': 'success',
            'products_found': len(products),
            'created': created,
            'updated': updated,
            'duration_seconds': round(duration, 1),
        }

    except Exception as exc:
        duration = time.time() - started
        logger.error(f"{log_prefix} Failed: {exc}", exc_info=True)

        try:
            if 'scrape_run' in locals():
                scrape_run.status = ScrapeRun.Status.FAILED
                scrape_run.completed_at = timezone.now()
                scrape_run.duration_seconds = duration
                scrape_run.error_log = str(exc)[:2000]
                scrape_run.errors_count = 1
                scrape_run.save()
        except Exception:
            pass

        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))


@shared_task
def update_freshness_states_task() -> Dict[str, Any]:
    """
    Transition LeafletOffer freshness states based on FRESHNESS_CONFIG TTLs.

    FRESH → STALE (past fresh_hours)
    STALE → EXPIRED (past stale_hours, set via expires_at)
    """
    from datetime import timedelta
    from django.conf import settings as django_settings
    from .models import LeafletOffer

    freshness_config = getattr(django_settings, 'FRESHNESS_CONFIG', {})
    now = timezone.now()
    total_staled = 0
    total_expired = 0

    for shop_code, config in freshness_config.items():
        fresh_hours = config.get('fresh_hours', 72)
        stale_cutoff = now - timedelta(hours=fresh_hours)

        # FRESH → STALE
        staled = LeafletOffer.objects.filter(
            shop=shop_code,
            freshness_state='fresh',
            scraped_at__lt=stale_cutoff,
        ).update(freshness_state='stale', stale_at=now)
        total_staled += staled

        # STALE → EXPIRED (using expires_at which is already set)
        expired = LeafletOffer.objects.filter(
            shop=shop_code,
            freshness_state='stale',
            expires_at__lt=now,
        ).update(freshness_state='expired')
        total_expired += expired

    if total_staled or total_expired:
        logger.info(f"Freshness update: {total_staled} → stale, {total_expired} → expired")

    return {'staled': total_staled, 'expired': total_expired}


@shared_task
def archive_expired_offers_task() -> Dict[str, Any]:
    """
    Delete expired LeafletOffer rows older than 30 days.
    Price history is preserved via PriceRecord (when populated).
    """
    from datetime import timedelta
    from .models import LeafletOffer

    cutoff = timezone.now() - timedelta(days=30)
    count, _ = LeafletOffer.objects.filter(
        freshness_state='expired',
        scraped_at__lt=cutoff,
    ).delete()

    if count:
        logger.info(f"Archived {count} expired offers older than 30 days")

    return {'archived': count}


@shared_task
def scraper_health_check_task() -> Dict[str, Any]:
    """
    Daily health check across all stores.
    Logs warnings and sends Slack alert if any store is stale or broken.
    """
    from datetime import timedelta
    from .models import GroceryStore, LeafletOffer, ScrapeRun

    now = timezone.now()
    week_ago = now - timedelta(days=7)
    alerts = []

    stores = GroceryStore.objects.filter(is_active=True)
    for store in stores:
        # Check 1: successful scrape in last 48h
        latest = ScrapeRun.objects.filter(
            store=store, status='COMPLETED',
        ).order_by('-started_at').first()

        if not latest:
            alerts.append(f"CRITICAL: {store.code} has NEVER been scraped")
        elif (now - latest.started_at).total_seconds() > 48 * 3600:
            hours_ago = (now - latest.started_at).total_seconds() / 3600
            alerts.append(f"STALE: {store.code} last scraped {hours_ago:.0f}h ago")

        # Check 2: product count drop
        last_two = list(ScrapeRun.objects.filter(
            store=store, status__in=['COMPLETED', 'PARTIAL'],
        ).order_by('-started_at')[:2])

        if len(last_two) == 2 and last_two[1].products_found > 0:
            ratio = last_two[0].products_found / last_two[1].products_found
            if ratio < 0.3:
                alerts.append(
                    f"DROP: {store.code} products dropped from "
                    f"{last_two[1].products_found} to {last_two[0].products_found}"
                )

        # Check 3: weekly LLM cost spike
        from django.db.models import Sum as _Sum
        weekly_cost = ScrapeRun.objects.filter(
            store=store, started_at__gte=week_ago,
        ).aggregate(total=_Sum('llm_cost_usd'))['total'] or 0
        if float(weekly_cost) > 1.0:
            alerts.append(f"COST: {store.code} weekly LLM cost ${weekly_cost:.2f}")

    if alerts:
        alert_text = "Scraper Health Check:\n" + "\n".join(f"  - {a}" for a in alerts)
        logger.warning(alert_text)
        _send_slack_alert(alert_text)
    else:
        logger.info("Scraper health check: all stores healthy")

    return {'alerts': alerts, 'stores_checked': stores.count()}


def _send_slack_alert(message: str) -> None:
    """Best-effort Slack alert. Fails silently if Slack is not configured."""
    import os
    try:
        token = os.environ.get('SLACK_BOT_TOKEN')
        channel = os.environ.get('SLACK_ALERT_CHANNEL')
        if not token or not channel:
            return

        from slack_sdk import WebClient
        client = WebClient(token=token)
        client.chat_postMessage(channel=channel, text=message)
        logger.info("Slack alert sent")
    except Exception as e:
        logger.warning(f"Failed to send Slack alert: {e}")


def _find_matching_product(
    ingredient_name: str,
    available_ingredients: List[Dict[str, Any]]
) -> Optional[Dict[str, Any]]:
    """
    Find the best matching product for an ingredient from available shop products.

    Uses simple fuzzy matching based on ingredient name containment.

    Args:
        ingredient_name: Name of the ingredient to match
        available_ingredients: List of available products from shop scraper

    Returns:
        Matching product dict or None if no match found
    """
    if not ingredient_name or not available_ingredients:
        return None

    name_lower = ingredient_name.lower().strip()

    # First pass: exact match on ingredient_name
    for product in available_ingredients:
        product_name = (product.get('ingredient_name') or product.get('display_name') or '').lower()
        if product_name == name_lower:
            return product

    # Second pass: substring match (ingredient in product or product in ingredient)
    for product in available_ingredients:
        product_name = (product.get('ingredient_name') or product.get('display_name') or '').lower()
        if name_lower in product_name or product_name in name_lower:
            return product

    # Third pass: word-based matching (any word matches)
    ingredient_words = set(name_lower.split())
    best_match = None
    best_score = 0

    for product in available_ingredients:
        product_name = (product.get('ingredient_name') or product.get('display_name') or '').lower()
        product_words = set(product_name.split())

        # Count matching words
        matches = len(ingredient_words & product_words)
        if matches > best_score and matches >= 1:
            best_score = matches
            best_match = product

    return best_match
