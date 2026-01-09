"""
OpenAI LLM Service for Dietary Plan Generation
==============================================

This module handles all OpenAI API interactions for the diet planner application.

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
from decimal import Decimal

from django.conf import settings
from openai import OpenAI
import tiktoken

logger = logging.getLogger(__name__)


# OpenAI pricing per 1M tokens (as of 2024, update as needed)
# Prices in USD
OPENAI_PRICING = {
    'gpt-4o': {
        'input': 2.50,  # $2.50 per 1M input tokens
        'output': 10.00,  # $10.00 per 1M output tokens
    },
    'gpt-4o-mini': {
        'input': 0.15,  # $0.15 per 1M input tokens
        'output': 0.60,  # $0.60 per 1M output tokens
    },
    'gpt-4-turbo': {
        'input': 10.00,  # $10.00 per 1M input tokens
        'output': 30.00,  # $30.00 per 1M output tokens
    },
    'gpt-4': {
        'input': 30.00,  # $30.00 per 1M input tokens
        'output': 60.00,  # $60.00 per 1M output tokens
    },
    'gpt-3.5-turbo': {
        'input': 0.50,  # $0.50 per 1M input tokens
        'output': 1.50,  # $1.50 per 1M output tokens
    },
}


def get_model_pricing(model: str) -> Dict[str, float]:
    """
    Get pricing for a specific model.
    
    Args:
        model: Model name (e.g., 'gpt-4o', 'gpt-4o-mini')
        
    Returns:
        Dict with 'input' and 'output' prices per 1M tokens
    """
    # Handle model variants (e.g., 'gpt-4o-2024-05-13' -> 'gpt-4o')
    base_model = model.split('-')[0:3]  # Get first 3 parts (e.g., ['gpt', '4o', '2024'])
    if len(base_model) >= 2:
        base_model_name = '-'.join(base_model[:2])  # 'gpt-4o'
    else:
        base_model_name = model
    
    return OPENAI_PRICING.get(
        base_model_name,
        OPENAI_PRICING.get('gpt-4o-mini')  # Default to cheapest option
    )


def count_tokens(text: str, model: str = 'gpt-4o') -> int:
    """
    Count tokens in a text string using tiktoken.
    
    Args:
        text: Text to count tokens for
        model: Model name to use for encoding
        
    Returns:
        Number of tokens
    """
    try:
        # Map model names to tiktoken encodings
        encoding_map = {
            'gpt-4o': 'o200k_base',
            'gpt-4o-mini': 'o200k_base',
            'gpt-4-turbo': 'cl100k_base',
            'gpt-4': 'cl100k_base',
            'gpt-3.5-turbo': 'cl100k_base',
        }
        
        # Get base model for encoding
        base_model = model.split('-')[0:3]
        if len(base_model) >= 2:
            base_model_name = '-'.join(base_model[:2])
        else:
            base_model_name = model
        
        encoding_name = encoding_map.get(base_model_name, 'cl100k_base')
        
        # Get encoding
        encoding = tiktoken.get_encoding(encoding_name)
        
        # Count tokens
        return len(encoding.encode(text))
    except Exception as e:
        logger.warning(f"Error counting tokens: {e}. Using approximate count.")
        # Fallback: approximate 1 token = 4 characters
        return len(text) // 4


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


class OpenAIService:
    """
    Service for interacting with OpenAI API.
    Handles API calls, token counting, and cost tracking.
    """
    
    def __init__(self):
        """Initialise OpenAI client with API key from settings."""
        api_key = getattr(settings, 'OPENAI_API_KEY', None)
        if not api_key:
            raise ValueError(
                "OPENAI_API_KEY not set in settings. "
                "Please set it as an environment variable."
            )
        
        self.client = OpenAI(api_key=api_key)
        self.default_model = getattr(
            settings,
            'OPENAI_MODEL',
            'gpt-4o-mini'  # Default to cost-effective model
        )
    
    def generate_dietary_plan(
        self,
        prompt_text: str,
        system_prompt: Optional[str] = None,
        model: Optional[str] = None,
        language_code: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Generate a dietary plan using OpenAI API.
        
        Args:
            prompt_text: User prompt (JSON formatted)
            system_prompt: System prompt (optional, uses default if not provided)
            model: Model to use (optional, uses default if not provided)
            language_code: Language code for response (e.g., 'cs', 'pl', 'en')
            
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
        
        # Count input tokens
        input_tokens = count_tokens(system_prompt + prompt_text, model)
        
        try:
            # Make API call
            response = self.client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt_text}
                ],
                response_format={"type": "json_object"},
                temperature=0.7,
            )
            
            # Extract response
            content = response.choices[0].message.content
            
            # Get token usage from API response
            usage = response.usage
            input_tokens_api = usage.prompt_tokens
            output_tokens_api = usage.completion_tokens
            total_tokens_api = usage.total_tokens
            
            # Use API token counts (more accurate)
            input_tokens = input_tokens_api
            output_tokens = output_tokens_api
            total_tokens = total_tokens_api
            
            # Calculate cost
            cost_usd = calculate_cost(input_tokens, output_tokens, model)
            
            # Parse JSON response
            try:
                parsed_response = json.loads(content)
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse LLM JSON response: {e}")
                logger.error(f"Response content: {content}")
                raise ValueError(f"LLM returned invalid JSON: {e}")
            
            return {
                'response': parsed_response,
                'input_tokens': input_tokens,
                'output_tokens': output_tokens,
                'total_tokens': total_tokens,
                'cost_usd': cost_usd,
                'model': model,
            }
            
        except Exception as e:
            logger.error(f"OpenAI API error: {e}")
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
        Generate detailed cooking instructions for a recipe using LLM.
        
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

Return ONLY a JSON array of instruction strings, like this:
["Step 1 instruction", "Step 2 instruction", "Step 3 instruction", ...]"""

        system_prompt = "You are a professional chef providing clear, detailed cooking instructions. Always respond with valid JSON."
        
        try:
            response = self.client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0.7,
            )
            
            content = response.choices[0].message.content
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
            logger.error(f"Error generating recipe instructions: {e}")
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
        Use LLM to extract products and prices from HTML content of a leaflet/offer page.
        
        This is much more robust than regex-based scraping and handles HTML structure changes.
        
        Args:
            html_content: HTML content of the page
            url: URL of the page being scraped
            shop: Shop code (e.g., 'LIDL_CZ')
            country: Country code (e.g., 'CZ')
            model: Model to use (optional, defaults to gpt-4o-mini for cost efficiency)
            
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
        from decimal import Decimal, InvalidOperation
        
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
            # Count input tokens for logging
            input_tokens = count_tokens(system_prompt + user_prompt, model)
            logger.debug(f"LLM extraction request: {input_tokens} input tokens for {url}")
            
            response = self.client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0.1,  # Low temperature for consistent extraction
            )
            
            content = response.choices[0].message.content
            
            # Get token usage
            usage = response.usage
            input_tokens_api = usage.prompt_tokens
            output_tokens_api = usage.completion_tokens
            total_tokens_api = usage.total_tokens
            
            # Calculate cost
            cost_usd = calculate_cost(input_tokens_api, output_tokens_api, model)
            
            logger.info(
                f"LLM extraction for {url}: "
                f"{input_tokens_api} input tokens, {output_tokens_api} output tokens, "
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
            
            logger.info(f"LLM extracted {len(validated_products)} products with prices from {url}")
            return validated_products
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM JSON response from {url}: {e}")
            logger.error(f"Response content: {content[:500] if 'content' in locals() else 'N/A'}")
            return []
        except Exception as e:
            logger.error(f"Error extracting products from HTML using LLM for {url}: {e}", exc_info=True)
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
        Ask LLM to estimate the price of a product based on general knowledge about the shop.
        
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
            response = self.client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0.3,  # Low temperature for consistent estimates
            )
            
            content = response.choices[0].message.content
            parsed = json.loads(content)
            
            estimated_price = parsed.get('estimated_price')
            if estimated_price is None:
                logger.warning(f"No estimated_price in LLM response for {ingredient_name}")
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
                
                logger.info(f"LLM estimated price for {ingredient_name}: {price} {result['currency']} ({result.get('unit', 'unit')})")
                return result
                
            except (ValueError, InvalidOperation) as e:
                logger.warning(f"Invalid estimated price format for {ingredient_name}: {e}")
                return None
                
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM price estimate JSON for {ingredient_name}: {e}")
            return None
        except Exception as e:
            logger.error(f"Error estimating price for {ingredient_name}: {e}", exc_info=True)
            return None

