"""
Unit normalisation and base-unit conversion for pricing.

One shared converter so every pricing path (catalog resolver, static price-book
estimator) divides quantities the same way. Mixing a gram requirement with a
kilogram pack size without converting is what produced the 238k Kč chicken
(see [[prod-pricing-fabrication-surface]]); keeping the conversion in one place
keeps that from regressing in a second code path.

Base unit per measurement dimension: mass→g, volume→ml, count→ks.
"""
from typing import Optional, Tuple

# Multilingual (CZ/SK/PL/EN) unit spellings → canonical code.
_UNIT_ALIASES = {
    'kg': 'kg', 'kilogram': 'kg', 'kilogramy': 'kg', 'kilogramů': 'kg',
    'kilogramow': 'kg', 'kg.': 'kg',
    'g': 'g', 'gram': 'g', 'gramy': 'g', 'gramů': 'g', 'gramow': 'g', 'g.': 'g',
    'dkg': 'dkg', 'dag': 'dkg',  # deka (10 g), common in CZ recipes
    'l': 'l', 'litr': 'l', 'litry': 'l', 'litrů': 'l', 'litrow': 'l',
    'liter': 'l', 'litre': 'l', 'l.': 'l',
    'ml': 'ml', 'mililitr': 'ml', 'mililitry': 'ml', 'mililitrů': 'ml',
    'milliliter': 'ml', 'millilitre': 'ml', 'ml.': 'ml',
    'ks': 'ks', 'kus': 'ks', 'kusy': 'ks', 'kusů': 'ks', 'kusow': 'ks',
    'piece': 'ks', 'pieces': 'ks', 'pcs': 'ks', 'pc': 'ks', 'szt': 'ks',
    'sztuk': 'ks', 'sztuki': 'ks',
    # Cooking volume units (CZ/SK/EN) -> ml. Recipes routinely give seasonings
    # and liquids in spoons/cups; without these they used to fall back to a
    # whole package (a teaspoon of salt priced as a 250 g packet).
    'lžička': 'tsp', 'lžičky': 'tsp', 'lžiček': 'tsp', 'čl': 'tsp',
    'čajová lžička': 'tsp', 'lyzicka': 'tsp', 'tsp': 'tsp', 'teaspoon': 'tsp',
    'lžíce': 'tbsp', 'lžic': 'tbsp', 'pl': 'tbsp', 'polévková lžíce': 'tbsp',
    'lzice': 'tbsp', 'tbsp': 'tbsp', 'tablespoon': 'tbsp', 'polevkova lzice': 'tbsp',
    'hrnek': 'cup', 'hrnky': 'cup', 'hrnků': 'cup', 'hrnku': 'cup',
    'šálek': 'cup', 'šálky': 'cup', 'salek': 'cup', 'cup': 'cup', 'cups': 'cup',
    'dl': 'dl', 'deci': 'dl', 'decilitr': 'dl', 'decilitry': 'dl',
    'špetka': 'pinch', 'špetky': 'pinch', 'spetka': 'pinch',
}

# code → (dimension, factor to base unit). Base: mass→g, volume→ml, count→ks.
_TO_BASE = {
    'g': ('mass', 1.0), 'dkg': ('mass', 10.0), 'kg': ('mass', 1000.0),
    'ml': ('volume', 1.0), 'l': ('volume', 1000.0),
    'tsp': ('volume', 5.0), 'tbsp': ('volume', 15.0), 'cup': ('volume', 250.0),
    'dl': ('volume', 100.0), 'pinch': ('volume', 0.3),
    'ks': ('count', 1.0),
}


def normalize_unit(unit: str) -> str:
    """Standardise a unit string to a canonical code (g/kg/ml/l/ks/dkg)."""
    if not unit:
        return ''
    return _UNIT_ALIASES.get(str(unit).lower().strip(), str(unit).lower().strip())


def to_base(value: float, unit: str) -> Tuple[float, Optional[str]]:
    """Return (base_value, dimension) for a quantity.

    dimension is 'mass' | 'volume' | 'count', or None when the unit is unknown
    or empty so callers can detect an unconvertible quantity instead of dividing
    incomparable units.
    """
    entry = _TO_BASE.get(normalize_unit(unit))
    if entry is None:
        return value, None
    dim, factor = entry
    return value * factor, dim
