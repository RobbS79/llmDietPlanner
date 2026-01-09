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
from typing import Dict, Any, Optional, List
import json
import logging
import re
from decimal import Decimal, InvalidOperation

from django.conf import settings
import google.generativeai as genai

logger = logging.getLogger(__name__)


# Gemini pricing per 1M tokens (as of 2024)
# Prices in USD
GEMINI_PRICING = {
    'gemini-2.0-flash-exp': {
        'input': 0.0,  # Free tier
        'output': 0.0,  # Free tier
    },
    'gemini-1.5-pro': {
        'input': 1.25,  # $1.25 per 1M input tokens
        'output': 5.00,  # $5.00 per 1M output tokens
    },
    'gemini-1.5-flash': {
        'input': 0.075,  # $0.075 per 1M input tokens
        'output': 0.30,  # $0.30 per 1M output tokens
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
            'gemini-2.0-flash-exp'  # Default to free tier
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
    
    def generate_complete_plan_with_shopping_list(
        self,
        user_prompt: str,  # Full clinical document from user
        shop_url: str,
        goal: Any,  # DietaryGoal - using Any to avoid circular import
        model: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Single comprehensive LLM call that:
        1. Browses shop_url for current prices
        2. Generates meal plan with recipes (step-by-step instructions)
        3. Creates shopping list with real prices from shop_url
        4. Calculates total costs
        
        This matches the Gemini web UI approach - one call does everything.
        
        Args:
            user_prompt: Full user prompt/document with dietary requirements
            shop_url: Shop URL for Gemini to browse (e.g., https://www.rohlik.cz/cs/akcni-nabidka)
            goal: DietaryGoal object with all configuration
            model: Optional model override
            
        Returns:
            Dict with 'response' containing complete plan with shopping list
        """
        model = model or self.default_model
        
        # Language mapping
        language_names = {
            'cs': 'Czech', 'sk': 'Slovak', 'pl': 'Polish',
            'hu': 'Hungarian', 'ro': 'Romanian', 'bg': 'Bulgarian',
            'de': 'German', 'en': 'English',
        }
        target_language = language_names.get(getattr(goal, 'language_code', 'en') or 'en', 'English')
        
        # Currency mapping
        currency_map = {
            'CZ': 'CZK', 'SK': 'EUR', 'PL': 'PLN', 'HU': 'HUF',
        }
        country = getattr(goal, 'country', 'CZ')
        currency = currency_map.get(country, 'CZK')
        
        # Build comprehensive system prompt
        system_prompt = f"""You are a nutrition expert and shopping assistant creating personalised meal plans with complete shopping lists.

RESPONSE FORMAT:
- Valid JSON only, no markdown, no code blocks
- All text content in {target_language} language

TASK:
1. Browse {shop_url} to get current product prices and availability
2. Create a meal plan with recipes (step-by-step instructions)
3. Generate complete shopping list with exact quantities
4. Match products from {shop_url} and use REAL prices (not estimates)
5. Calculate total cost

OUTPUT STRUCTURE:
{{
  "days": [
    {{
      "day_number": 1,
      "breakfast": {{
        "name": "meal name",
        "description": "brief description",
        "preparation_time": 15,
        "ingredients": [
          {{"name": "ingredient", "quantity": 200, "unit": "g"}}
        ],
        "instructions": ["Step 1", "Step 2", ...],
        "nutritional_info": {{
          "calories": 450,
          "protein": "30g",
          "carbs": "25g",
          "fat": "20g"
        }}
      }},
      "lunch": {{...}},
      "dinner": {{...}},
      "small_meals": [{{...}}],
      "snacks": [{{...}}]
    }}
  ],
  "shopping_list": [
    {{
      "ingredient": "ingredient name",
      "quantity": 500,
      "unit": "g",
      "matched_product_name": "actual product name from {shop_url}",
      "price": 89.90,
      "price_total": 89.90,
      "currency": "{currency}",
      "package_size": 500,
      "product_unit": "g",
      "price_type": "REGULAR" or "DISCOUNTED",
      "estimated": false
    }}
  ],
  "total_cost": 2345.67
}}

CRITICAL RULES:
1. Browse {shop_url} and use ACTUAL prices from the website
2. If product not found on {shop_url}, mark as estimated: true
3. For ingredients sold per piece (avocado, eggs), convert weights to pieces (e.g., 200g avocado = 2 pieces)
4. For liquids, select appropriate package size (e.g., 300ml oil needed → 500ml bottle from shop)
5. DO NOT consider leftovers - always round UP to purchasable packages
6. Include step-by-step cooking instructions for each meal (keep instructions concise: 3-4 steps max per meal)
7. All prices must be in {currency}
8. Quantities should be realistic per-meal amounts
9. Keep all text concise - descriptions should be brief (1-2 sentences max)

MEAL PLAN REQUIREMENTS:
- {getattr(goal, 'num_days', 7)} days
- Breakfast: {'YES' if getattr(goal, 'breakfast', True) else 'NO'}
- Lunch: {'YES' if getattr(goal, 'lunch', True) else 'NO'}
- Dinner: {'YES' if getattr(goal, 'dinner', True) else 'NO'}
- Small meals: {getattr(goal, 'small_meals_per_day', 2)} per day
- Snacks: {getattr(goal, 'snacks_per_day', 2)} per day
- Language: {target_language}
- Currency: {currency}"""

        full_prompt = f"""{user_prompt}

Create a complete meal plan with shopping list from {shop_url}.
Browse the shop URL to get current prices and availability.
Return JSON with days (meal plan with recipes) and shopping_list (with real prices)."""

        try:
            gemini_model = genai.GenerativeModel(
                model_name=model,
                system_instruction=system_prompt
            )
            
            # Determine max_output_tokens based on model limits
            # gemini-2.0-flash-exp max is 8192 tokens
            # For Czech/Slovak responses, ~1 token per 2-3 chars due to accents
            # 23k chars ≈ 7.6k-11.5k tokens, so 8192 may be tight for large plans
            MAX_OUTPUT_TOKENS = 8192  # Max for gemini-2.0-flash-exp model
            
            response = gemini_model.generate_content(
                full_prompt,
                generation_config={
                    "response_mime_type": "application/json",
                    "temperature": 0.7,
                    "max_output_tokens": MAX_OUTPUT_TOKENS,
                },
                request_options={"timeout": 300}  # 5 minutes for complex response
            )
            
            content = response.text
            usage = response.usage_metadata
            
            # Check if response was truncated (finish_reason should be 'STOP' for complete responses)
            finish_reason = None
            try:
                if hasattr(response, 'candidates') and response.candidates:
                    finish_reason = getattr(response.candidates[0], 'finish_reason', None)
                    if finish_reason and finish_reason != 'STOP':
                        logger.warning(f"Response may be truncated: finish_reason={finish_reason}")
            except (AttributeError, IndexError):
                pass
            
            # Apply same JSON cleaning logic as generate_dietary_plan
            response_length = len(content)
            logger.debug(f"Gemini complete plan response length: {response_length} characters, output_tokens: {usage.candidates_token_count}")
            
            # Check if we hit the token limit (indicates truncation)
            # For Czech/Slovak, ~1 token per 2-3 chars, so 23k chars ≈ 7.6k-11.5k tokens
            if usage.candidates_token_count >= 8150:  # Very close to MAX_OUTPUT_TOKENS limit (8192)
                logger.warning(
                    f"Response may be truncated: used {usage.candidates_token_count} tokens "
                    f"(limit: {MAX_OUTPUT_TOKENS}). Consider using a model with higher limits for plans >7 days."
                )
            
            if response_length > 10000:
                try:
                    with open('/tmp/gemini_complete_plan_response.json', 'w', encoding='utf-8') as f:
                        f.write(content)
                    logger.warning(f"Response too long ({response_length} chars), saved to /tmp/gemini_complete_plan_response.json")
                except Exception:
                    pass
            
            # Parse JSON with cleaning
            try:
                parsed_response = json.loads(content)
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse Gemini complete plan JSON: {e}")
                logger.error(f"Error at position {e.pos if hasattr(e, 'pos') else 'unknown'}")
                logger.error(f"Response length: {response_length} chars, Output tokens: {usage.candidates_token_count}")
                logger.error(f"Response content (first 1000 chars): {content[:1000]}")
                logger.error(f"Response content (last 1000 chars): {content[-1000:] if len(content) > 1000 else content}")
                
                # Check for truncation indicators
                is_truncated = (
                    (finish_reason and finish_reason != 'STOP') or
                    (usage.candidates_token_count >= MAX_OUTPUT_TOKENS - 10) or  # Within 10 tokens of limit
                    ('Unterminated string' in str(e)) or
                    ('Expecting value' in str(e) and hasattr(e, 'pos') and e.pos >= len(content) - 10)
                )
                
                if is_truncated:
                    logger.error("Response appears to be truncated - retrying with more concise prompt...")
                    # Can't increase beyond 8192 for gemini-2.0-flash-exp, so modify prompt to be more concise
                    concise_prompt = f"""{user_prompt}

Create a complete meal plan with shopping list from {shop_url}.
IMPORTANT: Keep instructions brief (2-3 steps max per meal). Keep descriptions short.
Browse the shop URL to get current prices and availability.
Return JSON with days (meal plan with recipes) and shopping_list (with real prices)."""
                    
                    response = gemini_model.generate_content(
                        concise_prompt,
                        generation_config={
                            "response_mime_type": "application/json",
                            "temperature": 0.7,
                            "max_output_tokens": MAX_OUTPUT_TOKENS,  # Still 8192 (model limit)
                        },
                        request_options={"timeout": 300}
                    )
                    content = response.text
                    usage = response.usage_metadata
                    logger.info(f"Retry response length: {len(content)} chars, tokens: {usage.candidates_token_count}")
                    # Try parsing the retry response directly
                    try:
                        parsed_response = json.loads(content)
                        logger.info("Successfully parsed JSON from retry response")
                        return {
                            'response': parsed_response,
                            'input_tokens': usage.prompt_token_count,
                            'output_tokens': usage.candidates_token_count,
                            'total_tokens': usage.total_token_count,
                            'cost_usd': calculate_cost(usage.prompt_token_count, usage.candidates_token_count, model),
                            'model': model,
                        }
                    except json.JSONDecodeError as retry_error:
                        logger.error(f"Retry response also has JSON errors: {retry_error}")
                        # Continue with cleaning logic below
                
                # Try cleaning
                try:
                    logger.info("Attempting to clean and repair JSON...")
                    cleaned_content = content
                    # Remove trailing incomplete strings/objects
                    if is_truncated:
                        # Try to find last complete JSON object and close it
                        last_complete_pos = max(
                            cleaned_content.rfind('}') if cleaned_content.rfind('}') > cleaned_content.rfind(']') else -1,
                            cleaned_content.rfind(']')
                        )
                        if last_complete_pos > len(cleaned_content) * 0.8:  # If close to end
                            # Try to close incomplete structures
                            open_braces = cleaned_content.count('{') - cleaned_content.count('}')
                            open_brackets = cleaned_content.count('[') - cleaned_content.count(']')
                            cleaned_content = cleaned_content.rstrip().rstrip(',')
                            cleaned_content += '}' * open_braces
                            cleaned_content += ']' * open_brackets
                            logger.info(f"Attempted to close {open_braces} braces and {open_brackets} brackets")
                    
                    cleaned_content = re.sub(r',\s*}', '}', cleaned_content)
                    cleaned_content = re.sub(r',\s*]', ']', cleaned_content)
                    parsed_response = json.loads(cleaned_content)
                    logger.warning("Successfully parsed JSON after cleaning")
                except json.JSONDecodeError as e2:
                    logger.error(f"Failed to parse even after cleaning: {e2}")
                    try:
                        with open('/tmp/gemini_invalid_complete_plan.json', 'w', encoding='utf-8') as f:
                            f.write(content)
                        logger.error(f"Saved invalid response to /tmp/gemini_invalid_complete_plan.json")
                    except Exception:
                        pass
                    raise ValueError(f"Gemini returned invalid JSON that could not be repaired (likely truncated): {e}")
            
            return {
                'response': parsed_response,
                'input_tokens': usage.prompt_token_count,
                'output_tokens': usage.candidates_token_count,
                'total_tokens': usage.total_token_count,
                'cost_usd': calculate_cost(usage.prompt_token_count, usage.candidates_token_count, model),
                'model': model,
            }
            
        except Exception as e:
            logger.error(f"Gemini complete plan API error: {e}", exc_info=True)
            raise
    
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
        
        prompt = f"""Generate detailed, step-by-step cooking instructions for the following meal:

Meal Name: {meal_name}
Ingredients: {ingredients_text}{description_text}

Requirements:
- Provide 4-8 clear, specific cooking steps
- Each step should be a complete action (e.g., "Heat 1 tablespoon of olive oil in a pan over medium heat")
- Include specific temperatures, times, and techniques where appropriate
- Instructions should be practical and easy to follow
- Write in {language_code} language

Return ONLY a JSON object with an "instructions" array of strings:
{{"instructions": ["Step 1 instruction", "Step 2 instruction", "Step 3 instruction", ...]}}"""

        system_prompt = "You are a professional chef providing clear, detailed cooking instructions. Always respond with valid JSON."
        
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
            return validated_products
            
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


# Temporary alias for backward compatibility during migration
# Can be removed after full migration
OpenAIService = GeminiService
