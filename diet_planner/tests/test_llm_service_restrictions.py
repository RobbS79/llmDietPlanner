"""System-prompt construction tests for the meal-plan LLM calls."""
from unittest.mock import MagicMock

from diet_planner.llm_service import GeminiService
from diet_planner.services.restrictions import ResolvedRestrictions


def _goal(**overrides):
    g = MagicMock()
    g.language_code = "cs"
    g.country = "CZ"
    g.num_days = 7
    g.shop = "rohlik"
    for k, v in overrides.items():
        setattr(g, k, v)
    return g


class TestBuildMealSystemPrompt:
    def test_no_exclusions_omits_restriction_block(self):
        svc = GeminiService()
        prompt = svc._build_meal_system_prompt(
            goal=_goal(), exclusions=None, shop_url="https://x.example",
        )
        assert "DIETARY RESTRICTIONS" not in prompt

    def test_gluten_free_adds_hard_rule_block_with_keywords(self):
        svc = GeminiService()
        exclusions = ResolvedRestrictions(
            tags=frozenset({"gluten_free"}),
            exclusion_keywords=frozenset({"mouka", "flour", "wheat"}),
            freeform_allergens=frozenset(),
        )
        prompt = svc._build_meal_system_prompt(
            goal=_goal(), exclusions=exclusions, shop_url="https://x.example",
        )
        assert "DIETARY RESTRICTIONS" in prompt
        assert "gluten_free" in prompt
        # all keywords surfaced for the model
        assert "mouka" in prompt
        assert "flour" in prompt
        assert "wheat" in prompt

    def test_freeform_allergens_appear_in_block(self):
        svc = GeminiService()
        exclusions = ResolvedRestrictions(
            tags=frozenset(),
            exclusion_keywords=frozenset({"arašíd", "peanut"}),
            freeform_allergens=frozenset({"peanut"}),
        )
        prompt = svc._build_meal_system_prompt(
            goal=_goal(), exclusions=exclusions, shop_url="https://x.example",
        )
        assert "ALLERG" in prompt.upper()
        assert "peanut" in prompt

    def test_single_meal_mode_changes_output_schema_hint(self):
        svc = GeminiService()
        prompt = svc._build_meal_system_prompt(
            goal=_goal(), exclusions=None, shop_url="https://x.example",
            single_meal=True,
        )
        # In single-meal mode we expect a single meal object, not a days array
        assert "days" not in prompt.lower() or "single meal" in prompt.lower()
