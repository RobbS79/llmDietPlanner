"""Dietary restriction resolution, validation, and repair.

Single source of truth for everything restriction-related. Used by:
- CatalogService to filter the product catalog
- GeminiService to inject restriction rules into meal-plan prompts
- The post-generation validator that rejects/repairs violating meals
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from diet_planner.services.catalog import DIETARY_EXCLUSIONS

if TYPE_CHECKING:
    from diet_planner.models import DietaryGoal


@dataclass(frozen=True)
class ResolvedRestrictions:
    """Normalized dietary restrictions for one DietaryGoal.

    `tags` are the canonical restriction names (e.g. 'gluten_free').
    `exclusion_keywords` is the union of DIETARY_EXCLUSIONS for those tags
    plus any freeform allergens, all lowercased, ready for substring match.
    `freeform_allergens` is the set of allergen tokens parsed from prose
    (kept separate so callers can render them distinctly in prompts).
    """

    tags: frozenset[str]
    exclusion_keywords: frozenset[str]
    freeform_allergens: frozenset[str]


class RestrictionResolver:
    """Resolve a DietaryGoal into a normalized ResolvedRestrictions value."""

    def resolve(self, goal: "DietaryGoal") -> ResolvedRestrictions:
        tags: set[str] = set()

        structured = (getattr(goal, "dietary_restrictions", "") or "").lower()
        for tag in DIETARY_EXCLUSIONS.keys():
            if tag in structured:
                tags.add(tag)

        exclusion_keywords: set[str] = set()
        for tag in tags:
            exclusion_keywords.update(
                kw.lower() for kw in DIETARY_EXCLUSIONS[tag]
            )

        return ResolvedRestrictions(
            tags=frozenset(tags),
            exclusion_keywords=frozenset(exclusion_keywords),
            freeform_allergens=frozenset(),
        )
