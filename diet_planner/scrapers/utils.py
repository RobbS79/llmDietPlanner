"""
Utility functions for scrapers.
"""
import re


def normalize_ingredient_name(name: str) -> str:
    """
    Normalize ingredient name for matching.
    
    Converts to lowercase and removes extra whitespace.
    Can be extended with more normalization logic (diacritics, etc.)
    
    Args:
        name: Original ingredient name
        
    Returns:
        Normalized ingredient name
    """
    if not name:
        return ""
    # Convert to lowercase and strip whitespace
    normalized = name.lower().strip()
    # Replace multiple spaces with single space
    normalized = re.sub(r'\s+', ' ', normalized)
    return normalized

