"""System-prompt construction tests for the meal-plan LLM calls."""
import json
from unittest.mock import MagicMock

import pytest

from diet_planner.llm_service import GeminiService
from diet_planner.services.restrictions import (
    RepairBudgetExhausted,
    ResolvedRestrictions,
)


def _fake_response(text):
    resp = MagicMock()
    finish = MagicMock()
    finish.name = "STOP"
    resp.candidates = [MagicMock(finish_reason=finish)]
    resp.text = text
    resp.usage_metadata = MagicMock(
        prompt_token_count=1, candidates_token_count=1, total_token_count=2,
    )
    return resp


def _script_genai(monkeypatch, script):
    """Patch genai.GenerativeModel to emit `script` response texts in order.

    Returns a state dict whose 'prompts' list records every generate_content
    call, so a test can assert how many LLM round-trips actually happened
    (initial plan + re-prompts).
    """
    state = {"prompts": [], "script": list(script)}

    class ScriptedModel:
        def __init__(self, model_name, system_instruction):
            self.system_instruction = system_instruction

        def generate_content(self, prompt, *a, **kw):
            state["prompts"].append(prompt)
            return _fake_response(state["script"].pop(0))

    import diet_planner.llm_service as llm_mod
    monkeypatch.setattr(llm_mod.genai, "GenerativeModel", ScriptedModel)
    return state


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


class TestShoppingListUsesAggregatedList:
    def test_user_prompt_lists_every_aggregated_item(self, monkeypatch):
        svc = GeminiService()
        captured = {}

        class FakeModel:
            def __init__(self, model_name, system_instruction):
                captured["system_instruction"] = system_instruction
            def generate_content(self, prompt, *a, **kw):
                captured["prompt"] = prompt
                resp = MagicMock()
                resp.candidates = [MagicMock(finish_reason=MagicMock(name="OK"))]
                resp.text = '{"shopping_list": [], "total_cost": 0}'
                resp.usage_metadata = MagicMock(
                    prompt_token_count=1, candidates_token_count=1
                )
                return resp

        import diet_planner.llm_service as llm_mod
        monkeypatch.setattr(llm_mod.genai, "GenerativeModel", FakeModel)

        aggregated = [
            {"ingredient": "rýže", "quantity": 200, "unit": "g"},
            {"ingredient": "kuřecí prsa", "quantity": 800, "unit": "g"},
            # 40 more items to ensure no [:5000] truncation drops them
            *[
                {"ingredient": f"item_{i}", "quantity": 10, "unit": "g"}
                for i in range(40)
            ],
        ]
        svc.generate_shopping_list_with_prices(
            aggregated_items=aggregated,
            shop_url="https://x.example",
            goal=_goal(),
        )
        # Every aggregated item must appear verbatim in the user prompt
        for item in aggregated:
            assert item["ingredient"] in captured["prompt"]


class TestGenerateMealPlanOnlyEnforcesRestrictions:
    """End-to-end through the real generation method with only Gemini mocked.

    Exercises resolve-from-goal -> system prompt -> JSON parse -> repair loop,
    i.e. the wiring that connects restriction enforcement to generation.
    """

    def test_swappable_violation_repaired_without_reprompt(self, monkeypatch):
        svc = GeminiService()
        plan = json.dumps({"days": [{
            "day_number": 1,
            "lunch": {
                "name": "Pšeničné placky",
                "ingredients": [
                    {"name": "pšeničná mouka", "quantity": 200, "unit": "g"}
                ],
                "instructions": ["Smíchej a opeč."],
            },
        }]})
        state = _script_genai(monkeypatch, [plan])

        # exclusions=None -> resolved from the goal's gluten_free restriction.
        result = svc.generate_meal_plan_only(
            user_prompt="bezlepkový týden",
            shop_url="https://x.example",
            goal=_goal(dietary_restrictions="gluten_free", prompt=""),
            exclusions=None,
        )

        lunch = result["response"]["days"][0]["lunch"]
        assert lunch["ingredients"][0]["name"] == "bezlepková mouka"
        # Deterministic swap => no second LLM round-trip.
        assert len(state["prompts"]) == 1

    def test_unswappable_violation_triggers_reprompt(self, monkeypatch):
        svc = GeminiService()
        bad_plan = json.dumps({"days": [{
            "day_number": 1,
            "lunch": {
                "name": "Máslová omáčka",
                "ingredients": [{"name": "máslo", "quantity": 50, "unit": "g"}],
                "instructions": ["Smíchej s moukou."],
            },
        }]})
        compliant_meal = json.dumps({
            "name": "Bezlepková omáčka",
            "ingredients": [{"name": "máslo", "quantity": 50, "unit": "g"}],
            "instructions": ["Smíchej s bezlepkovou moukou."],
            "food_category": "lunch_main_dish",
        })
        state = _script_genai(monkeypatch, [bad_plan, compliant_meal])

        exclusions = ResolvedRestrictions(
            tags=frozenset({"gluten_free"}),
            exclusion_keywords=frozenset({"mouka", "mouk"}),
            freeform_allergens=frozenset(),
        )
        result = svc.generate_meal_plan_only(
            user_prompt="bezlepkový týden",
            shop_url="https://x.example",
            goal=_goal(),
            exclusions=exclusions,
        )

        assert result["response"]["days"][0]["lunch"]["name"] == "Bezlepková omáčka"
        # initial plan + exactly one re-prompt
        assert len(state["prompts"]) == 2

    def test_unrepairable_violation_raises_budget_exhausted(self, monkeypatch):
        svc = GeminiService()
        bad_instructions = ["Smíchej s moukou."]
        bad_plan = json.dumps({"days": [{
            "day_number": 1,
            "lunch": {
                "name": "Máslová omáčka",
                "ingredients": [{"name": "máslo", "quantity": 50, "unit": "g"}],
                "instructions": bad_instructions,
            },
        }]})
        still_bad = json.dumps({
            "name": "Pořád špatné",
            "ingredients": [{"name": "máslo", "quantity": 50, "unit": "g"}],
            "instructions": bad_instructions,
            "food_category": "lunch_main_dish",
        })
        # initial plan + 2 failing re-prompts trips the per-meal cap.
        state = _script_genai(monkeypatch, [bad_plan, still_bad, still_bad])

        exclusions = ResolvedRestrictions(
            tags=frozenset({"gluten_free"}),
            exclusion_keywords=frozenset({"mouka", "mouk"}),
            freeform_allergens=frozenset(),
        )
        with pytest.raises(RepairBudgetExhausted):
            svc.generate_meal_plan_only(
                user_prompt="bezlepkový týden",
                shop_url="https://x.example",
                goal=_goal(),
                exclusions=exclusions,
            )
        assert len(state["prompts"]) == 3


class TestCompletePlanAlignsShoppingListWithRecipes:
    """The two-step generator must price the AGGREGATED recipe ingredients,
    not the raw days envelope. This is the shopping-list <-> recipe parity
    guarantee: every ingredient a recipe uses reaches the pricing call exactly
    once, with quantities summed across meals.
    """

    def test_pricing_call_receives_every_recipe_ingredient(self, monkeypatch):
        svc = GeminiService()
        plan = json.dumps({"days": [{
            "day_number": 1,
            "breakfast": {
                "name": "Vaječná snídaně",
                "ingredients": [
                    {"name": "vejce", "quantity": 2, "unit": "ks"},
                    {"name": "rýže", "quantity": 100, "unit": "g"},
                ],
                "instructions": ["Uvař."],
            },
            "lunch": {
                "name": "Kuřecí oběd",
                "ingredients": [
                    {"name": "kuřecí prsa", "quantity": 200, "unit": "g"},
                ],
                "instructions": ["Opeč."],
            },
            "dinner": {
                "name": "Rýžová večeře",
                "ingredients": [
                    {"name": "rýže", "quantity": 150, "unit": "g"},
                ],
                "instructions": ["Uvař."],
            },
        }]})
        shopping = json.dumps({"shopping_list": [], "total_cost": 0})
        state = _script_genai(monkeypatch, [plan, shopping])

        svc.generate_complete_plan_with_shopping_list(
            user_prompt="týdenní jídelníček",
            shop_url="https://x.example",
            goal=_goal(dietary_restrictions="", prompt=""),
        )

        # Two LLM round-trips: meal plan (step 1), then pricing (step 2).
        assert len(state["prompts"]) == 2
        pricing_prompt = state["prompts"][1]
        # Every recipe ingredient reaches the pricing call.
        for name in ("vejce", "rýže", "kuřecí prsa"):
            assert name in pricing_prompt, f"{name!r} missing from pricing prompt"
        # rýže is used in two meals: it must be aggregated into a single line
        # (250 g total), not duplicated and not left as a raw days envelope.
        assert pricing_prompt.count("rýže") == 1
        assert "250" in pricing_prompt
