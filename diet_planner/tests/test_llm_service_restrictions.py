"""System-prompt construction tests for the single-meal LLM calls."""
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
            goal=_goal(), exclusions=None,
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
            goal=_goal(), exclusions=exclusions,
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
            goal=_goal(), exclusions=exclusions,
        )
        assert "ALLERG" in prompt.upper()
        assert "peanut" in prompt

    def test_prompt_asks_for_a_single_meal_not_a_days_array(self):
        svc = GeminiService()
        prompt = svc._build_meal_system_prompt(goal=_goal(), exclusions=None)
        assert "SINGLE meal" in prompt
        assert '"days"' not in prompt
        assert "INGREDIENT EFFICIENCY" not in prompt

    def test_task_line_overrides_default_scope(self):
        svc = GeminiService()
        prompt = svc._build_meal_system_prompt(
            goal=_goal(), exclusions=None, task_line="TASK: custom line.",
        )
        assert "TASK: custom line." in prompt
        assert "replacement meal" not in prompt


class TestRegenerateMeal:
    def test_returns_single_meal_dict(self, monkeypatch):
        svc = GeminiService()

        class FakeModel:
            def __init__(self, model_name, system_instruction):
                self.system_instruction = system_instruction
            def generate_content(self, *a, **kw):
                resp = MagicMock()
                resp.candidates = [MagicMock(finish_reason=MagicMock(name="OK"))]
                resp.text = (
                    '{"name": "GF Risotto", "description": "Compliant.",'
                    '"food_category": "lunch_main_dish", "preparation_time": 20,'
                    '"ingredients": [{"name": "rýže", "quantity": 100, "unit": "g"}],'
                    '"instructions": ["Vař rýži."],'
                    '"nutritional_info": {"calories": 350}}'
                )
                resp.usage_metadata = MagicMock(
                    prompt_token_count=1, candidates_token_count=1
                )
                return resp

        import diet_planner.llm_service as llm_mod
        monkeypatch.setattr(llm_mod.genai, "GenerativeModel", FakeModel)

        original = {
            "name": "Wheat-based lunch",
            "ingredients": [{"name": "mouka", "quantity": 100, "unit": "g"}],
            "instructions": ["mix flour"],
            "food_category": "lunch_main_dish",
        }
        exclusions = ResolvedRestrictions(
            tags=frozenset({"gluten_free"}),
            exclusion_keywords=frozenset({"mouka", "flour"}),
            freeform_allergens=frozenset(),
        )
        result = svc.regenerate_meal(
            original_meal=original, goal=_goal(), exclusions=exclusions,
        )
        # Must be a SINGLE meal dict, not a days envelope
        assert "days" not in result
        assert result["name"] == "GF Risotto"
        assert all(i["name"] != "mouka" for i in result["ingredients"])
