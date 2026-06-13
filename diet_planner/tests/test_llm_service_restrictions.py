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


class TestGenerateMealPlanOnlyUsesExclusions:
    def test_passes_restriction_block_via_system_instruction(self, monkeypatch):
        svc = GeminiService()
        captured = {}

        class FakeModel:
            def __init__(self, model_name, system_instruction):
                captured["system_instruction"] = system_instruction
            def generate_content(self, *a, **kw):
                resp = MagicMock()
                resp.candidates = [MagicMock(finish_reason=MagicMock(name="OK"))]
                resp.text = '{"days": []}'
                resp.usage_metadata = MagicMock(
                    prompt_token_count=1, candidates_token_count=1
                )
                return resp

        import diet_planner.llm_service as llm_mod
        monkeypatch.setattr(llm_mod.genai, "GenerativeModel", FakeModel)

        exclusions = ResolvedRestrictions(
            tags=frozenset({"gluten_free"}),
            exclusion_keywords=frozenset({"mouka", "flour"}),
            freeform_allergens=frozenset(),
        )
        svc.generate_meal_plan_only(
            user_prompt="bezlepkový týden",
            shop_url="https://x.example",
            goal=_goal(),
            exclusions=exclusions,
        )
        assert "DIETARY RESTRICTIONS" in captured["system_instruction"]
        assert "mouka" in captured["system_instruction"]


class TestGenerateCatalogConstrainedPlanUsesExclusions:
    def test_passes_restriction_block_via_system_instruction(self, monkeypatch):
        svc = GeminiService()
        captured = {}

        class FakeModel:
            def __init__(self, model_name, system_instruction):
                captured["system_instruction"] = system_instruction
            def generate_content(self, *a, **kw):
                resp = MagicMock()
                resp.candidates = [MagicMock(finish_reason=MagicMock(name="OK"))]
                resp.text = '{"days": []}'
                resp.usage_metadata = MagicMock(
                    prompt_token_count=1, candidates_token_count=1
                )
                return resp

        import diet_planner.llm_service as llm_mod
        monkeypatch.setattr(llm_mod.genai, "GenerativeModel", FakeModel)

        exclusions = ResolvedRestrictions(
            tags=frozenset({"vegan"}),
            exclusion_keywords=frozenset({"kuřecí", "chicken"}),
            freeform_allergens=frozenset(),
        )
        svc.generate_catalog_constrained_plan(
            user_prompt="vegan",
            catalog_text="#1 rice\n#2 beans",
            goal=_goal(),
            exclusions=exclusions,
        )
        assert "DIETARY RESTRICTIONS" in captured["system_instruction"]
        assert "kuřecí" in captured["system_instruction"]
