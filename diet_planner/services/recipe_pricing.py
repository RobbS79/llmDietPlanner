"""Per-recipe from-to price range from the static price book.

Low end = sum of consumed ingredient costs (the food actually in the dish).
High end = low * PACK_OVERHEAD, the measured consumed->till overhead. The range
is pantry-agnostic (counts staples): a recipe viewer wants "what this dish
costs", not "assuming you own oil". See
docs/superpowers/specs/2026-06-22-recipe-price-range-design.md.
"""
from dataclasses import dataclass
from typing import Optional

from diet_planner.services.canonical_lookup import resolve_canonical
from diet_planner.services.estimate_pricer import _FX_FROM_CZK, _load_book
from diet_planner.services.piece_weights import load_piece_weights
from diet_planner.services.pricing_core import consumed_line_cost

# Measured consumed->till overhead (see spec eval). Tune from real-spend feedback.
PACK_OVERHEAD = 1.25
# Below this priced-ingredient fraction the range is too thin to show confidently.
COVERAGE_MIN = 0.6


@dataclass(frozen=True)
class RecipeRange:
    low: float
    high: float
    per_portion_low: Optional[float]
    per_portion_high: Optional[float]
    currency: str
    priced_count: int
    total_count: int
    confident: bool


def _num(v) -> Optional[float]:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _fx(currency: str, book_currency: str) -> float:
    if currency == book_currency:
        return 1.0
    return _FX_FROM_CZK.get(currency, 1.0)


def price_recipe(ingredients, servings, *, currency='CZK', book=None) -> Optional[RecipeRange]:
    """Return a RecipeRange for `ingredients`, or None if nothing prices.

    `ingredients`: [{name, quantity, unit, canonical?, optional?}].
    `book`: optional injected price map (defaults to the loaded book) — for tests.
    """
    if not ingredients:
        return None
    data = _load_book()
    prices = book if book is not None else data['prices']
    book_currency = data.get('currency', 'CZK')
    weights = load_piece_weights()

    low = 0.0
    priced = total = 0
    for ingredient in ingredients:
        if ingredient.get('optional'):
            continue
        total += 1
        slug = ingredient.get('canonical')
        if not slug:
            name = (ingredient.get('name') or '').strip()
            canonical = resolve_canonical(name) if name else None
            slug = canonical.slug if canonical else None
        entry = prices.get(slug) if slug else None
        if not entry:
            continue
        cost = consumed_line_cost(entry, _num(ingredient.get('quantity')),
                                  ingredient.get('unit', ''), weights.get(slug))
        if cost is None:
            continue
        low += cost
        priced += 1

    if priced == 0:
        return None
    low *= _fx(currency, book_currency)
    high = low * PACK_OVERHEAD
    per_portion_low = per_portion_high = None
    if isinstance(servings, int) and servings > 0:
        per_portion_low = low / servings
        per_portion_high = high / servings
    confident = total > 0 and (priced / total) >= COVERAGE_MIN
    return RecipeRange(low, high, per_portion_low, per_portion_high,
                       currency, priced, total, confident)
