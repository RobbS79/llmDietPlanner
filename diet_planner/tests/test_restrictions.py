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


class TestRestrictionResolverFreeform:
    def test_prompt_only_czech_gluten_free(self):
        result = RestrictionResolver().resolve(
            _goal(prompt="Chci bezlepkový jídelníček, mám celiakii.")
        )
        assert "gluten_free" in result.tags
        assert "mouka" in result.exclusion_keywords

    def test_prompt_only_english_vegan(self):
        result = RestrictionResolver().resolve(
            _goal(prompt="Make me a vegan meal plan please")
        )
        assert "vegan" in result.tags

    def test_prompt_and_structured_field_union(self):
        result = RestrictionResolver().resolve(
            _goal(
                prompt="bez lepku",
                dietary_restrictions="vegan",
            )
        )
        assert result.tags == frozenset({"vegan", "gluten_free"})

    def test_freeform_allergen_peanut(self):
        result = RestrictionResolver().resolve(
            _goal(prompt="Alergie na arašídy a sezam.")
        )
        assert "peanut" in result.freeform_allergens
        assert "sesame" in result.freeform_allergens
        # Allergens also flow into exclusion_keywords for the validator
        assert "arašíd" in result.exclusion_keywords
        assert "sezam" in result.exclusion_keywords

    def test_freeform_allergen_english(self):
        result = RestrictionResolver().resolve(
            _goal(prompt="I'm allergic to soy and shellfish.")
        )
        assert "soy" in result.freeform_allergens
        assert "shellfish" in result.freeform_allergens

    def test_unknown_word_is_ignored(self):
        result = RestrictionResolver().resolve(
            _goal(prompt="Allergic to xylophone")
        )
        assert result.freeform_allergens == frozenset()


from diet_planner.services.restrictions import (
    COMPLIANCE_MODIFIERS,
    Violation,
    validate_meal_against_exclusions,
)


def _meal(name="Test meal", ingredients=None, instructions=None):
    return {
        "name": name,
        "ingredients": ingredients or [],
        "instructions": instructions or [],
    }


class TestValidator:
    def test_compliant_meal_has_no_violations(self):
        meal = _meal(
            ingredients=[{"name": "kuřecí prsa", "quantity": 200, "unit": "g"}],
            instructions=["Osol kuře a opeč."],
        )
        violations = validate_meal_against_exclusions(meal, frozenset({"mouka", "flour"}))
        assert violations == []

    def test_flour_in_ingredients_is_flagged(self):
        meal = _meal(
            ingredients=[{"name": "pšeničná mouka", "quantity": 100, "unit": "g"}],
        )
        violations = validate_meal_against_exclusions(meal, frozenset({"mouka"}))
        assert len(violations) == 1
        assert violations[0].matched_keyword == "mouka"
        assert violations[0].matched_in == "ingredients"

    def test_flour_in_instructions_is_flagged(self):
        meal = _meal(
            ingredients=[{"name": "máslo", "quantity": 50, "unit": "g"}],
            instructions=["Smíchej s moukou."],
        )
        violations = validate_meal_against_exclusions(meal, frozenset({"mouk"}))
        assert len(violations) == 1
        assert violations[0].matched_in == "instructions"

    def test_compliance_modifier_suppresses_match(self):
        # 'bezlepková mouka' contains 'mouka' but the bezlepk- modifier
        # legitimises it — no violation.
        meal = _meal(
            ingredients=[{"name": "bezlepková mouka", "quantity": 100, "unit": "g"}],
        )
        violations = validate_meal_against_exclusions(meal, frozenset({"mouka"}))
        assert violations == []

    def test_compliance_modifier_only_suppresses_for_modified_token(self):
        # 'bezlepková mouka, obyčejná mouka' — second one MUST still flag.
        meal = _meal(
            ingredients=[
                {"name": "bezlepková mouka", "quantity": 100, "unit": "g"},
                {"name": "obyčejná mouka", "quantity": 100, "unit": "g"},
            ],
        )
        violations = validate_meal_against_exclusions(meal, frozenset({"mouka"}))
        assert len(violations) == 1
        assert violations[0].ingredient_name == "obyčejná mouka"

    def test_compliance_modifiers_constant_exists(self):
        # Smoke test: every supported tag has a modifier list.
        for tag in ("gluten_free", "lactose_free", "vegan"):
            assert tag in COMPLIANCE_MODIFIERS
            assert len(COMPLIANCE_MODIFIERS[tag]) >= 1
