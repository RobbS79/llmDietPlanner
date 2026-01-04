"""
Scraper service for managing leaflet data scraping and caching.
"""
from typing import List, Dict, Any, Optional
from datetime import timedelta
from django.utils import timezone
from django.db.models import Q
import logging

from ..models import LeafletOffer, SHOP_TO_SOURCE_URL, COUNTRY_TO_SHOPS, get_currency_for_country
from .kupi_cz import KupiCzScraper
from .rohlik_cz import RohlikCzScraper
from .kupino_sk import KupinoSkScraper
from .lunys_sk import LunysSkScraper
from .utils import normalize_ingredient_name

logger = logging.getLogger(__name__)

# Cache expiry time: 24 hours
CACHE_EXPIRY_HOURS = 24


class ScraperService:
    """
    Service for managing leaflet scraping and caching.
    
    Routes shop selection to correct scraper, checks cache validity,
    triggers scraping if needed, and stores results.
    """
    
    # Map shop codes to scraper classes
    SCRAPER_MAP = {
        'LIDL_CZ': KupiCzScraper,
        'ROHLIK': RohlikCzScraper,
        'LIDL_SK': KupinoSkScraper,
        'LUNYS': LunysSkScraper,
    }
    
    @classmethod
    def get_scraper(cls, shop: str):
        """
        Get scraper instance for a shop.
        
        Args:
            shop: Shop code (e.g., 'LIDL_CZ')
            
        Returns:
            Scraper instance
            
        Raises:
            ValueError: If shop is not supported
        """
        scraper_class = cls.SCRAPER_MAP.get(shop)
        if not scraper_class:
            raise ValueError(f"Unsupported shop: {shop}")
        return scraper_class()
    
    @classmethod
    def is_cache_valid(cls, shop: str, country: str) -> bool:
        """
        Check if cached data exists and is still valid.
        
        Args:
            shop: Shop code
            country: Country code
            
        Returns:
            True if valid cache exists, False otherwise
        """
        now = timezone.now()
        cached_count = LeafletOffer.objects.filter(
            shop=shop,
            country=country,
            expires_at__gt=now
        ).count()
        
        return cached_count > 0
    
    @classmethod
    def get_cached_offers(cls, shop: str, country: str) -> List[LeafletOffer]:
        """
        Get cached offers that are still valid.
        
        Args:
            shop: Shop code
            country: Country code
            
        Returns:
            List of LeafletOffer instances
        """
        now = timezone.now()
        return list(LeafletOffer.objects.filter(
            shop=shop,
            country=country,
            expires_at__gt=now
        ).order_by('ingredient_name'))
    
    @classmethod
    def scrape_and_store(cls, shop: str, country: str) -> List[LeafletOffer]:
        """
        Scrape leaflet data and store in database.
        
        Args:
            shop: Shop code
            country: Country code
            
        Returns:
            List of created LeafletOffer instances
        """
        logger.info(f"Scraping leaflet data for {shop} ({country})")
        
        # Get scraper instance
        scraper = cls.get_scraper(shop)
        logger.debug(f"Using scraper class: {type(scraper).__name__}")
        
        # Scrape data
        try:
            offers_data = scraper.scrape()
            logger.info(f"Scraper returned {len(offers_data)} raw offers for {shop} ({country})")
            
            # Log sample of scraped data for debugging
            if offers_data:
                logger.debug(f"Sample scraped offer: {offers_data[0]}")
            else:
                logger.warning(f"No offers scraped from {shop} ({country}) - scraper returned empty list")
        except Exception as e:
            logger.error(f"Error scraping {shop} ({country}): {e}", exc_info=True)
            raise
        
        # Delete old expired offers for this shop/country
        now = timezone.now()
        deleted_count = LeafletOffer.objects.filter(
            shop=shop,
            country=country
        ).filter(
            Q(expires_at__lte=now) | Q(expires_at__isnull=True)
        ).delete()[0]
        logger.debug(f"Deleted {deleted_count} expired offers for {shop} ({country})")
        
        # Calculate expiry time
        expires_at = now + timedelta(hours=CACHE_EXPIRY_HOURS)
        currency = get_currency_for_country(country)
        logger.debug(f"Using currency {currency} for {country}, expiry time: {expires_at}")
        
        # Store offers
        created_offers = []
        skipped_count = 0
        for idx, offer_data in enumerate(offers_data):
            # Normalize ingredient name
            raw_name = offer_data.get('ingredient_name') or offer_data.get('display_name', '')
            ingredient_name = normalize_ingredient_name(raw_name)
            
            if not ingredient_name:
                logger.warning(f"Skipping offer #{idx} with empty ingredient name: {offer_data}")
                skipped_count += 1
                continue
            
            # Truncate names to fit database field (database has max_length=200, not 255)
            # Truncate display name
            display_name = offer_data.get('display_name', ingredient_name)
            if len(display_name) > 200:
                display_name = display_name[:200]
                logger.debug(f"Truncated display_name from {len(offer_data.get('display_name', ''))} to 200 chars")
            
            # Truncate ingredient_name if needed
            if len(ingredient_name) > 200:
                ingredient_name = ingredient_name[:200]
                logger.debug(f"Truncated ingredient_name from {len(raw_name)} to 200 chars")
            
            # Validate price if present
            price = offer_data.get('price')
            if price is not None:
                try:
                    from decimal import Decimal, InvalidOperation
                    if isinstance(price, (int, float, str)):
                        price = Decimal(str(price))
                    elif not isinstance(price, Decimal):
                        logger.warning(f"Invalid price type for offer #{idx} ({ingredient_name}): {type(price)}")
                        price = None
                except (ValueError, InvalidOperation) as e:
                    logger.warning(f"Invalid price value for offer #{idx} ({ingredient_name}): {offer_data.get('price')} - {e}")
                    price = None
            
            try:
                offer = LeafletOffer.objects.create(
                    shop=shop,
                    country=country,
                    ingredient_name=ingredient_name,
                    display_name=display_name,
                    price=price,
                    currency=offer_data.get('currency', currency),
                    unit=offer_data.get('unit'),
                    expires_at=expires_at,
                    source_url=offer_data.get('source_url'),
                )
                created_offers.append(offer)
                logger.debug(f"Stored offer #{idx}: {ingredient_name} - {price} {offer_data.get('currency', currency)}")
            except Exception as e:
                logger.error(f"Error storing offer #{idx} ({ingredient_name}): {e}", exc_info=True)
                skipped_count += 1
        
        logger.info(f"Stored {len(created_offers)} offers for {shop} ({country}), skipped {skipped_count}")
        return created_offers
    
    @classmethod
    def get_available_ingredients(cls, shop: str, country: str, force_refresh: bool = False) -> List[Dict[str, Any]]:
        """
        Get available ingredients for a shop/country.
        
        Checks cache first, scrapes if needed.
        
        Args:
            shop: Shop code
            country: Country code
            force_refresh: If True, force re-scraping even if cache is valid
            
        Returns:
            List of ingredient dictionaries with 'name' and 'display_name'
        """
        # Check cache
        if not force_refresh and cls.is_cache_valid(shop, country):
            logger.info(f"Using cached offers for {shop} ({country})")
            offers = cls.get_cached_offers(shop, country)
        else:
            # Scrape and store
            offers = cls.scrape_and_store(shop, country)
        
        # Convert to list of dictionaries for LLM prompt
        ingredients = []
        for offer in offers:
            ingredients.append({
                'name': offer.ingredient_name,
                'display_name': offer.display_name,
            })
        
        return ingredients
    
    @classmethod
    def match_ingredient_price(cls, ingredient_name: str, shop: str, country: str) -> Optional[Dict[str, Any]]:
        """
        Match an ingredient name with a price from LeafletOffer.
        
        Uses multiple matching strategies:
        1. Exact match on normalized name
        2. Partial match (scraped name contains search term)
        3. Reverse partial match (search term contains scraped name)
        
        Args:
            ingredient_name: Normalized ingredient name to match
            shop: Shop code
            country: Country code
            
        Returns:
            Dict with price info or None if not found:
            {
                'price': Decimal,
                'currency': str,
                'unit': str,
                'display_name': str,
            }
        """
        from django.utils import timezone
        from decimal import Decimal
        from django.db.models import Q
        
        normalized_name = normalize_ingredient_name(ingredient_name)
        logger.debug(f"Matching ingredient: '{ingredient_name}' (normalized: '{normalized_name}') for {shop} ({country})")
        
        if not normalized_name:
            logger.warning(f"Empty normalized name for ingredient: '{ingredient_name}'")
            return None
        
        current_time = timezone.now()
        
        # Strategy 1: Exact match on normalized name
        offer = LeafletOffer.objects.filter(
            shop=shop,
            country=country,
            ingredient_name=normalized_name,
            expires_at__gt=current_time,
            price__isnull=False
        ).order_by('-scraped_at').first()
        
        if offer:
            logger.debug(f"Found exact price match: {offer.display_name} - {offer.price} {offer.currency}")
            return {
                'price': Decimal(str(offer.price)),
                'currency': offer.currency,
                'unit': offer.unit or '',
                'display_name': offer.display_name,
            }
        
        # Strategy 2: Partial match - scraped ingredient_name contains the search term
        # E.g., search "rajčata" matches "rajčata cherry" or "rajčata červená"
        offer = LeafletOffer.objects.filter(
            shop=shop,
            country=country,
            ingredient_name__icontains=normalized_name,
            expires_at__gt=current_time,
            price__isnull=False
        ).order_by('-scraped_at').first()
        
        if offer:
            logger.debug(f"Found partial price match (scraped contains search): {offer.display_name} - {offer.price} {offer.currency}")
            return {
                'price': Decimal(str(offer.price)),
                'currency': offer.currency,
                'unit': offer.unit or '',
                'display_name': offer.display_name,
            }
        
        # Strategy 3: Reverse partial match - search term contains scraped ingredient_name
        # E.g., search "rajčata cherry" matches "rajčata"
        # We need to filter in Python since Django doesn't support this in the ORM efficiently
        # But for performance, we'll limit the query first
        candidates = LeafletOffer.objects.filter(
            shop=shop,
            country=country,
            expires_at__gt=current_time,
            price__isnull=False
        ).order_by('-scraped_at')[:100]  # Limit to recent offers for performance
        
        for candidate in candidates:
            if normalized_name.startswith(candidate.ingredient_name) or candidate.ingredient_name.startswith(normalized_name):
                # Additional check: ensure significant overlap (at least 3 characters)
                if len(normalized_name) >= 3 and len(candidate.ingredient_name) >= 3:
                    logger.debug(f"Found reverse partial price match: {candidate.display_name} - {candidate.price} {candidate.currency}")
                    return {
                        'price': Decimal(str(candidate.price)),
                        'currency': candidate.currency,
                        'unit': candidate.unit or '',
                        'display_name': candidate.display_name,
                    }
        
        logger.debug(f"No price match found for '{ingredient_name}' in {shop} ({country})")
        return None
    
    @classmethod
    def match_shopping_list_prices(cls, shopping_list: List[Dict[str, Any]], shop: str, country: str) -> List[Dict[str, Any]]:
        """
        Match shopping list items with prices from LeafletOffer.
        
        Args:
            shopping_list: List of shopping list items (from LLM)
            shop: Shop code
            country: Country code
            
        Returns:
            List of shopping list items with price information added
        """
        logger.info(f"Matching prices for {len(shopping_list)} shopping list items from {shop} ({country})")
        
        # Check if we have any offers in the database first
        current_time = timezone.now()
        total_offers = LeafletOffer.objects.filter(
            shop=shop,
            country=country,
            expires_at__gt=current_time,
            price__isnull=False
        ).count()
        logger.info(f"Found {total_offers} valid offers with prices in database for {shop} ({country})")
        
        if total_offers == 0:
            logger.warning(f"No offers found in database for {shop} ({country}) - scraping may have failed or returned no data")
        
        enhanced_list = []
        matched_count = 0
        unmatched_items = []
        
        for item in shopping_list:
            ingredient_name = item.get('ingredient', '')
            if ingredient_name:
                price_info = cls.match_ingredient_price(ingredient_name, shop, country)
                if price_info:
                    item['price'] = price_info['price']
                    item['currency'] = price_info['currency']
                    item['offer_unit'] = price_info['unit']
                    item['offer_display_name'] = price_info['display_name']
                    matched_count += 1
                    logger.debug(f"✓ Matched '{ingredient_name}' -> '{price_info['display_name']}' ({price_info['price']} {price_info['currency']})")
                else:
                    # No price found, mark as unavailable
                    item['price'] = None
                    item['currency'] = get_currency_for_country(country)
                    item['offer_unit'] = None
                    item['offer_display_name'] = None
                    unmatched_items.append(ingredient_name)
                    logger.debug(f"✗ No match found for '{ingredient_name}'")
            else:
                logger.warning(f"Shopping list item missing ingredient name: {item}")
                item['price'] = None
                item['currency'] = get_currency_for_country(country)
                item['offer_unit'] = None
                item['offer_display_name'] = None
            enhanced_list.append(item)
        
        logger.info(f"Matched {matched_count}/{len(shopping_list)} items with prices from {shop} ({country})")
        if unmatched_items:
            logger.info(f"Unmatched items: {', '.join(unmatched_items[:10])}{'...' if len(unmatched_items) > 10 else ''}")
        return enhanced_list

