"""
Shopping-list pantry classification — shared pricing primitives.

The whole-plan price-range and leaflet-deal machinery has been removed (shopping
and pricing live per-recipe now). What remains is the pure pantry-classification
decision logic: it has no DB dependency and is unit-tested directly.
"""
from typing import Optional

# Fridge basics (decision #2/#4): the "Mám doma mléko, máslo, vejce" toggle.
# Curated rather than category-derived: not all DAIRY is a basic (a recipe
# cheese is not), only plain milk/butter/eggs. Multilingual (EN/CS/SK).
FRIDGE_BASIC_NAMES = {
    'milk', 'butter', 'egg', 'eggs',
    'mléko', 'mleko', 'máslo', 'maslo', 'vejce', 'vejce m', 'vajíčko', 'vajicko',
    'mlieko', 'vajcia', 'vajíčka', 'vajicka',
}


def classify_pantry_level(ingredient_name: str, canonical) -> Optional[str]:
    """Classify an ingredient as a pantry basic, or None if it's a real buy.

    Returns 'fridge' (milk/butter/eggs), 'dry' (seeded pantry staple), or None.
    `canonical` is a CanonicalIngredient or None.
    """
    name = (ingredient_name or '').lower().strip()
    if name in FRIDGE_BASIC_NAMES:
        return 'fridge'
    if canonical is not None:
        for cand in (canonical.name, getattr(canonical, 'name_cs', ''), getattr(canonical, 'name_sk', '')):
            if cand and cand.lower().strip() in FRIDGE_BASIC_NAMES:
                return 'fridge'
        if canonical.is_pantry_staple:
            return 'dry'
    return None


def item_is_excluded(level: Optional[str], basics_on: bool, fridge_on: bool) -> bool:
    """Whether an item drops out of the basket given the pantry toggles."""
    if level == 'dry':
        return basics_on
    if level == 'fridge':
        return fridge_on
    return False
