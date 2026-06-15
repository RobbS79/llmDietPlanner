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


from diet_planner.services.restrictions import (
    DETERMINISTIC_SWAPS,
    try_deterministic_swap,
)


class TestDeterministicSwap:
    def test_gluten_free_flour_swap(self):
        meal = _meal(
            ingredients=[{"name": "pšeničná mouka", "quantity": 100, "unit": "g"}],
        )
        violation = Violation(
            meal_key="day_1.lunch",
            matched_keyword="mouka",
            matched_in="ingredients",
            ingredient_name="pšeničná mouka",
            source_text="pšeničná mouka",
        )
        swapped = try_deterministic_swap(
            meal, violation, tags=frozenset({"gluten_free"})
        )
        assert swapped is not None
        names = [i["name"] for i in swapped["ingredients"]]
        assert names == ["bezlepková mouka"]

    def test_vegan_meat_violation_has_no_swap(self):
        meal = _meal(
            ingredients=[{"name": "kuřecí prsa", "quantity": 200, "unit": "g"}],
        )
        violation = Violation(
            meal_key="day_1.dinner",
            matched_keyword="kuřecí",
            matched_in="ingredients",
            ingredient_name="kuřecí prsa",
            source_text="kuřecí prsa",
        )
        swapped = try_deterministic_swap(
            meal, violation, tags=frozenset({"vegan"})
        )
        assert swapped is None  # no swap exists — caller must re-prompt

    def test_instructions_violation_has_no_swap(self):
        # Swaps only fix ingredients[]; instruction-only violations always
        # require re-prompt.
        meal = _meal(
            ingredients=[{"name": "máslo", "quantity": 50, "unit": "g"}],
            instructions=["Smíchej s pšeničnou moukou."],
        )
        violation = Violation(
            meal_key="day_1.lunch",
            matched_keyword="mouka",
            matched_in="instructions",
            ingredient_name=None,
            source_text="Smíchej s pšeničnou moukou.",
        )
        swapped = try_deterministic_swap(
            meal, violation, tags=frozenset({"gluten_free"})
        )
        assert swapped is None

    def test_anti_rot_every_swap_target_validates_clean(self):
        """Swap targets must NOT trigger the validator for their own tag.

        Catches both 'we forgot the compliance modifier' and 'we swapped
        flour -> wheat flour'. If this test fails, the swap is bogus.
        """
        from diet_planner.services.catalog import DIETARY_EXCLUSIONS

        for tag, mapping in DETERMINISTIC_SWAPS.items():
            exclusion = frozenset(
                kw.lower() for kw in DIETARY_EXCLUSIONS[tag]
            )
            for source, target in mapping.items():
                meal = _meal(ingredients=[{"name": target, "quantity": 1, "unit": "g"}])
                violations = validate_meal_against_exclusions(meal, exclusion)
                assert violations == [], (
                    f"Swap target {target!r} (from {source!r} for tag {tag!r}) "
                    f"itself triggers the validator: {violations}"
                )


from diet_planner.services.restrictions import (
    RepairBudgetExhausted,
    RepairOutcome,
    repair_meals_with_violations,
)


class _FakeLLM:
    """Stub for GeminiService.regenerate_meal. Each script entry is the dict
    returned by the next call."""

    def __init__(self, scripted: list[dict]):
        self._scripted = list(scripted)
        self.calls = 0

    def regenerate_meal(self, *, original_meal, goal, exclusions, **_):
        self.calls += 1
        return self._scripted.pop(0)


class TestRepairLoop:
    def _exclusions(self):
        # 'mouka' (nominative) catches ingredient names like 'pšeničná mouka'
        # and triggers the deterministic swap; 'mouk' (prefix) catches Czech
        # case forms like 'moukou' in instruction prose, which has no swap.
        return ResolvedRestrictions(
            tags=frozenset({"gluten_free"}),
            exclusion_keywords=frozenset({"mouka", "mouk"}),
            freeform_allergens=frozenset(),
        )

    def test_no_violations_returns_days_unchanged(self):
        days = [{
            "day_number": 1,
            "breakfast": _meal(ingredients=[{"name": "rýže", "quantity": 100, "unit": "g"}]),
        }]
        outcome = repair_meals_with_violations(
            days=days, goal=MagicMock(),
            exclusions=self._exclusions(), llm=_FakeLLM([]),
        )
        assert outcome.days == days
        assert outcome.reprompts == 0

    def test_swap_applied_no_llm_call(self):
        days = [{
            "day_number": 1,
            "lunch": _meal(ingredients=[{"name": "pšeničná mouka", "quantity": 100, "unit": "g"}]),
        }]
        llm = _FakeLLM([])
        outcome = repair_meals_with_violations(
            days=days, goal=MagicMock(),
            exclusions=self._exclusions(), llm=llm,
        )
        assert llm.calls == 0
        assert outcome.days[0]["lunch"]["ingredients"][0]["name"] == "bezlepková mouka"

    def test_reprompt_for_unmapped_violation(self):
        # Instruction-only violation isn't swappable -> must re-prompt
        days = [{
            "day_number": 1,
            "lunch": _meal(
                ingredients=[{"name": "máslo", "quantity": 50, "unit": "g"}],
                instructions=["Smíchej s moukou."],
            ),
        }]
        compliant_replacement = _meal(
            name="GF lunch",
            ingredients=[{"name": "máslo", "quantity": 50, "unit": "g"}],
            instructions=["Smíchej s bezlepkovou moukou."],
        )
        llm = _FakeLLM([compliant_replacement])
        outcome = repair_meals_with_violations(
            days=days, goal=MagicMock(),
            exclusions=self._exclusions(), llm=llm,
        )
        assert llm.calls == 1
        assert outcome.days[0]["lunch"]["name"] == "GF lunch"

    def test_two_failed_reprompts_then_failure(self):
        days = [{
            "day_number": 1,
            "lunch": _meal(
                ingredients=[{"name": "máslo", "quantity": 50, "unit": "g"}],
                instructions=["Smíchej s moukou."],
            ),
        }]
        # Both replacements still contain 'moukou' in instructions
        still_bad = _meal(
            ingredients=[{"name": "máslo", "quantity": 50, "unit": "g"}],
            instructions=["Smíchej s moukou."],
        )
        llm = _FakeLLM([still_bad, still_bad])
        with pytest.raises(RepairBudgetExhausted):
            repair_meals_with_violations(
                days=days, goal=MagicMock(),
                exclusions=self._exclusions(), llm=llm,
                max_reprompts_per_meal=2, max_reprompts_per_plan=6,
            )
        assert llm.calls == 2

    def test_per_plan_budget_caps_calls(self):
        # Each meal becomes compliant after exactly one re-prompt, so the
        # per-meal cap (2) never trips. Re-prompts accumulate across meals;
        # the 6th spends the per-plan budget and the 7th meal raises before
        # any further LLM call -> exactly 6 calls.
        days = [
            {
                "day_number": d,
                "lunch": _meal(
                    ingredients=[{"name": "máslo", "quantity": 50, "unit": "g"}],
                    instructions=["Smíchej s moukou."],
                ),
            }
            for d in range(1, 8)  # 7 days, 7 violations
        ]
        compliant = _meal(
            ingredients=[{"name": "máslo", "quantity": 50, "unit": "g"}],
            instructions=["Smíchej s bezlepkovou moukou."],
        )
        llm = _FakeLLM([compliant] * 6)
        with pytest.raises(RepairBudgetExhausted):
            repair_meals_with_violations(
                days=days, goal=MagicMock(),
                exclusions=self._exclusions(), llm=llm,
                max_reprompts_per_meal=2, max_reprompts_per_plan=6,
            )
        assert llm.calls == 6
