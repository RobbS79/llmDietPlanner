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
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import re

logger = logging.getLogger(__name__)

# Lazy import for LLM service to avoid circular dependencies
def get_llm_service():
    """Get LLM service instance with lazy loading."""
    try:
        from ..llm_service import OpenAIService
        return OpenAIService()
    except Exception as e:
        logger.error(f"Failed to import/initialize LLM service: {e}", exc_info=True)
        raise

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
    def _get_shop_urls(cls, shop: str, country: str) -> List[str]:
        """
        Get the base URLs to scrape for a shop.
        
        Args:
            shop: Shop code
            country: Country code
            
        Returns:
            List of URLs to scrape (for shops with multiple leaflet pages, returns listing page)
        """
        url_map = {
            'LIDL_CZ': 'https://www.kupi.cz/letaky/lidl',
            'ROHLIK': 'https://www.rohlik.cz/cs/akcni-nabidka',
            'LIDL_SK': 'https://kupino.sk/lidl',
            'LUNYS': 'https://lunys.sk/akcie',
        }
        
        base_url = url_map.get(shop)
        if not base_url:
            raise ValueError(f"Unknown shop: {shop}")
        
        return [base_url]
    
    @classmethod
    def _extract_leaflet_urls(cls, html_content: str, base_url: str, shop: str) -> List[str]:
        """
        Extract leaflet page URLs from a listing page.
        
        Args:
            html_content: HTML content of the listing page
            base_url: Base URL of the listing page
            shop: Shop code
            
        Returns:
            List of leaflet page URLs
        """
        leaflet_urls = []
        
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            
            if shop == 'LIDL_CZ':
                # Look for links matching /letak/lidl-*
                for link in soup.find_all('a', href=True):
                    href = link.get('href', '')
                    if href.startswith('/letak/lidl-') or href.startswith('https://www.kupi.cz/letak/lidl-'):
                        full_url = urljoin(base_url, href)
                        if full_url not in leaflet_urls:
                            leaflet_urls.append(full_url)
            elif shop == 'LIDL_SK':
                # Similar pattern for kupino.sk
                for link in soup.find_all('a', href=True):
                    href = link.get('href', '')
                    if '/letak/' in href or '/lidl-' in href:
                        full_url = urljoin(base_url, href)
                        if full_url not in leaflet_urls:
                            leaflet_urls.append(full_url)
            
            logger.debug(f"Extracted {len(leaflet_urls)} leaflet URLs for {shop}")
        except Exception as e:
            logger.error(f"Error extracting leaflet URLs: {e}", exc_info=True)
        
        return leaflet_urls
    
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
            List of LeafletOffer instances (with prices)
        """
        now = timezone.now()
        return list(LeafletOffer.objects.filter(
            shop=shop,
            country=country,
            expires_at__gt=now,
            price__isnull=False,  # Only return offers with prices
            price__gt=0  # Only return offers with positive prices (exclude zero)
        ).order_by('ingredient_name'))
    
    @classmethod
    def scrape_and_store(cls, shop: str, country: str) -> List[LeafletOffer]:
        """
        Scrape leaflet data using LLM extraction and store in database.
        
        Args:
            shop: Shop code
            country: Country code
            
        Returns:
            List of created LeafletOffer instances
        """
        logger.info(f"Scraping leaflet data for {shop} ({country}) using LLM extraction")
        
        # Get URLs to scrape
        try:
            base_urls = cls._get_shop_urls(shop, country)
        except Exception as e:
            logger.error(f"Error getting shop URLs for {shop}: {e}", exc_info=True)
            raise
        
        # Fetch HTML and extract products using LLM
        offers_data = []
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        # Get LLM service with error handling
        try:
            llm_service = get_llm_service()
        except Exception as e:
            logger.error(f"Failed to initialize LLM service: {e}", exc_info=True)
            raise ValueError(f"LLM service initialization failed: {e}") from e
        
        # Determine which shops need leaflet navigation
        shops_with_leaflets = ['LIDL_CZ', 'LIDL_SK']
        
        for base_url in base_urls:
            try:
                # Fetch HTML from base URL
                logger.info(f"Fetching HTML from {base_url}")
                response = requests.get(base_url, headers=headers, timeout=10)
                response.raise_for_status()
                response.encoding = 'utf-8'
                html_content = response.text
                
                # For shops with multiple leaflet pages, extract leaflet URLs
                if shop in shops_with_leaflets:
                    leaflet_urls = cls._extract_leaflet_urls(html_content, base_url, shop)
                    
                    if leaflet_urls:
                        # Scrape only the first (current) leaflet for now
                        leaflet_url = leaflet_urls[0]
                        logger.info(f"Scraping leaflet page: {leaflet_url}")
                        
                        # Fetch leaflet page HTML
                        leaflet_response = requests.get(leaflet_url, headers=headers, timeout=10)
                        leaflet_response.raise_for_status()
                        leaflet_response.encoding = 'utf-8'
                        leaflet_html = leaflet_response.text
                        
                        # Extract products from leaflet page using LLM
                        products = llm_service.extract_products_from_html(
                            html_content=leaflet_html,
                            url=leaflet_url,
                            shop=shop,
                            country=country
                        )
                        offers_data.extend(products)
                    else:
                        # Fallback: try extracting from listing page
                        logger.warning(f"No leaflet URLs found, trying to extract from listing page")
                        products = llm_service.extract_products_from_html(
                            html_content=html_content,
                            url=base_url,
                            shop=shop,
                            country=country
                        )
                        offers_data.extend(products)
                else:
                    # For shops with single page (rohlik.cz, lunys.sk), extract directly
                    products = llm_service.extract_products_from_html(
                        html_content=html_content,
                        url=base_url,
                        shop=shop,
                        country=country
                    )
                    offers_data.extend(products)
                    
            except requests.RequestException as e:
                logger.error(f"Error fetching {base_url}: {e}", exc_info=True)
                continue
            except Exception as e:
                logger.error(f"Error extracting products from {base_url}: {e}", exc_info=True)
                continue
        
        logger.info(f"LLM extraction returned {len(offers_data)} raw offers for {shop} ({country})")
        
        if not offers_data:
            logger.warning(f"No offers extracted from {shop} ({country}) - LLM returned empty list")
        
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
            
            # Validate price if present - must be positive (> 0)
            price = offer_data.get('price')
            if price is not None:
                try:
                    from decimal import Decimal, InvalidOperation
                    if isinstance(price, (int, float, str)):
                        price = Decimal(str(price))
                    elif not isinstance(price, Decimal):
                        logger.warning(f"Invalid price type for offer #{idx} ({ingredient_name}): {type(price)}")
                        price = None
                    # Filter out zero or negative prices
                    if price is not None and price <= 0:
                        logger.debug(f"Skipping offer #{idx} ({ingredient_name}) with invalid price: {price}")
                        price = None
                except (ValueError, InvalidOperation) as e:
                    logger.warning(f"Invalid price value for offer #{idx} ({ingredient_name}): {offer_data.get('price')} - {e}")
                    price = None
            
            try:
                # Use update_or_create to handle duplicates
                offer, created = LeafletOffer.objects.update_or_create(
                    shop=shop,
                    country=country,
                    ingredient_name=ingredient_name,
                    defaults={
                        'display_name': display_name,
                        'price': price,
                        'currency': offer_data.get('currency', currency),
                        'unit': offer_data.get('unit'),
                        'expires_at': expires_at,
                        'source_url': offer_data.get('source_url'),
                        'scraped_at': timezone.now(),
                    }
                )
                created_offers.append(offer)
                if created:
                    logger.debug(f"Created offer #{idx}: {ingredient_name} - {price} {offer_data.get('currency', currency)}")
                else:
                    logger.debug(f"Updated offer #{idx}: {ingredient_name} - {price} {offer_data.get('currency', currency)}")
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
            List of ingredient dictionaries with 'name', 'display_name', 'price', 'currency', 'unit'
        """
        # Check cache
        if not force_refresh and cls.is_cache_valid(shop, country):
            logger.info(f"Using cached offers for {shop} ({country})")
            offers = cls.get_cached_offers(shop, country)
        else:
            # Scrape and store - wrap in try/except to prevent failures from breaking the request
            try:
                offers = cls.scrape_and_store(shop, country)
            except Exception as e:
                logger.error(f"Error scraping {shop} ({country}): {e}", exc_info=True)
                # Return cached offers if available, even if expired, rather than failing completely
                logger.warning(f"Falling back to expired cache for {shop} ({country})")
                offers = cls.get_cached_offers(shop, country)  # This might return empty list if no cache
        
        # Convert to list of dictionaries for LLM prompt (only include offers with positive prices)
        ingredients = []
        for offer in offers:
            # Only include offers that have positive prices (filter out None and 0)
            if offer.price is not None and offer.price > 0:
                # Try to extract package_size from display_name if not stored in DB
                package_size = None
                display_name = offer.display_name or ''
                if display_name:
                    # Pattern: number + unit (e.g., "10 ks", "500 g", "1kg")
                    patterns = [
                        r'(\d+[\.,]?\d*)\s*(ks|piece|pieces|pcs|pc|bal|balíček)',  # Pieces
                        r'(\d+[\.,]?\d*)\s*(kg|kilogram)',  # Kilograms  
                        r'(\d+[\.,]?\d*)\s*(g|gram)',  # Grams
                        r'(\d+[\.,]?\d*)\s*(l|litre|liter)',  # Liters
                        r'(\d+[\.,]?\d*)\s*(ml|millilitre|milliliter)',  # Milliliters
                    ]
                    for pattern in patterns:
                        match = re.search(pattern, display_name, re.I)
                        if match:
                            try:
                                size_str = match.group(1).replace(',', '.')
                                package_size = float(size_str)
                                break
                            except (ValueError, Exception):
                                continue
                
                ingredients.append({
                    'name': offer.ingredient_name,
                    'display_name': offer.display_name,
                    'price': float(offer.price),
                    'currency': offer.currency,
                    'unit': offer.unit or '',
                    'package_size': package_size,  # Include package_size if detected
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
            price__isnull=False,
            price__gt=0  # Only match offers with positive prices
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
            price__isnull=False,
            price__gt=0  # Only match offers with positive prices
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
            price__isnull=False,
            price__gt=0  # Only match offers with positive prices
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
            price__isnull=False,
            price__gt=0  # Only count offers with positive prices
        ).count()
        logger.info(f"Found {total_offers} valid offers with prices in database for {shop} ({country})")
        
        if total_offers == 0:
            logger.warning(f"No offers found in database for {shop} ({country}) - scraping may have failed or returned no data")
        else:
            # Log sample of available ingredient names from database
            sample_offers = LeafletOffer.objects.filter(
                shop=shop,
                country=country,
                expires_at__gt=current_time,
                price__isnull=False,
                price__gt=0  # Only include offers with positive prices
            ).values_list('ingredient_name', 'display_name')[:10]
            sample_names = [name for name, _ in sample_offers]
            logger.info(f"Sample ingredient names from database (first 10): {sample_names}")
        
        # Log sample of shopping list ingredient names
        shopping_list_ingredients = [item.get('ingredient', '') for item in shopping_list[:10] if item.get('ingredient')]
        logger.info(f"Sample shopping list ingredient names (first 10): {shopping_list_ingredients}")
        
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
            logger.info(f"Unmatched items (first 10): {', '.join(unmatched_items[:10])}{'...' if len(unmatched_items) > 10 else ''}")
            logger.debug(f"All unmatched items ({len(unmatched_items)} total): {unmatched_items}")
        return enhanced_list

