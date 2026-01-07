"""
Price Discovery Service - Handles price estimation for missing ingredients.
Uses OpenAI LLM for batch price estimation when items aren't found in scraped data.
"""
import json
import logging
from typing import List, Dict, Any, Optional
from decimal import Decimal
from dataclasses import dataclass

from django.conf import settings
import openai

from diet_planner.models import DietaryGoal, LeafletOffer

logger = logging.getLogger(__name__)


@dataclass
class PriceEstimate:
    """Result of a price estimation."""
    ingredient: str
    quantity: str
    price: Decimal
    currency: str
    confidence: str  # 'high', 'medium', 'low'
    reasoning: str
    typical_unit: str


class PriceDiscoveryService:
    """
    Service for discovering/estimating prices of ingredients.
    Primary source: LeafletOffer database (scraped data)
    Fallback: OpenAI LLM estimation based on location context
    """

    def __init__(self, goal: DietaryGoal):
        """
        Initialize the service with a dietary goal for context.

        Args:
            goal: The DietaryGoal being processed (provides country, city, shop context)
        """
        self.goal = goal
        self.country = goal.country
        self.city = goal.city
        self.shop = goal.shop
        self.currency = goal.currency

        # Initialize OpenAI client
        self.client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)
        self.model = getattr(settings, 'OPENAI_MODEL', 'gpt-4o-mini')

    def fill_missing_prices(self, shopping_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Fill in prices for items that don't have them.
        First tries database lookup, then falls back to LLM estimation.

        Args:
            shopping_list: List of shopping items with ingredient, quantity, optional price

        Returns:
            Updated shopping list with prices filled in
        """
        items_needing_prices = []
        items_with_indices = []

        for i, item in enumerate(shopping_list):
            # Skip items that already have a price
            if item.get('price') and float(item.get('price', 0)) > 0:
                # Ensure price_type is set
                if 'price_type' not in item:
                    item['price_type'] = 'REGULAR'
                continue

            # Try to find in database first
            db_price = self._lookup_price_in_db(item.get('ingredient', ''))

            if db_price:
                item['price'] = float(db_price['price'])
                item['currency'] = db_price['currency']
                item['price_type'] = db_price['price_type']
                if db_price.get('original_price'):
                    item['original_price'] = float(db_price['original_price'])
                if db_price.get('discount_percentage'):
                    item['discount_percentage'] = db_price['discount_percentage']
                item['source'] = 'database'
            else:
                # Need LLM estimation
                items_needing_prices.append({
                    'ingredient': item.get('ingredient', ''),
                    'quantity': item.get('quantity', ''),
                })
                items_with_indices.append(i)

        # Batch estimate missing prices
        if items_needing_prices:
            logger.info(f"Estimating prices for {len(items_needing_prices)} items via LLM")
            estimates = self._batch_estimate_prices(items_needing_prices)

            for idx, estimate in zip(items_with_indices, estimates):
                if estimate:
                    shopping_list[idx]['price'] = float(estimate.price)
                    shopping_list[idx]['currency'] = estimate.currency
                    shopping_list[idx]['price_type'] = 'LLM_ESTIMATED'
                    shopping_list[idx]['price_confidence'] = estimate.confidence
                    shopping_list[idx]['source'] = 'llm_estimate'
                else:
                    # Failed to estimate - mark as unavailable
                    shopping_list[idx]['price'] = None
                    shopping_list[idx]['price_type'] = 'UNAVAILABLE'
                    shopping_list[idx]['source'] = 'none'

        return shopping_list

    def _lookup_price_in_db(self, ingredient: str) -> Optional[Dict[str, Any]]:
        """
        Look up ingredient price in the LeafletOffer database.

        Args:
            ingredient: Ingredient name to look up

        Returns:
            Dict with price info or None if not found
        """
        if not ingredient:
            return None

        from django.utils import timezone

        # Normalize ingredient name
        normalized = ingredient.lower().strip()

        # Look for active (non-expired) offers
        offer = LeafletOffer.objects.filter(
            ingredient_name__icontains=normalized,
            shop=self.shop,
            country=self.country,
            expires_at__gt=timezone.now()
        ).order_by('-scraped_at').first()

        if offer:
            return {
                'price': offer.price,
                'currency': offer.currency,
                'price_type': offer.price_type,
                'original_price': offer.original_price,
                'discount_percentage': offer.discount_percentage,
            }

        # Try broader search without shop filter
        offer = LeafletOffer.objects.filter(
            ingredient_name__icontains=normalized,
            country=self.country,
            expires_at__gt=timezone.now()
        ).order_by('-scraped_at').first()

        if offer:
            return {
                'price': offer.price,
                'currency': offer.currency,
                'price_type': offer.price_type,
                'original_price': offer.original_price,
                'discount_percentage': offer.discount_percentage,
            }

        return None

    def _batch_estimate_prices(self, items: List[Dict[str, str]]) -> List[Optional[PriceEstimate]]:
        """
        Estimate prices for multiple items in a single LLM call.

        Args:
            items: List of dicts with 'ingredient' and 'quantity' keys

        Returns:
            List of PriceEstimate objects (or None for failed estimates)
        """
        if not items:
            return []

        # Build the prompt
        shop_description = self._get_shop_description()

        prompt = f"""You are a grocery price estimator for {self.country}.

Context:
- Location: {self.city}, {self.country}
- Store type: {self.shop} ({shop_description})
- Currency: {self.currency}
- Date: Today

Task: Estimate retail prices for the following grocery items.

Items to estimate:
{json.dumps(items, indent=2)}

For each item, consider:
1. Local purchasing power in {self.country}
2. Store positioning ({shop_description})
3. Typical package sizes available
4. Current season and availability

Return a JSON array with one object per item:
[
  {{
    "ingredient": "item name",
    "estimated_price": <number>,
    "currency": "{self.currency}",
    "confidence": "high" | "medium" | "low",
    "reasoning": "brief explanation",
    "typical_unit": "package size, e.g., 500g, 1L"
  }}
]

Important:
- Return ONLY valid JSON, no markdown formatting
- Prices should be realistic for the specified country and store type
- Use the specified currency ({self.currency})
"""

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a helpful assistant that estimates grocery prices. Always respond with valid JSON."
                    },
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,  # Lower temperature for more consistent prices
                max_tokens=2000
            )

            content = response.choices[0].message.content.strip()

            # Clean up potential markdown formatting
            if content.startswith('```'):
                content = content.split('```')[1]
                if content.startswith('json'):
                    content = content[4:]
                content = content.strip()

            estimates_data = json.loads(content)

            results = []
            for data in estimates_data:
                try:
                    estimate = PriceEstimate(
                        ingredient=data.get('ingredient', ''),
                        quantity='',  # Not returned by LLM
                        price=Decimal(str(data.get('estimated_price', 0))),
                        currency=data.get('currency', self.currency),
                        confidence=data.get('confidence', 'medium'),
                        reasoning=data.get('reasoning', ''),
                        typical_unit=data.get('typical_unit', '')
                    )
                    results.append(estimate)
                except Exception as e:
                    logger.warning(f"Failed to parse price estimate: {e}")
                    results.append(None)

            # Pad with None if fewer results than items
            while len(results) < len(items):
                results.append(None)

            return results

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM response as JSON: {e}")
            return [None] * len(items)
        except Exception as e:
            logger.exception(f"LLM price estimation failed: {e}")
            return [None] * len(items)

    def _get_shop_description(self) -> str:
        """Get a human-readable description of the shop type."""
        shop_descriptions = {
            'LIDL_CZ': 'Lidl - German discount supermarket chain',
            'LIDL_SK': 'Lidl - German discount supermarket chain',
            'ROHLIK': 'Rohlik.cz - Premium online grocery delivery',
            'LUNYS': 'Lunys.sk - Slovak online grocery store',
        }
        return shop_descriptions.get(self.shop, 'general supermarket')

    def estimate_single_price(self, ingredient: str, quantity: str = '') -> Optional[PriceEstimate]:
        """
        Estimate price for a single ingredient.

        Args:
            ingredient: Ingredient name
            quantity: Optional quantity string

        Returns:
            PriceEstimate or None
        """
        results = self._batch_estimate_prices([{
            'ingredient': ingredient,
            'quantity': quantity
        }])
        return results[0] if results else None
