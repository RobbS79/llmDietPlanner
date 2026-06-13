"""
Google Gemini LLM Service for Dietary Plan Generation
======================================================

This module handles all Google Gemini API interactions for the diet planner application.
Gemini can browse URLs directly, enabling real-time price fetching from shop websites.

## Responsibilities:
- Generate meal plans (days with meals and ingredients)
- Extract products from scraped HTML (for price discovery)
- Estimate prices for products not found in shop data

## Important Design Decision:
The LLM generates ONLY the meal plan structure with ingredients per meal.
The backend (tasks.py) handles:
- Aggregating ingredients into shopping list
- Matching ingredients with shop products
- Calculating prices

This separation prevents confusion and ensures consistent pricing logic.

## Cost Tracking:
All API calls track token usage and calculate costs in USD.
Costs are stored in DietaryPlan.llm_cost_usd for billing/monitoring.

## Debugging Tips:
- Check logs for "LLM extraction" entries with token counts
- Look for "estimated price" logs for price estimation calls
- Token counts help identify prompt optimization opportunities
"""
from typing import Dict, Any, Optional, List, TYPE_CHECKING
import json
import logging
import re
from decimal import Decimal, InvalidOperation

from django.conf import settings
import google.generativeai as genai

from .food_categories import CATEGORY_SLUGS

if TYPE_CHECKING:
    from diet_planner.services.restrictions import ResolvedRestrictions

logger = logging.getLogger(__name__)


# Gemini pricing per 1M tokens (as of 2024)
# Prices in USD
GEMINI_PRICING = {
    'gemini-2.5-flash': {
        'input': 0.15,
        'output': 0.60,
    },
    'gemini-2.0-flash': {
        'input': 0.10,
        'output': 0.40,
    },
    'gemini-1.5-pro': {
        'input': 1.25,
        'output': 5.00,
    },
    'gemini-1.5-flash': {
        'input': 0.075,
        'output': 0.30,
    },
}


def get_model_pricing(model: str) -> Dict[str, float]:
    """
    Get pricing for a specific Gemini model.
    
    Args:
        model: Model name (e.g., 'gemini-2.0-flash-exp', 'gemini-1.5-pro')
        
    Returns:
        Dict with 'input' and 'output' prices per 1M tokens
    """
    return GEMINI_PRICING.get(
        model,
        GEMINI_PRICING.get('gemini-1.5-flash')  # Default to cheapest paid option
    )


def calculate_cost(
    input_tokens: int,
    output_tokens: int,
    model: str
) -> Decimal:
    """
    Calculate the cost of an API call in USD.
    
    Args:
        input_tokens: Number of input tokens
        output_tokens: Number of output tokens
        model: Model name used
        
    Returns:
        Cost in USD as Decimal
    """
    pricing = get_model_pricing(model)
    
    input_cost = (input_tokens / 1_000_000) * pricing['input']
    output_cost = (output_tokens / 1_000_000) * pricing['output']
    
    total_cost = Decimal(str(input_cost + output_cost))
    return total_cost.quantize(Decimal('0.000001'))  # Round to 6 decimal places


class GeminiService:
    """
    Service for interacting with Google Gemini API.
    Handles API calls, token counting, and cost tracking.
    """
    
    def __init__(self):
        """Initialise Gemini client with API key from settings."""
        api_key = getattr(settings, 'GEMINI_API_KEY', None)
        if not api_key:
            raise ValueError(
                "GEMINI_API_KEY not set in settings. "
                "Please set it as an environment variable."
            )
        
        genai.configure(api_key=api_key)
        self.default_model = getattr(
            settings,
            'GEMINI_MODEL',
            'gemini-2.5-flash'
        )
    
    def generate_dietary_plan(
        self,
        prompt_text: str,
        system_prompt: Optional[str] = None,
        model: Optional[str] = None,
        language_code: Optional[str] = None,
        shop_url: Optional[str] = None  # NEW: Pass shop URL for Gemini to browse
    ) -> Dict[str, Any]:
        """
        Generate a dietary plan using Gemini API.
        
        Args:
            prompt_text: User prompt (JSON formatted or natural language)
            system_prompt: System prompt (optional, uses default if not provided)
            model: Model to use (optional, uses default if not provided)
            language_code: Language code for response (e.g., 'cs', 'pl', 'en')
            shop_url: Optional shop URL for Gemini to browse for prices
            
        Returns:
            Dict containing:
                - 'response': LLM response content (parsed JSON)
                - 'input_tokens': Number of input tokens
                - 'output_tokens': Number of output tokens
                - 'total_tokens': Total tokens used
                - 'cost_usd': Cost in USD
                - 'model': Model used
        """
        model = model or self.default_model
        
        # Default system prompt (with language support)
        if system_prompt is None:
            # Language mapping for better prompts
            language_names = {
                'cs': 'Czech',
                'sk': 'Slovak',
                'pl': 'Polish',
                'hu': 'Hungarian',
                'ro': 'Romanian',
                'bg': 'Bulgarian',
                'de': 'German',
                'en': 'English',
            }
            target_language = language_names.get(language_code or 'en', 'English')

            # Clear, unambiguous system prompt - NO shopping list, NO prices
            system_prompt = f"""You are a nutrition expert creating personalised day-by-day meal plans.

RESPONSE FORMAT:
- Valid JSON only, no markdown, no code blocks
- All text content in {target_language} language

OUTPUT STRUCTURE:
Generate a 'days' array where each day object contains:
- day_number: integer (1, 2, 3, ...)
- breakfast: single meal object (if requested)
- lunch: single meal object (if requested)
- dinner: single meal object (if requested)
- small_meals: array of meal objects
- snacks: array of meal objects

MEAL OBJECT STRUCTURE:
Each meal must include:
- name: meal name in {target_language}
- description: brief description in {target_language}
- preparation_time: integer minutes
- ingredients: array of ingredient objects
- nutritional_info: object with calories (number), protein (string like "20g"), carbs (string), fat (string)

INGREDIENT OBJECT STRUCTURE:
Each ingredient must be an object with:
- name: ingredient name in {target_language}
- quantity: numeric value (e.g., 200, 2, 0.5)
- unit: metric unit only (g, kg, ml, l, ks)

CRITICAL RULES:
1. Use REALISTIC per-meal quantities (e.g., 200g chicken, 2 eggs, 30ml oil - NOT 2000g or 20 eggs)
2. DO NOT generate a shopping_list - the backend creates it from ingredients
3. DO NOT include prices - the backend handles pricing
4. Focus on ingredients available in Central European supermarkets (Lidl, Kaufland, etc.)
5. Consider local cuisine preferences

EXAMPLE INGREDIENT FORMAT:
"ingredients": [
  {{"name": "kuřecí prsa", "quantity": 200, "unit": "g"}},
  {{"name": "olivový olej", "quantity": 30, "unit": "ml"}},
  {{"name": "vejce", "quantity": 2, "unit": "ks"}}
]"""
        
        try:
            # Initialize model with system instruction
            gemini_model = genai.GenerativeModel(
                model_name=model,
                system_instruction=system_prompt
            )
            
            # Build full prompt
            full_prompt = prompt_text
            
            # If shop_url provided, instruct Gemini to browse it
            if shop_url:
                full_prompt += f"\n\nIMPORTANT: Browse {shop_url} to get current product prices and availability. Use this information when creating the meal plan."
            
            # Generate content with extended timeout for complex prompts and URL browsing
            response = gemini_model.generate_content(
                full_prompt,
                generation_config={
                    "response_mime_type": "application/json",
                    "temperature": 0.7,
                },
                request_options={"timeout": 300}  # 5 minutes timeout for long responses
            )
            
            # Extract response
            content = response.text
            
            # Get token usage from API response
            usage = response.usage_metadata
            input_tokens = usage.prompt_token_count
            output_tokens = usage.candidates_token_count
            total_tokens = usage.total_token_count
            
            # Calculate cost
            cost_usd = calculate_cost(input_tokens, output_tokens, model)
            
            # Log full response for debugging (Option 2)
            response_length = len(content)
            logger.debug(f"Gemini response length: {response_length} characters")
            
            # If response is very long, save to file for detailed inspection
            if response_length > 10000:
                try:
                    with open('/tmp/gemini_response.json', 'w', encoding='utf-8') as f:
                        f.write(content)
                    logger.warning(f"Response too long ({response_length} chars), saved to /tmp/gemini_response.json for inspection")
                    logger.error(f"Response content (first 1000 chars): {content[:1000]}")
                    logger.error(f"Response content (last 1000 chars): {content[-1000:]}")
                except Exception as save_error:
                    logger.warning(f"Failed to save response to file: {save_error}")
                    logger.error(f"Response content (first 2000 chars): {content[:2000]}")
            else:
                logger.debug(f"Full Gemini response: {content}")
            
            # Parse JSON response with error handling and cleaning (Option 1)
            try:
                parsed_response = json.loads(content)
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse Gemini JSON response: {e}")
                logger.error(f"Error at position {e.pos if hasattr(e, 'pos') else 'unknown'}")
                logger.error(f"Response content (first 1000 chars): {content[:1000]}")
                logger.error(f"Response content (last 1000 chars): {content[-1000:] if len(content) > 1000 else content}")
                
                # Try to fix common JSON issues (Option 1)
                try:
                    logger.info("Attempting to clean and repair JSON...")
                    cleaned_content = content
                    
                    # Remove trailing commas before } or ] (most common JSON error)
                    cleaned_content = re.sub(r',\s*}', '}', cleaned_content)
                    cleaned_content = re.sub(r',\s*]', ']', cleaned_content)
                    
                    # Try parsing cleaned version
                    parsed_response = json.loads(cleaned_content)
                    logger.warning("Successfully parsed JSON after cleaning trailing commas")
                except json.JSONDecodeError as e2:
                    logger.error(f"Failed to parse even after cleaning: {e2}")
                    logger.error(f"Cleaned content length: {len(cleaned_content)}")
                    if len(cleaned_content) > 2000:
                        logger.error(f"Cleaned content (first 1000 chars): {cleaned_content[:1000]}")
                        logger.error(f"Cleaned content (last 1000 chars): {cleaned_content[-1000:]}")
                    else:
                        logger.error(f"Cleaned content: {cleaned_content}")
                    
                    # Save problematic response for detailed analysis
                    try:
                        with open('/tmp/gemini_invalid_response.json', 'w', encoding='utf-8') as f:
                            f.write(content)
                        logger.error(f"Saved invalid response to /tmp/gemini_invalid_response.json for analysis")
                    except Exception:
                        pass
                    
                    raise ValueError(f"Gemini returned invalid JSON that could not be repaired: {e}")
            
            return {
                'response': parsed_response,
                'input_tokens': input_tokens,
                'output_tokens': output_tokens,
                'total_tokens': total_tokens,
                'cost_usd': cost_usd,
                'model': model,
            }
            
        except Exception as e:
            logger.error(f"Gemini API error: {e}", exc_info=True)
            raise
    
    def _build_meal_system_prompt(
        self,
        *,
        goal: Any,
        exclusions: "Optional[ResolvedRestrictions]",
        shop_url: Optional[str] = None,
        catalog_text: Optional[str] = None,
        single_meal: bool = False,
    ) -> str:
        """Build the system prompt for meal generation.

        Shared by generate_meal_plan_only (URL browsing), generate_catalog_
        constrained_plan (catalog text), and regenerate_meal (single-meal
        repair). The restriction block is injected when exclusions is non-
        empty; this is the ONE place the rule lives.
        """
        language_names = {
            "cs": "Czech", "sk": "Slovak", "pl": "Polish",
            "hu": "Hungarian", "ro": "Romanian", "bg": "Bulgarian",
            "de": "German", "en": "English",
        }
        target_language = language_names.get(
            getattr(goal, "language_code", "en") or "en", "English"
        )
        num_days = getattr(goal, "num_days", 7)

        restriction_block = self._format_restriction_block(exclusions)

        if single_meal:
            schema_hint = (
                "OUTPUT: a SINGLE meal JSON object with keys "
                "name, description, food_category, preparation_time, "
                "ingredients[], instructions[], nutritional_info."
            )
            scope_line = "TASK: produce ONE replacement meal honoring all rules."
        else:
            schema_hint = (
                'OUTPUT: {"days": [{"day_number": 1, "breakfast": {...}, '
                '"lunch": {...}, "dinner": {...}, "small_meals": [...], '
                '"snacks": [...]}, ...]}'
            )
            scope_line = f"TASK: generate a {num_days}-day meal plan."

        source_line = (
            f"Browse {shop_url} for context but don't list prices."
            if shop_url
            else f"Use ONLY the AVAILABLE PRODUCTS list below.\n\n{catalog_text or ''}"
        )

        return (
            f"You are a nutrition expert creating meal plans.\n\n"
            f"RESPONSE FORMAT: Valid JSON only, no markdown, all text in {target_language}.\n\n"
            f"{scope_line}\n"
            f"{schema_hint}\n\n"
            f"{source_line}\n\n"
            f"{restriction_block}"
            f"CRITICAL RULES:\n"
            f"- Keep instructions VERY BRIEF: 3 steps maximum per meal\n"
            f"- Keep descriptions to 1 sentence\n"
            f"\n"
            f"INGREDIENT CONSISTENCY (production-critical, do not violate):\n"
            f"- ingredients[] MUST list ONLY raw items the user has to buy fresh\n"
            f"  at the store for THIS meal.\n"
            f"- A meal that reuses a leftover from another day MUST exclude that\n"
            f"  leftover from ingredients[]."
        )

    @staticmethod
    def _format_restriction_block(
        exclusions: "Optional[ResolvedRestrictions]",
    ) -> str:
        if exclusions is None or not exclusions.exclusion_keywords:
            return ""
        tags_str = ", ".join(sorted(exclusions.tags)) or "(none)"
        allergens_line = ""
        if exclusions.freeform_allergens:
            allergens_line = (
                "- The user has reported ALLERGIES to: "
                f"{', '.join(sorted(exclusions.freeform_allergens))}.\n"
            )
        kw_str = ", ".join(sorted(exclusions.exclusion_keywords))
        return (
            "DIETARY RESTRICTIONS (non-negotiable, hard rule):\n"
            f"- The user requires: {tags_str}.\n"
            f"{allergens_line}"
            f"- The following ingredient keywords are FORBIDDEN in ingredients[]\n"
            f"  AND instructions[] for ALL meals: {kw_str}.\n"
            "- If a traditional recipe would require a forbidden ingredient,\n"
            "  substitute a compliant alternative (e.g. bezlepková mouka instead\n"
            "  of mouka). Generated meals containing any forbidden keyword will\n"
            "  be REJECTED.\n\n"
        )

    def generate_meal_plan_only(
        self,
        user_prompt: str,
        shop_url: str,
        goal: Any,
        model: Optional[str] = None,
        exclusions: "Optional[ResolvedRestrictions]" = None,
    ) -> Dict[str, Any]:
        """
        Generate meal plan ONLY (no shopping list) to avoid token limits.
        This is the first call in a two-step process.
        """
        model = model or self.default_model

        system_prompt = self._build_meal_system_prompt(
            goal=goal,
            exclusions=exclusions,
            shop_url=shop_url,
            single_meal=False,
        )

        full_prompt = f"""{user_prompt}

Create meal plan with recipes from {shop_url}.
Keep all text concise - 3 steps max per recipe, 1 sentence descriptions."""

        try:
            gemini_model = genai.GenerativeModel(model_name=model, system_instruction=system_prompt)
            max_tokens = getattr(settings, 'GEMINI_MAX_OUTPUT_TOKENS', 65536)

            response = gemini_model.generate_content(
                full_prompt,
                generation_config={
                    "response_mime_type": "application/json",
                    "temperature": 0.7,
                    "max_output_tokens": max_tokens,
                },
                request_options={"timeout": 300}
            )

            if response.candidates and hasattr(response.candidates[0], 'finish_reason'):
                finish_reason = response.candidates[0].finish_reason
                if finish_reason.name == 'MAX_TOKENS':
                    logger.error(f"Meal plan response truncated at {max_tokens} tokens")
                    raise ValueError(f"Response truncated: output exceeded {max_tokens} tokens")

            content = response.text
            usage = response.usage_metadata

            try:
                parsed_response = json.loads(content)
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse meal plan JSON: {e}")
                try:
                    cleaned = re.sub(r',\s*}', '}', content)
                    cleaned = re.sub(r',\s*]', ']', cleaned)
                    parsed_response = json.loads(cleaned)
                except json.JSONDecodeError:
                    raise ValueError(f"Invalid JSON from meal plan generation: {e}")

            return {
                'response': parsed_response,
                'input_tokens': usage.prompt_token_count,
                'output_tokens': usage.candidates_token_count,
                'total_tokens': usage.total_token_count,
                'cost_usd': calculate_cost(usage.prompt_token_count, usage.candidates_token_count, model),
                'model': model,
            }

        except Exception as e:
            logger.error(f"Meal plan generation error: {e}", exc_info=True)
            raise
    
    def generate_shopping_list_with_prices(
        self,
        meal_plan_days: List[Dict],
        shop_url: str,
        goal: Any,
        model: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Generate shopping list with prices based on meal plan.
        This is the second call - separate to avoid token limits.
        """
        model = model or self.default_model
        
        language_names = {
            'cs': 'Czech', 'sk': 'Slovak', 'pl': 'Polish',
            'hu': 'Hungarian', 'ro': 'Romanian', 'bg': 'Bulgarian',
            'de': 'German', 'en': 'English',
        }
        target_language = language_names.get(getattr(goal, 'language_code', 'en') or 'en', 'English')
        currency_map = {'CZ': 'CZK', 'SK': 'EUR', 'PL': 'PLN', 'HU': 'HUF'}
        currency = currency_map.get(getattr(goal, 'country', 'CZ'), 'CZK')
        
        # Extract ingredients summary for prompt
        import json as json_module
        days_summary = json_module.dumps(meal_plan_days, ensure_ascii=False)[:5000]  # Limit prompt size
        
        system_prompt = f"""You are a shopping assistant. Create shopping list with prices from {shop_url}.

RESPONSE FORMAT: Valid JSON only, all text in {target_language}

OUTPUT:
{{
  "shopping_list": [
    {{
      "ingredient": "name",
      "quantity": 500,
      "unit": "g",
      "matched_product_name": "actual product from {shop_url}",
      "price": 89.90,
      "price_total": 89.90,
      "currency": "{currency}",
      "package_size": 500,
      "product_unit": "g",
      "price_type": "REGULAR",
      "estimated": false
    }}
  ],
  "total_cost": 2345.67
}}

RULES:
1. Browse {shop_url} for ACTUAL prices
2. Convert weights to pieces when needed (200g avocado → 2 pieces)
3. Round UP to purchasable packages (300ml oil → 500ml bottle)
4. Mark estimated: true only if product not found"""

        prompt = f"""Based on this meal plan, create shopping list with prices from {shop_url}.

Meal plan (summary):
{days_summary}

Browse {shop_url} and return complete shopping list with real prices."""

        try:
            gemini_model = genai.GenerativeModel(model_name=model, system_instruction=system_prompt)
            max_tokens = getattr(settings, 'GEMINI_MAX_OUTPUT_TOKENS', 65536)

            response = gemini_model.generate_content(
                prompt,
                generation_config={
                    "response_mime_type": "application/json",
                    "temperature": 0.3,
                    "max_output_tokens": max_tokens,
                },
                request_options={"timeout": 300}
            )

            if response.candidates and hasattr(response.candidates[0], 'finish_reason'):
                finish_reason = response.candidates[0].finish_reason
                if finish_reason.name == 'MAX_TOKENS':
                    logger.error(f"Shopping list response truncated at {max_tokens} tokens")
                    raise ValueError(f"Response truncated: output exceeded {max_tokens} tokens")

            content = response.text
            usage = response.usage_metadata

            try:
                parsed_response = json.loads(content)
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse shopping list JSON: {e}")
                try:
                    cleaned = re.sub(r',\s*}', '}', content)
                    cleaned = re.sub(r',\s*]', ']', cleaned)
                    parsed_response = json.loads(cleaned)
                except json.JSONDecodeError:
                    raise ValueError(f"Invalid JSON from shopping list generation: {e}")

            return {
                'response': parsed_response,
                'input_tokens': usage.prompt_token_count,
                'output_tokens': usage.candidates_token_count,
                'total_tokens': usage.total_token_count,
                'cost_usd': calculate_cost(usage.prompt_token_count, usage.candidates_token_count, model),
                'model': model,
            }

        except Exception as e:
            logger.error(f"Shopping list generation error: {e}", exc_info=True)
            raise
    
    def generate_complete_plan_with_shopping_list(
        self,
        user_prompt: str,  # Full clinical document from user
        shop_url: str,
        goal: Any,  # DietaryGoal - using Any to avoid circular import
        model: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Generate complete plan with shopping list using TWO calls to avoid token limits:
        1. Generate meal plan first (recipes, ingredients)
        2. Generate shopping list with prices based on meal plan
        
        This avoids hitting the 8192 token limit that was causing truncation.
        
        Args:
            user_prompt: Full user prompt/document with dietary requirements
            shop_url: Shop URL for Gemini to browse
            goal: DietaryGoal object with all configuration
            model: Optional model override
            
        Returns:
            Dict with 'response' containing complete plan with shopping list
        """
        logger.info("Generating meal plan (step 1/2)...")
        meal_plan_result = self.generate_meal_plan_only(user_prompt, shop_url, goal, model)
        days = meal_plan_result['response'].get('days', [])
        
        logger.info(f"Meal plan generated: {len(days)} days. Generating shopping list (step 2/2)...")
        shopping_list_result = self.generate_shopping_list_with_prices(days, shop_url, goal, model)
        shopping_data = shopping_list_result['response']
        
        # Combine results
        combined_response = {
            'days': days,
            'shopping_list': shopping_data.get('shopping_list', []),
            'total_cost': shopping_data.get('total_cost', 0)
        }
        
        # Sum up tokens and costs
        total_input_tokens = meal_plan_result['input_tokens'] + shopping_list_result['input_tokens']
        total_output_tokens = meal_plan_result['output_tokens'] + shopping_list_result['output_tokens']
        total_cost = meal_plan_result['cost_usd'] + shopping_list_result['cost_usd']
        
        logger.info(f"Complete plan generated: {len(days)} days, {len(combined_response['shopping_list'])} shopping items")
        
        return {
            'response': combined_response,
            'input_tokens': total_input_tokens,
            'output_tokens': total_output_tokens,
            'total_tokens': total_input_tokens + total_output_tokens,
            'cost_usd': total_cost,
            'model': model or self.default_model,
        }
    
    def generate_recipe_instructions(
        self,
        meal_name: str,
        ingredients: list,
        description: str = "",
        language_code: str = "en",
        model: Optional[str] = None
    ) -> list:
        """
        Generate detailed cooking instructions for a recipe using Gemini.
        
        Args:
            meal_name: Name of the meal
            ingredients: List of ingredients
            description: Optional meal description
            language_code: Language code for instructions (e.g., 'cs', 'pl', 'en')
            model: Model to use (optional, uses default if not provided)
            
        Returns:
            List of step-by-step cooking instructions
        """
        model = model or self.default_model
        
        # Build prompt for generating instructions
        ingredients_text = ", ".join(ingredients) if ingredients else "standard ingredients"
        description_text = f"\nDescription: {description}" if description else ""
        
        prompt = f"""Generate substantive, informative cooking instructions for the following meal:

Meal Name: {meal_name}
Ingredients: {ingredients_text}{description_text}

Requirements:
- Provide 4–8 clear cooking steps with real substance — never one-liners
- Even for trivially-prepared foods (snacks, raw items, single-ingredient meals), produce a useful guide:
    * Step 1 should explain WHY this food is included — its nutritional or health value (e.g., magnesium, polyphenols, slow-release carbs, protein, fibre — choose what fits)
    * Subsequent steps cover quality cues when buying or selecting (look for ≥85% cocoa, fresh / firm produce, etc.), portion sizing, and timing or pairing suggestions
- For cooked dishes: include specific temperatures, times, techniques, and serving notes
- Each step must be a complete sentence with concrete information, not a vague action
- Aim for at least 60–80 words across all steps combined
- Write in {language_code} language, in a confident, practical tone

Avoid output like "Eat a small piece of chocolate." A reader should learn something or be guided to do it better, not just told what they already know.

Return ONLY a JSON object with an "instructions" array of strings:
{{"instructions": ["Step 1 instruction", "Step 2 instruction", "Step 3 instruction", ...]}}"""

        system_prompt = (
            "You are a professional chef and nutritionist providing substantive, informative cooking "
            "and serving guidance. Never produce trivial one-liners — every recipe, even for simple "
            "snacks, must give the reader real context (nutrition, quality cues, portion, timing). "
            "Always respond with valid JSON."
        )
        
        try:
            gemini_model = genai.GenerativeModel(
                model_name=model,
                system_instruction=system_prompt
            )
            
            response = gemini_model.generate_content(
                prompt,
                generation_config={
                    "response_mime_type": "application/json",
                    "temperature": 0.7,
                },
                request_options={"timeout": 300}  # 5 minutes timeout
            )
            
            content = response.text
            parsed = json.loads(content)
            
            # Extract instructions array (could be under 'instructions' key or be the root)
            if isinstance(parsed, list):
                return parsed
            elif 'instructions' in parsed:
                return parsed['instructions']
            else:
                # Try to find any array in the response
                for value in parsed.values():
                    if isinstance(value, list):
                        return value
                return []
                
        except Exception as e:
            logger.error(f"Error generating recipe instructions: {e}", exc_info=True)
            # Return empty list on error - fallback will be used
            return []

    def expand_thin_recipe_instructions(
        self,
        meal_name: str,
        ingredients: list,
        thin_instructions: list,
        description: str = "",
        language_code: str = "en",
        model: Optional[str] = None,
    ) -> list:
        """
        Re-generate instructions when the first attempt was too brief.

        Feeds the thin output back to the model with an explicit ask to
        expand it — nutritional context, quality cues, portion guidance,
        serving notes. Used as a one-shot retry by the recipe view when
        the substantive-content gate would otherwise keep the recipe
        private.
        """
        model = model or self.default_model
        ingredients_text = ", ".join(ingredients) if ingredients else "standard ingredients"
        description_text = f"\nDescription: {description}" if description else ""
        thin_text = "\n".join(f"- {step}" for step in thin_instructions) if thin_instructions else "- (none)"

        prompt = f"""The previous attempt at generating instructions for this recipe was too brief and unhelpful. Rewrite it as a substantive guide.

Meal Name: {meal_name}
Ingredients: {ingredients_text}{description_text}

Previous (too-thin) instructions:
{thin_text}

Required improvements:
- 4–8 steps total, at least 60 words combined
- Open with WHY this food is included — its nutritional or health value (specific nutrients, what they do)
- Include quality cues for selecting the ingredients (% cocoa, freshness, marbling, etc. — whatever fits)
- Give a sensible portion size and when to eat it (pre-workout, post-meal, etc.)
- For cooked dishes, include temperatures, times, and serving suggestions
- Write in {language_code}, in a confident practical tone
- Never produce one-liners — every step must teach the reader something concrete

Return ONLY a JSON object: {{"instructions": ["Step 1 ...", "Step 2 ...", ...]}}"""

        system_prompt = (
            "You are rewriting a too-brief recipe into a substantive cooking and nutrition guide. "
            "Always respond with valid JSON."
        )

        try:
            gemini_model = genai.GenerativeModel(
                model_name=model,
                system_instruction=system_prompt,
            )
            response = gemini_model.generate_content(
                prompt,
                generation_config={
                    "response_mime_type": "application/json",
                    "temperature": 0.7,
                },
                request_options={"timeout": 300},
            )
            parsed = json.loads(response.text)
            if isinstance(parsed, list):
                return parsed
            if 'instructions' in parsed:
                return parsed['instructions']
            for value in parsed.values():
                if isinstance(value, list):
                    return value
            return []
        except Exception as e:
            logger.error(f"Error expanding thin recipe instructions: {e}", exc_info=True)
            return []

    def curate_recipe_to_czech(
        self,
        source_title: str,
        source_material: str,
        source_url: str = "",
        source_lang_hint: str = "",
        model: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Turn a real, attributed source recipe into a curated, novice-clear
        Czech record (Direction B — recipe grounding, see
        docs/recipe-grounding-plan.md §4 step 3).

        `source_material` is either a JSON-LD `schema.org/Recipe` blob (dumped
        to a string) or the cleaned page text when no structured data exists —
        the model extracts the real ingredients/method/timing/yield from
        whichever it's given, then *paraphrases* (never copies verbatim) into
        our schema, rewriting the steps for a beginner cook and translating
        everything into Czech.

        Returns a dict shaped to the `CuratedRecipe` content fields:
            {name_cs, name_en, description, meal_types, cuisine, difficulty,
             dietary_tags, ingredients:[{name, quantity, unit, optional}],
             instructions:[{text, time_min?, tip?}], base_servings,
             base_nutrition:{calories, protein, carbs, fat},
             prep_time, cook_time}
        Ingredient catalog mapping (catalog_id/canonical) is added afterwards
        by the deterministic resolver, not by the model.

        Returns {} on failure so the caller can skip the entry without raising.
        """
        model = model or self.default_model
        lang_note = f" The source appears to be in {source_lang_hint}." if source_lang_hint else ""
        url_note = f"\nSource URL (for your context only): {source_url}" if source_url else ""

        system_prompt = (
            "You are a Czech recipe editor curating a library of real, "
            "attributed dishes for a meal-planning app. You take a real source "
            "recipe and rewrite it into clear, beginner-friendly Czech — "
            "paraphrasing in your own words, never copying the source text "
            "verbatim. You preserve the real dish (ingredients, proportions, "
            "method, timing) but make the steps teach a novice how to cook it. "
            "Always respond with valid JSON only (no markdown, no code blocks)."
        )

        prompt = f"""Curate this real source recipe into our schema.{lang_note}

Source dish name: {source_title}{url_note}

Source material (structured JSON-LD or raw page text — extract the real
ingredients, method, servings and timing from it):
---
{source_material}
---

Produce a JSON object with EXACTLY these keys:

- "name_cs": the dish name in Czech (a real, named dish — not a description).
- "name_en": a short English gloss of the name (may be empty if obvious).
- "description": 1-2 appetizing sentences in Czech.
- "meal_types": array, any of ["breakfast","lunch","dinner","snack","small_meal"]
  — which slots this dish realistically fills.
- "cuisine": one lowercase word, e.g. "czech","italian","asian","mediterranean","mexican","american".
- "difficulty": "easy" or "medium" only (cap at medium; skip anything harder).
- "dietary_tags": array drawn from ["vegetarian","vegan","gluten_free","dairy_free","high_protein","low_carb"] — only tags that are actually TRUE for the dish.
- "ingredients": array of {{"name","quantity","unit","optional"}} in Czech.
  * "name": the ingredient in Czech, normalized & lowercase (e.g. "kuřecí prsa", "olivový olej").
  * "quantity": a number (grams/ml/pieces as appropriate); use null if truly to-taste.
  * "unit": one of "g","ml","ks","lžíce","lžička","špetka" (prefer g/ml/ks).
  * "optional": true for garnishes / to-taste extras, else false.
- "instructions": array of {{"text","time_min","tip"}} — 4 to 8 steps, in Czech.
  * "text": one clear step. Teach the novice: technique, pan/oven temperature,
    times, and doneness cues ("until golden", "until the juices run clear").
  * "time_min": integer minutes this step takes, or null.
  * "tip": a short optional helper tip in Czech, or null.
- "base_servings": integer — how many portions the quantities/nutrition below describe.
- "base_nutrition": {{"calories","protein","carbs","fat"}} per base_servings (numbers, grams for macros). Estimate from the ingredients if the source omits it.
- "prep_time": integer minutes of hands-on prep, or null.
- "cook_time": integer minutes of cooking, or null.

Rules:
- Paraphrase the method in your own words; do NOT reproduce the source's sentences.
- Keep the dish faithful — same ingredients and proportions as the real recipe.
- Everything user-facing (name_cs, description, ingredients, instructions) MUST be in Czech.
- Return ONLY the JSON object."""

        try:
            gemini_model = genai.GenerativeModel(
                model_name=model,
                system_instruction=system_prompt,
            )
            response = gemini_model.generate_content(
                prompt,
                generation_config={
                    "response_mime_type": "application/json",
                    "temperature": 0.4,
                },
                request_options={"timeout": 300},
            )
            parsed = json.loads(response.text)
            if not isinstance(parsed, dict):
                logger.error("curate_recipe_to_czech: model returned non-object JSON")
                return {}
            return parsed
        except Exception as e:
            logger.error(f"Error curating recipe '{source_title}': {e}", exc_info=True)
            return {}

    def extract_products_from_html(
        self,
        html_content: str,
        url: str,
        shop: str,
        country: str,
        model: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Use Gemini to extract products and prices from HTML content of a leaflet/offer page.
        
        This is much more robust than regex-based scraping and handles HTML structure changes.
        
        Args:
            html_content: HTML content of the page
            url: URL of the page being scraped
            shop: Shop code (e.g., 'LIDL_CZ')
            country: Country code (e.g., 'CZ')
            model: Model to use (optional, defaults to default model for cost efficiency)
            
        Returns:
            List of product dictionaries with structure:
            {
                'display_name': str,
                'ingredient_name': str,
                'price': Decimal (optional),
                'currency': str,
                'unit': str (optional),
                'source_url': str
            }
        """
        from bs4 import BeautifulSoup
        from decimal import Decimal
        from decimal import InvalidOperation
        
        model = model or self.default_model
        
        # Clean HTML - remove scripts, styles, and excessive tags
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Remove script and style elements
            for script in soup(["script", "style", "noscript", "meta", "link"]):
                script.decompose()
            
            # Get text content (this gives us the readable content without all the HTML noise)
            text_content = soup.get_text()
            
            # Clean up whitespace
            lines = (line.strip() for line in text_content.splitlines())
            chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
            text_content = ' '.join(chunk for chunk in chunks if chunk)
            
            # Limit to first 50k characters to avoid token limits (adjust based on model)
            text_content = text_content[:50000]
            
            logger.debug(f"Cleaned HTML: {len(html_content)} chars -> {len(text_content)} chars of text")
        except Exception as e:
            logger.error(f"Error cleaning HTML: {e}", exc_info=True)
            return []
        
        # Currency mapping
        currency_map = {
            'CZ': 'CZK',
            'SK': 'EUR',
            'PL': 'PLN',
            'HU': 'HUF',
        }
        currency = currency_map.get(country, 'CZK')
        
        system_prompt = (
            "You are a data extraction expert. Extract product information from web page content. "
            "Always respond with valid JSON only (no markdown, no code blocks)."
        )
        
        user_prompt = f"""Extract all products with prices from this web page content:

URL: {url}
Shop: {shop}
Country: {country}
Currency: {currency}

Page content:
{text_content}

Extract all products that have prices. For each product, provide:
- display_name: The full product name as shown on the page (include any package sizes mentioned, e.g., "Vejce 10 ks", "Kuřecí maso 1 kg")
- ingredient_name: Normalized ingredient name (lowercase, e.g., "Kuřecí prsa" -> "kuřecí prsa")
- price: Numeric price value (decimal number, not string, must be > 0). This is the TOTAL price shown for the product/package.
- currency: Currency code ({currency})
- unit: Unit of measurement - CRITICAL: This indicates what the price represents:
  * "ks" = price is per piece (if package_size is null/1) OR price is for a package measured in pieces (if package_size is set, e.g., package_size=10 means price for 10 pieces)
  * "kg" = price is per kilogram (if package_size is null/1) OR price is for a package measured in kg (if package_size is set, e.g., package_size=1 means price for 1kg package)
  * "g" = price is per gram (rare, usually prices are per kg) OR price is for a package measured in grams (if package_size is set, e.g., package_size=500 means price for 500g package)
  * "l" = price is per liter OR price is for a package measured in liters
  * "ml" = price is per milliliter (rare) OR price is for a package measured in milliliters
- package_size: Numeric value indicating the size of the package if the price is for a package:
  * If product shows "Vejce 10 ks - 64.90 CZK": package_size=10, unit="ks", price=64.90 (price is for 10 pieces)
  * If product shows "Kuřecí maso 1 kg - 89.90 CZK": package_size=1, unit="kg", price=89.90 (price is for 1kg) OR package_size=null, unit="kg", price=89.90 (price per kg)
  * If product shows "Špenát 500 g - 39 CZK": package_size=500, unit="g", price=39 (price is for 500g package)
  * If no package size is mentioned and price appears to be per unit: set package_size to null or 1

IMPORTANT: 
- If the product shows "Vejce 10 ks - 48 CZK", the price is 48 CZK for 10 pieces, so: price=48, unit="ks", package_size=10
- If the product shows "Kuřecí maso - 89.90 CZK/kg", the price is per kg, so: price=89.90, unit="kg", package_size=1 or null
- If the product shows "Špenát 500 g - 39 CZK", the price is for 500g package, so: price=39, unit="g", package_size=500
- Always extract package sizes from the product name or description if visible.

Return a JSON object with a single key "products" containing an array of product objects.
Only include products that have a clear price displayed (> 0). Ignore leaflet titles, navigation items, and items without prices.
If no products are found, return an empty array.

Example format:
{{
  "products": [
    {{
      "display_name": "Rajčata cherry Roma",
      "ingredient_name": "rajčata cherry roma",
      "price": 34.90,
      "currency": "CZK",
      "unit": null,
      "package_size": null,
      "source_url": "{url}"
    }},
    {{
      "display_name": "Kuřecí maso 1 kg",
      "ingredient_name": "kuřecí maso",
      "price": 89.90,
      "currency": "CZK",
      "unit": "kg",
      "package_size": 1,
      "source_url": "{url}"
    }},
    {{
      "display_name": "Vejce 10 ks",
      "ingredient_name": "vejce",
      "price": 48.00,
      "currency": "CZK",
      "unit": "ks",
      "package_size": 10,
      "source_url": "{url}"
    }},
    {{
      "display_name": "Špenát čerstvý 500 g",
      "ingredient_name": "špenát čerstvý",
      "price": 39.00,
      "currency": "CZK",
      "unit": "g",
      "package_size": 500,
      "source_url": "{url}"
    }}
  ]
}}"""
        
        try:
            gemini_model = genai.GenerativeModel(
                model_name=model,
                system_instruction=system_prompt
            )
            
            response = gemini_model.generate_content(
                user_prompt,
                generation_config={
                    "response_mime_type": "application/json",
                    "temperature": 0.1,  # Low temperature for consistent extraction
                },
                request_options={"timeout": 300}  # 5 minutes timeout for HTML extraction
            )
            
            content = response.text
            
            # Get token usage
            usage = response.usage_metadata
            input_tokens = usage.prompt_token_count
            output_tokens = usage.candidates_token_count
            
            # Calculate cost
            cost_usd = calculate_cost(input_tokens, output_tokens, model)
            
            logger.info(
                f"Gemini extraction for {url}: "
                f"{input_tokens} input tokens, {output_tokens} output tokens, "
                f"cost ${cost_usd}, model {model}"
            )
            
            parsed = json.loads(content)
            products = parsed.get('products', [])
            
            # Convert price to Decimal and validate
            validated_products = []
            for product in products:
                try:
                    price = product.get('price')
                    if price is not None:
                        if isinstance(price, (int, float)):
                            price = Decimal(str(price))
                        elif isinstance(price, str):
                            # Remove currency symbols and whitespace
                            price_str = price.replace('Kč', '').replace('€', '').replace('EUR', '').strip()
                            price_str = price_str.replace(',', '.')
                            price = Decimal(price_str)
                        else:
                            price = Decimal(str(price))
                        
                        # Only include products with positive prices
                        if price > 0:
                            product['price'] = price
                            
                            # Convert package_size to Decimal if present
                            package_size = product.get('package_size')
                            if package_size is not None:
                                try:
                                    if isinstance(package_size, (int, float)):
                                        product['package_size'] = Decimal(str(package_size))
                                    elif isinstance(package_size, str):
                                        product['package_size'] = Decimal(str(package_size).replace(',', '.'))
                                    else:
                                        product['package_size'] = Decimal(str(package_size))
                                except (ValueError, InvalidOperation):
                                    product['package_size'] = None
                            else:
                                product['package_size'] = None
                            
                            validated_products.append(product)
                        else:
                            logger.debug(f"Skipping product with non-positive price: {product.get('display_name')} - {price}")
                    else:
                        # Skip products without prices
                        logger.debug(f"Skipping product without price: {product.get('display_name')}")
                        continue
                except (ValueError, InvalidOperation) as e:
                    logger.warning(f"Invalid price for product {product.get('display_name')}: {e}")
                    continue
            
            logger.info(f"Gemini extracted {len(validated_products)} products with prices from {url}")

            # Phase E: source-evidence verification — drop items whose name or
            # price isn't present in the source HTML. Catches hallucinations
            # from the LLM extraction step before they hit storage.
            verified = []
            html_lower = (html_content or '').lower()
            for product in validated_products:
                name_token = (product.get('display_name') or product.get('ingredient_name') or '').lower().strip()
                price_token = str(product.get('price'))
                # Coerce trailing-zero variants: "34.9", "34.90", "34,90"
                price_variants = {price_token, price_token.replace('.', ','), price_token.rstrip('0').rstrip('.')}
                name_seen = bool(name_token) and name_token[:30] in html_lower
                price_seen = any(v and v in html_content for v in price_variants)
                if not name_seen or not price_seen:
                    logger.warning(
                        f"Dropping unverified product (name_seen={name_seen}, price_seen={price_seen}): "
                        f"{product.get('display_name')} - {product.get('price')}"
                    )
                    continue
                verified.append(product)
            if len(verified) != len(validated_products):
                logger.info(
                    f"Source-evidence filter: kept {len(verified)}/{len(validated_products)} for {url}"
                )
            return verified
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Gemini JSON response from {url}: {e}")
            logger.error(f"Response content: {content[:500] if 'content' in locals() else 'N/A'}")
            return []
        except Exception as e:
            logger.error(f"Error extracting products from HTML using Gemini for {url}: {e}", exc_info=True)
            return []
    
    def estimate_product_price(
        self,
        ingredient_name: str,
        quantity: Optional[str] = None,
        unit: Optional[str] = None,
        shop: Optional[str] = None,
        country: Optional[str] = None,
        model: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Ask Gemini to estimate the price of a product based on general knowledge about the shop.
        
        This is used as a fallback when the product is not found in scraped leaflet data.
        
        Args:
            ingredient_name: Name of the ingredient/product
            quantity: Required quantity (optional)
            unit: Unit of measurement (optional)
            shop: Shop code (e.g., 'LIDL_CZ')
            country: Country code (e.g., 'CZ')
            model: Model to use (optional)
            
        Returns:
            Dict with estimated price info or None if estimation fails:
            {
                'price': Decimal,
                'currency': str,
                'unit': str (optional),
                'display_name': str,
                'estimated': True,  # Flag to indicate this is an estimate
                'source': 'llm_estimate'
            }
        """
        model = model or self.default_model
        
        # Currency mapping
        currency_map = {
            'CZ': 'CZK',
            'SK': 'EUR',
            'PL': 'PLN',
            'HU': 'HUF',
        }
        currency = currency_map.get(country, 'CZK') if country else 'CZK'
        
        # Shop name mapping for better prompts
        shop_names = {
            'LIDL_CZ': 'Lidl Česká republika',
            'LIDL_SK': 'Lidl Slovensko',
            'ROHLIK': 'Rohlik.cz',
            'LUNYS': 'Lunys.sk',
        }
        shop_name = shop_names.get(shop, shop) if shop else 'supermarketu'
        
        system_prompt = (
            "You are a price estimation expert for Central European supermarkets. "
            "Provide realistic price estimates based on typical prices at the specified shop. "
            "Always respond with valid JSON only (no markdown, no code blocks)."
        )
        
        quantity_info = ""
        if quantity and unit:
            quantity_info = f" Required quantity: {quantity} {unit}."
        
        user_prompt = f"""Odhadni cenu produktu na základě znalosti cen v {shop_name}.

Produkt: {ingredient_name}
{quantity_info}
Měna: {currency}

Poskytni realistický odhad ceny, jakou by tento produkt typicky měl v {shop_name} (leden 2026).
Uvažuj běžné ceny, ne akční nabídky, pokud není uvedeno jinak.

Vrať JSON objekt s následující strukturou:
{{
  "estimated_price": 12.90,
  "currency": "{currency}",
  "unit": "ks",
  "display_name": "{ingredient_name}",
  "note": "Typická cena pro běžné balení"
}}

Důležité:
- Uveď cenu jako číslo (desetinné číslo, ne string)
- Pokud znáš typické balení (např. "pepř 20g", "sůl 500g", "jogurt 100g", "mleko 1L", "olej 700ml"), uveď to v unit
- Pokud odhaduješ cenu pro konkrétní množství, uveď cenu celkem pro to množství
- Pokud odhaduješ cenu za jednotku (kg, ks, ml), uveď jednotkovou cenu a unit

Příklad pro pepř černý mletý 20g v Lidl ČR:
{{
  "estimated_price": 8.90,
  "currency": "CZK",
  "unit": "20g",
  "display_name": "Pepř černý mletý",
  "note": "Typická cena za balení 20g"
}}

Příklad pro sůl 500g:
{{
  "estimated_price": 12.90,
  "currency": "CZK",
  "unit": "500g",
  "display_name": "Sůl kuchyňská",
  "note": "Typická cena za balení 500g"
}}"""
        
        try:
            gemini_model = genai.GenerativeModel(
                model_name=model,
                system_instruction=system_prompt
            )
            
            response = gemini_model.generate_content(
                user_prompt,
                generation_config={
                    "response_mime_type": "application/json",
                    "temperature": 0.3,  # Low temperature for consistent estimates
                },
                request_options={"timeout": 300}  # 5 minutes timeout
            )
            
            content = response.text
            parsed = json.loads(content)
            
            estimated_price = parsed.get('estimated_price')
            if estimated_price is None:
                logger.warning(f"No estimated_price in Gemini response for {ingredient_name}")
                return None
            
            try:
                if isinstance(estimated_price, (int, float)):
                    price = Decimal(str(estimated_price))
                elif isinstance(estimated_price, str):
                    price_str = estimated_price.replace(',', '.').strip()
                    price = Decimal(price_str)
                else:
                    price = Decimal(str(estimated_price))
                
                if price <= 0:
                    logger.warning(f"Invalid estimated price for {ingredient_name}: {price}")
                    return None
                
                result = {
                    'price': price,
                    'currency': parsed.get('currency', currency),
                    'unit': parsed.get('unit'),
                    'display_name': parsed.get('display_name', ingredient_name),
                    'estimated': True,
                    'source': 'llm_estimate',
                    'note': parsed.get('note', '')
                }
                
                logger.info(f"Gemini estimated price for {ingredient_name}: {price} {result['currency']} ({result.get('unit', 'unit')})")
                return result
                
            except (ValueError, InvalidOperation) as e:
                logger.warning(f"Invalid estimated price format for {ingredient_name}: {e}")
                return None
                
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Gemini price estimate JSON for {ingredient_name}: {e}")
            return None
        except Exception as e:
            logger.error(f"Error estimating price for {ingredient_name}: {e}", exc_info=True)
            return None


    # ─── Phase 0 / C helpers: staples bootstrap + canonical matching ──

    def suggest_store_staples(
        self,
        chain: str,
        country: str,
        n: int = 150,
        model: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Ask Gemini for a candidate list of staple products reliably stocked
        year-round at `chain` in `country`. Output is meant for offline human
        review into data/staples/<chain>.yaml — never written directly.

        Mirrors `estimate_product_price` in JSON-mode contract style.
        """
        model = model or self.default_model
        prompt = f"""You are a grocery merchandising analyst familiar with {chain} stores in {country}.

List {n} staple products that {chain} reliably carries year-round (not promotions,
not seasonal). Cover the main categories: dairy, eggs, meat & poultry, fish, fresh
produce, grains & pasta, oils, condiments, canned goods, baking.

Return a JSON object with one key "products" containing an array of objects:
[
  {{
    "name": "display name as printed on shelf",
    "canonical_slug": "english-slug-of-the-canonical-ingredient",
    "package_size": <number or null>,
    "package_unit": "g|kg|ml|l|ks",
    "brand": "private label or brand name or empty"
  }}
]

Important: use lowercase hyphenated English slugs for canonical_slug
(e.g. "white-yogurt", "rice-basmati"). Skip products that are seasonal or
promotional-only.
"""
        try:
            gemini_model = genai.GenerativeModel(
                model_name=model,
                system_instruction=(
                    "You are a Czech/Slovak retail expert. "
                    "Always respond with valid JSON only (no markdown)."
                ),
            )
            response = gemini_model.generate_content(
                prompt,
                generation_config={
                    "response_mime_type": "application/json",
                    "temperature": 0.4,
                },
                request_options={"timeout": 300},
            )
            data = json.loads(response.text)
            return data.get('products', []) or []
        except Exception as exc:
            logger.error(f"suggest_store_staples failed for {chain}: {exc}", exc_info=True)
            return []

    def match_canonical_ingredients_batch(
        self,
        names: List[str],
        candidates: List[Dict[str, str]],
        model: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Ask Gemini to map each raw product name to one of the candidate
        canonical ingredients (by slug) plus a confidence score.

        Used by `manage.py match_canonical_ingredients` for the LLM fallback
        pass after rule-based matching fails.
        """
        if not names:
            return []
        model = model or self.default_model
        prompt = f"""Match each product name to the best canonical ingredient slug.

Product names:
{json.dumps(names, ensure_ascii=False)}

Candidate canonical ingredients (slug → name, category):
{json.dumps(candidates, ensure_ascii=False, indent=2)}

Return a JSON object with one key "matches" containing an array, one item per
product name in the same order:
[
  {{
    "name": "<the input name>",
    "canonical_slug": "<slug from candidates, or null if no good match>",
    "confidence": <0.0 to 1.0>
  }}
]

Only emit a slug from the candidate list. Use null when nothing fits.
"""
        try:
            gemini_model = genai.GenerativeModel(
                model_name=model,
                system_instruction=(
                    "You are a grocery taxonomy expert. "
                    "Always respond with valid JSON only."
                ),
            )
            response = gemini_model.generate_content(
                prompt,
                generation_config={
                    "response_mime_type": "application/json",
                    "temperature": 0.1,
                },
                request_options={"timeout": 300},
            )
            data = json.loads(response.text)
            return data.get('matches', []) or []
        except Exception as exc:
            logger.error(f"match_canonical_ingredients_batch failed: {exc}", exc_info=True)
            return []

    # ─── Catalog-Constrained Generation (Phase 4) ─────────────────────

    def generate_catalog_constrained_plan(
        self,
        user_prompt: str,
        catalog_text: str,
        goal: Any,
        model: Optional[str] = None,
        exclusions: "Optional[ResolvedRestrictions]" = None,
    ) -> Dict[str, Any]:
        """
        Generate a meal plan constrained to a real product catalog.

        Instead of browsing a URL, the LLM receives the actual catalog of
        available products and MUST use only those (plus pantry staples).
        This eliminates price hallucination entirely.

        Args:
            user_prompt: Full user prompt/clinical document
            catalog_text: Compact text block of available products (from CatalogService)
            goal: DietaryGoal object
            model: Optional model override

        Returns:
            Dict with 'response' (parsed JSON), token counts, cost
        """
        model = model or self.default_model

        system_prompt = self._build_meal_system_prompt(
            goal=goal,
            exclusions=exclusions,
            catalog_text=catalog_text,
            single_meal=False,
        )

        full_prompt = f"""{user_prompt}

Create a {getattr(goal, 'num_days', 7)}-day meal plan using ONLY the available products listed above.
Keep all text concise — 3 steps max per recipe, 1 sentence descriptions."""

        try:
            gemini_model = genai.GenerativeModel(
                model_name=model, system_instruction=system_prompt
            )
            max_tokens = getattr(settings, 'GEMINI_MAX_OUTPUT_TOKENS', 65536)

            response = gemini_model.generate_content(
                full_prompt,
                generation_config={
                    "response_mime_type": "application/json",
                    "temperature": 0.5,
                    "max_output_tokens": max_tokens,
                },
                request_options={"timeout": 300},
            )

            if response.candidates and hasattr(response.candidates[0], 'finish_reason'):
                finish_reason = response.candidates[0].finish_reason
                if finish_reason.name == 'MAX_TOKENS':
                    logger.error(f"Catalog-constrained plan truncated at {max_tokens} tokens")
                    raise ValueError(f"Response truncated at {max_tokens} tokens")

            content = response.text
            usage = response.usage_metadata

            try:
                parsed = json.loads(content)
            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON from catalog-constrained generation: {e}")
                cleaned = re.sub(r',\s*}', '}', content)
                cleaned = re.sub(r',\s*]', ']', cleaned)
                parsed = json.loads(cleaned)

            return {
                'response': parsed,
                'input_tokens': usage.prompt_token_count,
                'output_tokens': usage.candidates_token_count,
                'total_tokens': usage.total_token_count,
                'cost_usd': calculate_cost(
                    usage.prompt_token_count, usage.candidates_token_count, model
                ),
                'model': model,
            }

        except Exception as e:
            logger.error(f"Catalog-constrained generation error: {e}", exc_info=True)
            raise


    def generate_discount_optimization(
        self,
        current_plan_days: List[Dict[str, Any]],
        current_shopping_list: List[Dict[str, Any]],
        discounted_products: str,
        goal: Any,
        model: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Suggest ingredient swaps to use currently discounted products.

        Receives the existing plan and a list of discounted products,
        returns swap suggestions with price comparisons.
        """
        model = model or self.default_model

        language_names = {
            'cs': 'Czech', 'sk': 'Slovak', 'pl': 'Polish',
            'hu': 'Hungarian', 'ro': 'Romanian', 'bg': 'Bulgarian',
            'de': 'German', 'en': 'English',
        }
        target_language = language_names.get(
            getattr(goal, 'language_code', 'en') or 'en', 'English'
        )

        current_plan_json = json.dumps(current_plan_days, ensure_ascii=False, indent=1)
        current_list_json = json.dumps(current_shopping_list, ensure_ascii=False, indent=1)

        system_prompt = f"""You are a nutrition expert helping optimize a meal plan for cost savings.

RESPONSE FORMAT: Valid JSON only, no markdown, all text in {target_language}.

TASK: Review the current meal plan and shopping list. The candidate offers below were
extracted from current store leaflets (akce/letáky). Some carry an explicit original
price (shown as "(původně X Kč)" or "(-N%)") — those are confirmed discounts. Others
are leaflet-featured items without an explicit original price; treat those as candidates
only and propose a swap only if the leaflet price is meaningfully LOWER than the user's
current shopping-list price for the same ingredient.

CURRENT MEAL PLAN:
{current_plan_json}

CURRENT SHOPPING LIST (with each item's current price):
{current_list_json}

CANDIDATE LEAFLET OFFERS (each line: #id [SHOP_CODE] name — price [optional discount markers]):
{discounted_products}

OUTPUT STRUCTURE:
{{
  "swaps": [
    {{
      "original_ingredient": "ingredient name from current plan",
      "original_price": 89.90,
      "replacement_product": "leaflet product name",
      "replacement_catalog_id": 42,
      "replacement_price": 59.90,
      "source_shop": "LIDL_CZ",
      "saving": 30.00,
      "affected_meals": ["Den 1 Oběd: Meal Name", "Den 3 Večeře: Meal Name"],
      "reason": "Brief explanation why the swap works"
    }}
  ],
  "total_saving": 120.50,
  "optimized_days": [... modified days array with swaps applied ...],
  "optimized_shopping_list": [
    {{"ingredient": "name", "quantity": "500", "unit": "g", "catalog_id": 42, "pantry": false}}
  ]
}}

RULES:
- Only suggest a swap when the candidate's per-unit price is genuinely lower than the user's current price for that ingredient — never propose a swap that costs the same or more.
- Real discount detection is computed downstream from STORE_REGULAR baselines, not inferred from your output.
- Do NOT swap if it would ruin the recipe (e.g., don't replace chicken with tofu in chicken soup).
- Include the full optimized_days and optimized_shopping_list with all swaps applied.
- Keep the same meal structure — only change ingredients, not meal names or count.
- Preserve nutritional balance as much as possible.
- For each swap, set "source_shop" to the [SHOP_CODE] tag from the offer line you selected.
- If no good swaps exist, return {{"swaps": [], "total_saving": 0}}."""

        try:
            gemini_model = genai.GenerativeModel(
                model_name=model, system_instruction=system_prompt
            )

            response = gemini_model.generate_content(
                "Analyze the current plan and suggest discount-based swaps.",
                generation_config={
                    "response_mime_type": "application/json",
                    "temperature": 0.3,
                    "max_output_tokens": 65536,
                },
                request_options={"timeout": 300},
            )

            content = response.text
            usage = response.usage_metadata

            try:
                parsed = json.loads(content)
            except json.JSONDecodeError:
                cleaned = re.sub(r',\s*}', '}', content)
                cleaned = re.sub(r',\s*]', ']', cleaned)
                parsed = json.loads(cleaned)

            return {
                'response': parsed,
                'input_tokens': usage.prompt_token_count,
                'output_tokens': usage.candidates_token_count,
                'total_tokens': usage.total_token_count,
                'cost_usd': calculate_cost(
                    usage.prompt_token_count, usage.candidates_token_count, model
                ),
                'model': model,
            }

        except Exception as e:
            logger.error(f"Discount optimization generation error: {e}", exc_info=True)
            raise


# Temporary alias for backward compatibility during migration
# Can be removed after full migration
OpenAIService = GeminiService
