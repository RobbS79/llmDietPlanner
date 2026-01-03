"""
Base scraper interface.
"""
from abc import ABC, abstractmethod
from typing import List, Dict, Any
from decimal import Decimal


class BaseScraper(ABC):
    """
    Abstract base class for leaflet scrapers.
    
    Each scraper should implement the scrape() method to return
    a list of offer dictionaries.
    """
    
    @abstractmethod
    def scrape(self) -> List[Dict[str, Any]]:
        """
        Scrape leaflet data from the source.
        
        Returns:
            List of offer dictionaries with structure:
            {
                'ingredient_name': str,  # Normalized name
                'display_name': str,     # Original name from source
                'price': Decimal,        # Optional
                'currency': str,
                'unit': str,             # Optional (kg, piece, etc.)
                'source_url': str,       # Optional
            }
            
        Raises:
            Exception: If scraping fails
        """
        pass

