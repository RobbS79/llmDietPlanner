"""
Resolve free-text ingredient names (as emitted by the LLM or scraped) to a
CanonicalIngredient row. Used by the pricing pipeline to read the
is_pantry_staple flag and other catalog-level metadata for a shopping-list line.

Matching order:
  1. CanonicalIngredient.name / name_cs / name_sk  (case-insensitive)
  2. IngredientAlias.alias                          (case-insensitive)

Returns None if no match — callers must handle that as "not a staple,
treat as a normal grocery item".
"""
from __future__ import annotations

from typing import Optional

from django.db.models import Q

from diet_planner.models import CanonicalIngredient, IngredientAlias


def resolve_canonical(name: str) -> Optional[CanonicalIngredient]:
    if not name:
        return None
    needle = name.strip()
    if not needle:
        return None

    ci = CanonicalIngredient.objects.filter(
        Q(name__iexact=needle)
        | Q(name_cs__iexact=needle)
        | Q(name_sk__iexact=needle)
    ).first()
    if ci is not None:
        return ci

    alias = (
        IngredientAlias.objects
        .select_related('canonical_ingredient')
        .filter(alias__iexact=needle)
        .first()
    )
    return alias.canonical_ingredient if alias is not None else None
