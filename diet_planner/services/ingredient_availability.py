"""Obtainability of ingredients in ordinary Czech supermarkets.

Single source of truth for the availability rollup. The recompute command,
the measurement report and the curation intake gate all call in here — none
of them reimplement the ordering.

See docs/superpowers/specs/2026-08-11-ingredient-obtainability-design.md
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from diet_planner.models.catalog import Availability, CanonicalIngredient
from diet_planner.services.canonical_lookup import resolve_canonical

# UNRATED ranks alongside FINDABLE: a rating we have not made yet must not
# behave like a known-bad ingredient (that would collapse the corpus on the
# day the migration lands). Intake uses a different rule — see BLOCKING.
_RANK = {
    Availability.COMMON: 0,
    Availability.FINDABLE: 1,
    Availability.UNRATED: 1,
    Availability.SPECIALTY: 2,
}
_BY_RANK = {
    0: Availability.COMMON,
    1: Availability.FINDABLE,
    2: Availability.SPECIALTY,
}

#: Tiers a NEW recipe may not carry. Note UNRATED is here but not in the
#: ranking penalty — the asymmetry is deliberate.
BLOCKING = {Availability.SPECIALTY, Availability.UNRATED}


def availability_index() -> Dict[str, str]:
    """slug -> availability, for bulk walks.

    Pass this to compute_shopping_difficulty when iterating the corpus;
    otherwise each ingredient costs a query.
    """
    return dict(CanonicalIngredient.objects.values_list('slug', 'availability'))


def _entry_availability(
    ing: dict, index: Optional[Dict[str, str]] = None,
) -> Tuple[str, str]:
    """(availability, blocker_key) for one ingredient dict.

    blocker_key is the canonical slug when we know it, else the raw name —
    an unresolvable ingredient still needs to be nameable in a report.
    """
    slug = ing.get('canonical')
    if slug:
        if index is not None:
            if slug in index:
                return index[slug], slug
        else:
            ci = CanonicalIngredient.objects.filter(slug=slug).first()
            if ci is not None:
                return ci.availability, ci.slug

    name = (ing.get('name') or '').strip()
    if index is None:
        ci = resolve_canonical(name)
        if ci is not None:
            return ci.availability, ci.slug
    return Availability.UNRATED, (slug or name.lower())


def _dict_entries(ingredients) -> List[dict]:
    """Non-optional ingredient dicts only.

    Generated (non-corpus) meals carry bare strings rather than dicts; those
    have no canonical to rate, so they are skipped rather than crashing.
    See normalize_ingredient_entries in canonical_lookup.
    """
    out = []
    for ing in ingredients or []:
        if not isinstance(ing, dict):
            continue
        if ing.get('optional'):
            continue
        out.append(ing)
    return out


def compute_shopping_difficulty(
    recipe, index: Optional[Dict[str, str]] = None,
) -> Tuple[str, List[str]]:
    """(shopping_difficulty, shopping_blockers) for one recipe.

    Worst non-optional ingredient wins: one un-buyable item ruins the trip as
    thoroughly as five. Never returns UNRATED — see the field's docstring.
    """
    worst = 0
    blockers = set()
    for ing in _dict_entries(recipe.ingredients):
        availability, key = _entry_availability(ing, index)
        rank = _RANK.get(availability, 1)
        if rank > 0 and key:
            blockers.add(key)
        worst = max(worst, rank)
    return _BY_RANK[worst], sorted(blockers)


def unshoppable_ingredients(
    ingredients, index: Optional[Dict[str, str]] = None,
) -> List[str]:
    """Blocker keys that disqualify a NEW recipe at intake.

    Reads ingredient tiers directly rather than the recipe rollup: the rollup
    softens UNRATED to FINDABLE, which is right for ranking and wrong here.
    """
    blocked = set()
    for ing in _dict_entries(ingredients):
        availability, key = _entry_availability(ing, index)
        if availability in BLOCKING and key:
            blocked.add(key)
    return sorted(blocked)
