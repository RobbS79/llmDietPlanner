"""Shared per-line cost math for the pricing paths.

Single source of truth for converting one recipe/shopping line ("qty unit")
into a cost against a price-book entry, including the piece<->weight bridge.
The per-recipe range engine calls this, so unit conversion never forks into a
second path — the fork is what produced the 238k Kč chicken
(see [[prod-pricing-fabrication-surface]]).
"""
import logging
from typing import Optional

from diet_planner.services.units import to_base

logger = logging.getLogger(__name__)

# With correct unit conversion, no real line needs more than this many packs.
MAX_PACKAGES = 50


def consumed_line_cost(entry, qty, unit, grams=None) -> Optional[float]:
    """Pro-rated cost of `qty unit` against book `entry`.

    Charges only the consumed amount (10 ml of a 1 L bottle ~ the price of
    10 ml). Bridges count<->mass via `grams` (typical piece weight) when the
    line and the book disagree on dimension. Falls back to one typical pack
    when the quantity can't be converted at all. Returns None when not
    priceable (no/zero price, missing or non-positive quantity).
    """
    if qty is None or qty <= 0:
        return None
    pack = float(entry.get('pack') or 0)
    ppu = float(entry.get('price_per_unit') or 0)
    if ppu <= 0:
        return None
    need_base, need_dim = to_base(qty, unit)
    _, book_dim = to_base(1.0, entry.get('unit', ''))
    if need_dim is not None and book_dim == need_dim:
        cost = need_base * ppu
    elif (grams and need_dim is not None and book_dim is not None
          and {need_dim, book_dim} == {'count', 'mass'}):
        # Piece<->weight bridge: recipe and book disagree on dimension.
        if book_dim == 'count':       # book per-piece, recipe in grams
            cost = (need_base / grams) * ppu
        else:                          # book per-gram, recipe in pieces
            cost = (need_base * grams) * ppu
    elif (need_dim is not None and book_dim is not None
          and {need_dim, book_dim} == {'volume', 'mass'}):
        # Volume<->mass bridge at ~1 g/ml. Rough, but fine for a labelled
        # estimate of the small seasoning/liquid amounts this covers, and far
        # better than billing a whole package.
        cost = need_base * ppu  # need_base already in ml or g; 1 g/ml
    else:
        # Can't convert the quantity to the book's unit and no bridge applies.
        # Billing a whole package for a pinch/splash is what produced absurd
        # lines (a teaspoon of salt at 185 Kc), so treat the line as
        # unpriceable ("bez ceny") instead of fabricating a pack cost.
        return None
    # Guard against absurd quantities (bad data): never charge more than a
    # sane number of packs for a single line.
    if pack > 0:
        cap = MAX_PACKAGES * pack * ppu
        if cost > cap:
            logger.warning("consumed_line_cost: capping cost for unit %s "
                           "(qty %s) at %s packs", unit, qty, MAX_PACKAGES)
            cost = cap
    return cost
