"""Human-readable display names for recipe ingredients.

Catalog-constrained generation feeds the LLM catalog product strings shaped
`{brand} {name} (#{store_product_id})` (the id lets pricing round-trip), and the
model echoes them back verbatim as a meal's ingredients. Cached onto a public
`Recipe`, that internal string leaked to the /recepty page, the SSR HTML, and
the recipeIngredient JSON-LD.

`display_ingredient_name` converts one such string to the clean canonical name
(`pappudia tofu (#2153)` -> `tofu`); anything without the `(#id)` marker is a
name the recipe author already wrote and is returned untouched.
"""
from __future__ import annotations

import re
from typing import Any, Optional

from diet_planner.services.canonical_lookup import resolve_canonical

#: The internal catalog annotation the LLM echoes back: "(#2153)".
_CATALOG_ID = re.compile(r'\s*\(#(\d+)\)')


def _raw_name(entry: Any) -> str:
    if isinstance(entry, dict):
        return str(entry.get('name') or '')
    return str(entry or '')


def _canonical_from_store_product(sp_id: int) -> Optional[str]:
    """Clean name for a StoreProduct id via its canonical ingredient, or None."""
    from diet_planner.models import StoreProduct
    sp = (
        StoreProduct.objects
        .filter(id=sp_id)
        .select_related('canonical_ingredient')
        .first()
    )
    if sp and sp.canonical_ingredient:
        ci = sp.canonical_ingredient
        return ci.name_cs or ci.name
    return None


def display_ingredient_name(entry: Any) -> str:
    """Clean display name for one ingredient (dict or plain string).

    A name carrying the internal `(#id)` catalog marker is resolved to its
    canonical name — by the store-product id first (authoritative), then by the
    de-annotated name — and, failing both, has the marker stripped so no
    internal id ever reaches the page. Names without the marker are the author's
    own and pass through unchanged.
    """
    raw = _raw_name(entry)
    match = _CATALOG_ID.search(raw)
    if not match:
        return raw

    name = _canonical_from_store_product(int(match.group(1)))
    if name:
        return name

    stripped = _CATALOG_ID.sub('', raw).strip()
    ci = resolve_canonical(stripped) if stripped else None
    if ci:
        return ci.name_cs or ci.name
    return stripped


def display_ingredients(ingredients) -> list:
    """Ingredient list with display-clean names, shape preserved.

    Dicts keep every other field (quantity/unit/optional/canonical); strings
    stay strings. Used by both render paths — the API serializer and the SSR
    recipe view — so they cannot drift.
    """
    out = []
    for entry in ingredients or []:
        if isinstance(entry, dict):
            out.append({**entry, 'name': display_ingredient_name(entry)})
        else:
            out.append(display_ingredient_name(entry))
    return out
