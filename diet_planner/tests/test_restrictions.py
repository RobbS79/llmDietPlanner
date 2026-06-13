"""Unit tests for diet_planner.services.restrictions."""
from unittest.mock import MagicMock

import pytest

from diet_planner.services.restrictions import (
    ResolvedRestrictions,
    RestrictionResolver,
)


def _goal(prompt: str = "", dietary_restrictions: str = ""):
    g = MagicMock()
    g.prompt = prompt
    g.dietary_restrictions = dietary_restrictions
    return g


class TestRestrictionResolverStructured:
    def test_empty_goal_yields_empty_restrictions(self):
        result = RestrictionResolver().resolve(_goal())
        assert result == ResolvedRestrictions(
            tags=frozenset(),
            exclusion_keywords=frozenset(),
            freeform_allergens=frozenset(),
        )

    def test_structured_field_gluten_free(self):
        result = RestrictionResolver().resolve(
            _goal(dietary_restrictions="gluten_free")
        )
        assert "gluten_free" in result.tags
        # DIETARY_EXCLUSIONS['gluten_free'] keywords must all be present
        assert "mouka" in result.exclusion_keywords
        assert "flour" in result.exclusion_keywords
        assert "pšenič" in result.exclusion_keywords

    def test_structured_field_multiple_tags(self):
        result = RestrictionResolver().resolve(
            _goal(dietary_restrictions="vegan, gluten_free")
        )
        assert result.tags == frozenset({"vegan", "gluten_free"})
