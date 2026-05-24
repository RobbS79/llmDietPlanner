"""
Shopping List Generation Service - Phase 2 of Two-Phase LLM Architecture.
Generates shopping list WITH actual shop availability and pricing data.
"""
import json
import logging
from typing import Dict, Any, Optional, List
from decimal import Decimal

from django.conf import settings

from diet_planner.models import DietaryGoal
from diet_planner.llm_service import GeminiService

logger = logging.getLogger(__name__)


class ShoppingListService:
    """
    Service for generating shopping lists using Gemini.
    Phase 2: Creates optimized shopping list based on:
    - Meal plan from Phase 1
    - Actual shop availability/pricing data
    """

    def __init__(self):
        """Initialize Gemini service."""
        self.llm_service = GeminiService()
        self.model = getattr(settings, 'GEMINI_MODEL', 'gemini-2.0-flash')

    def generate_shopping_list(
        self,
        meal_plan: Dict[str, Any],
        shop_data: List[Dict[str, Any]],
        goal: DietaryGoal
    ) -> Dict[str, Any]:
        """
        Generate a shopping list based on meal plan and shop data.

        Args:
            meal_plan: Dict with 'days' from Phase 1
            shop_data: List of available products with prices from scraped data
            goal: DietaryGoal for context

        Returns:
            Dict containing:
                - 'shopping_list': List of shopping items with matched prices
                - 'input_tokens': Token count
                - 'output_tokens': Token count
                - 'cost_usd': API cost
                - 'model': Model used
        """
        prompt = self._build_shopping_list_prompt(meal_plan, shop_data, goal)
        system_prompt = self._build_system_prompt(goal)

        try:
            import google.generativeai as genai
            
            # Use Gemini API
            gemini_model = genai.GenerativeModel(
                model_name=self.model,
                system_instruction=system_prompt
            )
            
            response = gemini_model.generate_content(
                prompt,
                generation_config={
                    "response_mime_type": "application/json",
                    "temperature": 0.3,  # Lower temperature for consistent matching
                },
                request_options={"timeout": 300}  # 5 minutes timeout for shopping list generation
            )

            content = response.text
            usage = response.usage_metadata
            
            input_tokens = usage.prompt_token_count
            output_tokens = usage.candidates_token_count
            total_tokens = usage.total_token_count

            # Calculate cost
            from diet_planner.llm_service import calculate_cost
            cost_usd = calculate_cost(input_tokens, output_tokens, self.model)

            # Parse response
            parsed = json.loads(content)
            shopping_list = parsed.get('shopping_list', [])

            # Post-process shopping list
            shopping_list = self._post_process_shopping_list(shopping_list, goal)

            # Log statistics
            items_with_price = len([i for i in shopping_list if i.get('price')])
            logger.info(
                f"ShoppingListService: Generated {len(shopping_list)} items, "
                f"{items_with_price} with prices, tokens: {total_tokens}, cost: ${cost_usd}"
            )

            return {
                'shopping_list': shopping_list,
                'input_tokens': input_tokens,
                'output_tokens': output_tokens,
                'total_tokens': total_tokens,
                'cost_usd': cost_usd,
                'model': self.model,
            }

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse shopping list JSON: {e}")
            raise ValueError(f"LLM returned invalid JSON: {e}")
        except Exception as e:
            logger.exception(f"ShoppingListService error: {e}")
            raise

    def _build_system_prompt(self, goal: DietaryGoal) -> str:
        """Build system prompt for shopping list generation."""
        language_names = {
            'cs': 'Czech', 'sk': 'Slovak', 'pl': 'Polish',
            'hu': 'Hungarian', 'ro': 'Romanian', 'bg': 'Bulgarian',
            'de': 'German', 'en': 'English',
        }
        target_language = language_names.get(goal.language_code, 'English')

        return f"""You are a shopping list optimizer for {target_language}-speaking customers.
Your task is to create an accurate shopping list based on a meal plan and available products.
Your responses must be valid JSON only, with no markdown formatting.

CRITICAL RULES:
1. Match ingredients ONLY to products that are the SAME or VERY SIMILAR type
2. If an ingredient is not available, set price to null - DO NOT match to unrelated products
3. Calculate EXACT quantities needed for all meals across all days
4. Use metric units (g, kg, ml, l, ks)
5. Prioritize DISCOUNTED items when available"""

    def _build_shopping_list_prompt(
        self,
        meal_plan: Dict[str, Any],
        shop_data: List[Dict[str, Any]],
        goal: DietaryGoal
    ) -> str:
        """Build the user prompt for shopping list generation."""
        # Extract all ingredients from meal plan
        all_ingredients = self._extract_ingredients_from_meal_plan(meal_plan)

        # Limit shop data to avoid token limits (prioritize discounted items)
        shop_data_limited = self._limit_shop_data(shop_data, max_items=200)

        prompt_data = {
            "task": "generate_shopping_list",
            "context": {
                "country": goal.country,
                "city": goal.city,
                "shop": goal.shop,
                "currency": goal.currency,
                "num_days": goal.num_days,
            },
            "meal_plan_summary": {
                "total_days": len(meal_plan.get('days', [])),
                "ingredients_needed": all_ingredients,
            },
            "available_products": shop_data_limited,
            "instructions": {
                "output_format": "JSON object with 'shopping_list' array",
                "for_each_item": [
                    "ingredient: normalized ingredient name",
                    "quantity: exact amount needed (numeric)",
                    "unit: metric unit (g, kg, ml, l, ks)",
                    "matched_product_name: product name from available_products if matched",
                    "price: numeric price from available_products (null if no match)",
                    "currency: currency code if matched",
                    "product_unit: unit from the matched product",
                    "package_size: package size from matched product",
                    "price_type: 'DISCOUNTED', 'REGULAR', or null if no match",
                    "original_price: original price if discounted",
                    "discount_percentage: discount % if applicable",
                ],
                "matching_rules": [
                    "ONLY match if ingredient types are the SAME",
                    "Chicken matches chicken breast/meat, NOT pork",
                    "Eggs match eggs, NOT anything else",
                    "Salt matches salt, NOT 'sea salt flakes' unless it's salt",
                    "If unsure, set price to null - better no price than wrong price",
                    "Prioritize DISCOUNTED products over regular price",
                ],
                "quantity_calculation": [
                    "Sum all quantities for same ingredient across all meals",
                    "Account for waste factor (add ~10%)",
                    "Round up to practical purchase quantities",
                ],
            }
        }

        return json.dumps(prompt_data, indent=2, ensure_ascii=False)

    def _extract_ingredients_from_meal_plan(
        self,
        meal_plan: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Extract and aggregate ingredients from all meals."""
        ingredients_map = {}

        days = meal_plan.get('days', [])
        for day in days:
            for meal_type in ['breakfast', 'lunch', 'dinner', 'small_meals', 'snacks']:
                meals = day.get(meal_type)
                if not meals:
                    continue

                # Handle single meal or array of meals
                if isinstance(meals, dict):
                    meals = [meals]

                for meal in meals:
                    if not isinstance(meal, dict):
                        continue

                    for ingredient in meal.get('ingredients', []):
                        if isinstance(ingredient, dict):
                            name = ingredient.get('name', ingredient.get('ingredient', ''))
                            quantity = ingredient.get('quantity', '')
                        else:
                            name = str(ingredient)
                            quantity = ''

                        if name:
                            name_lower = name.lower().strip()
                            if name_lower not in ingredients_map:
                                ingredients_map[name_lower] = {
                                    'name': name,
                                    'occurrences': 0,
                                    'quantities': []
                                }
                            ingredients_map[name_lower]['occurrences'] += 1
                            if quantity:
                                ingredients_map[name_lower]['quantities'].append(str(quantity))

        # Convert to list
        return [
            {
                'name': data['name'],
                'occurrences': data['occurrences'],
                'sample_quantities': data['quantities'][:3]  # First 3 quantities as examples
            }
            for data in ingredients_map.values()
        ]

    def _limit_shop_data(
        self,
        shop_data: List[Dict[str, Any]],
        max_items: int = 200
    ) -> List[Dict[str, Any]]:
        """
        Limit shop data to avoid token limits.
        Prioritize discounted items.
        """
        if len(shop_data) <= max_items:
            return shop_data

        # Separate discounted and regular items
        discounted = [
            item for item in shop_data
            if item.get('price_type') == 'DISCOUNTED'
        ]
        regular = [
            item for item in shop_data
            if item.get('price_type') != 'DISCOUNTED'
        ]

        # Take all discounted, fill rest with regular
        result = discounted[:max_items]
        remaining = max_items - len(result)
        if remaining > 0:
            result.extend(regular[:remaining])

        logger.info(
            f"Limited shop data: {len(shop_data)} -> {len(result)} items "
            f"({len([i for i in result if i.get('price_type') == 'DISCOUNTED'])} discounted)"
        )

        return result

    def _post_process_shopping_list(
        self,
        shopping_list: List[Dict[str, Any]],
        goal: DietaryGoal
    ) -> List[Dict[str, Any]]:
        """Post-process shopping list to ensure correct types and defaults."""
        processed = []

        for item in shopping_list:
            processed_item = {
                'ingredient': item.get('ingredient', ''),
                'quantity': str(item.get('quantity', '')),
                'unit': item.get('unit', ''),
                'notes': item.get('notes'),
            }

            # Handle pricing
            price = item.get('price')
            if price is not None and price != '' and price != 'null':
                try:
                    processed_item['price'] = float(price)
                    processed_item['currency'] = item.get('currency', goal.currency)
                    processed_item['matched_product_name'] = item.get('matched_product_name', '')
                    processed_item['product_unit'] = item.get('product_unit', '')

                    # Handle package size
                    package_size = item.get('package_size')
                    if package_size is not None:
                        try:
                            processed_item['package_size'] = float(package_size)
                        except (ValueError, TypeError):
                            processed_item['package_size'] = None
                    else:
                        processed_item['package_size'] = None

                    # Handle price type
                    price_type = item.get('price_type')
                    if price_type in ['DISCOUNTED', 'REGULAR']:
                        processed_item['price_type'] = price_type
                    else:
                        processed_item['price_type'] = 'REGULAR'

                    # Handle discount info
                    if price_type == 'DISCOUNTED':
                        original_price = item.get('original_price')
                        if original_price:
                            try:
                                processed_item['original_price'] = float(original_price)
                            except (ValueError, TypeError):
                                pass
                        discount = item.get('discount_percentage')
                        if discount:
                            try:
                                processed_item['discount_percentage'] = int(discount)
                            except (ValueError, TypeError):
                                pass

                except (ValueError, TypeError):
                    processed_item['price'] = None
                    processed_item['price_type'] = None
            else:
                processed_item['price'] = None
                processed_item['price_type'] = None

            processed.append(processed_item)

        return processed
