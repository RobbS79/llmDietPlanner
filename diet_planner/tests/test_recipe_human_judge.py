"""
Tests for diet_planner.services.recipe_human_judge.

The judge calls the Anthropic API, so the network path is mocked — these
tests pin down the parts we own: plan/shopping-list serialization, the
gating logic, fail-open behaviour, and the parsing of a model verdict into
a JudgeVerdict. The actual quality of Claude's judgement is exercised
manually against staging (see docs/qa-recipe-shopping-coherence.md §5.4),
not in CI.
"""
import json
from types import SimpleNamespace
from unittest import mock

from django.test import SimpleTestCase, override_settings

from diet_planner.services import recipe_human_judge as judge_mod
from diet_planner.services.recipe_human_judge import (
    JudgeVerdict,
    judge_plan_coherence,
    serialize_plan,
    serialize_shopping_list,
)


def _plan():
    """A minimal two-meal plan in the shape the validator passes in."""
    return {
        "days": [
            {
                "day_number": 1,
                "dinner": {
                    "name": "Hovězí na cibulce",
                    "description": "Hovězí maso (klizka) je již připravené z předchozího dne.",
                    "instructions": [{"text": "Orestujte cibuli."}, "Přidejte maso."],
                    "ingredients": [
                        {"name": "klizka", "quantity": 300, "unit": "g"},
                        {"name": "cibule", "quantity": 100, "unit": "g"},
                    ],
                    "pre_prepared_ingredients": [{"name": "klizka"}],
                },
            }
        ]
    }


def _shopping_list():
    return [
        {"ingredient": "cibule", "quantity": 100, "unit": "g", "price": 5.0, "store": "Rohlik"},
        {"ingredient": "klizka", "quantity": 300, "unit": "g", "price": 89.0, "store": "Rohlik"},
    ]


def _fake_response(payload, stop_reason="end_turn"):
    """Mimic the anthropic Message object shape the judge reads."""
    block = SimpleNamespace(type="text", text=json.dumps(payload))
    return SimpleNamespace(content=[block], stop_reason=stop_reason)


class SerializationTest(SimpleTestCase):
    def test_serialize_plan_flattens_meals(self):
        meals = serialize_plan(_plan())
        self.assertEqual(len(meals), 1)
        meal = meals[0]
        self.assertEqual(meal["day"], 1)
        self.assertEqual(meal["meal_type"], "dinner")
        self.assertEqual(meal["name"], "Hovězí na cibulce")
        # instructions: dict-step and bare-string-step both normalised to text
        self.assertEqual(meal["instructions"], ["Orestujte cibuli.", "Přidejte maso."])
        self.assertEqual({i["name"] for i in meal["ingredients"]}, {"klizka", "cibule"})
        self.assertIn("klizka", meal["pre_prepared"])

    def test_serialize_plan_handles_meal_as_list(self):
        plan = {"days": [{"day_number": 2, "lunch": [
            {"name": "A", "ingredients": []}, {"name": "B", "ingredients": []},
        ]}]}
        meals = serialize_plan(plan)
        self.assertEqual([m["name"] for m in meals], ["A", "B"])
        self.assertEqual([m["index"] for m in meals], [0, 1])

    def test_serialize_shopping_list_normalises_name_fields(self):
        items = serialize_shopping_list([
            {"ingredient": "rohlik"},
            {"name": "mleko"},
            {"matched_product_name": "Madeta máslo"},
            "not-a-dict",
        ])
        self.assertEqual([i["name"] for i in items], ["rohlik", "mleko", "Madeta máslo"])


@override_settings(RECIPE_HUMAN_JUDGE_ENABLED=False, ANTHROPIC_API_KEY=None)
class GatingTest(SimpleTestCase):
    def test_disabled_returns_not_run_without_calling_api(self):
        with mock.patch.object(judge_mod, "is_enabled", wraps=judge_mod.is_enabled):
            verdict = judge_plan_coherence(_plan(), _shopping_list())
        self.assertFalse(verdict.ran)
        self.assertEqual(verdict.verdict, "unknown")
        self.assertEqual(verdict.issues, [])

    @override_settings(RECIPE_HUMAN_JUDGE_ENABLED=True, ANTHROPIC_API_KEY=None)
    def test_enabled_flag_but_no_key_is_still_disabled(self):
        self.assertFalse(judge_mod.is_enabled())


@override_settings(RECIPE_HUMAN_JUDGE_ENABLED=True, ANTHROPIC_API_KEY="sk-ant-test")
class JudgingTest(SimpleTestCase):
    def _patch_client(self, response=None, side_effect=None):
        fake_client = mock.Mock()
        if side_effect is not None:
            fake_client.messages.create.side_effect = side_effect
        else:
            fake_client.messages.create.return_value = response
        fake_anthropic = mock.Mock()
        fake_anthropic.Anthropic.return_value = fake_client
        return mock.patch.dict("sys.modules", {"anthropic": fake_anthropic}), fake_client

    def test_parses_verdict_with_issues(self):
        payload = {
            "verdict": "incoherent",
            "shoppable": False,
            "cookable": True,
            "human_sane": True,
            "summary": "Charges for klizka the recipe says is already prepared.",
            "issues": [{
                "category": "orphan_shopping_item",
                "severity": "high",
                "location": "shopping list: 'klizka'",
                "quote": "klizka",
                "explanation": "Recipe says the beef is already prepared, list still charges for it.",
                "suggested_fix": "Drop klizka from the shopping list.",
            }],
        }
        patcher, fake_client = self._patch_client(_fake_response(payload))
        with patcher:
            verdict = judge_plan_coherence(_plan(), _shopping_list(), language="cs")

        self.assertTrue(verdict.ran)
        self.assertEqual(verdict.verdict, "incoherent")
        self.assertFalse(verdict.shoppable)
        self.assertEqual(len(verdict.issues), 1)
        self.assertTrue(verdict.has_blocking_issues)
        # the request was actually made with our schema + model
        _, kwargs = fake_client.messages.create.call_args
        self.assertEqual(kwargs["model"], "claude-sonnet-4-6")
        self.assertEqual(kwargs["output_config"]["effort"], "low")
        self.assertIn("format", kwargs["output_config"])

    def test_coherent_plan_returns_no_issues(self):
        payload = {
            "verdict": "coherent", "shoppable": True, "cookable": True,
            "human_sane": True, "summary": "Looks good.", "issues": [],
        }
        patcher, _ = self._patch_client(_fake_response(payload))
        with patcher:
            verdict = judge_plan_coherence(_plan(), _shopping_list())
        self.assertTrue(verdict.ran)
        self.assertEqual(verdict.issues, [])
        self.assertFalse(verdict.has_blocking_issues)

    def test_refusal_is_fail_open(self):
        patcher, _ = self._patch_client(_fake_response({}, stop_reason="refusal"))
        with patcher:
            verdict = judge_plan_coherence(_plan(), _shopping_list())
        self.assertFalse(verdict.ran)
        self.assertEqual(verdict.error, "refusal")

    def test_api_exception_is_fail_open(self):
        patcher, _ = self._patch_client(side_effect=RuntimeError("boom"))
        with patcher:
            verdict = judge_plan_coherence(_plan(), _shopping_list())
        self.assertFalse(verdict.ran)
        self.assertEqual(verdict.verdict, "unknown")
        self.assertIn("boom", verdict.error or "")

    def test_missing_sdk_is_fail_open(self):
        # Simulate `import anthropic` raising ImportError.
        import builtins
        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "anthropic":
                raise ImportError("No module named 'anthropic'")
            return real_import(name, *args, **kwargs)

        with mock.patch.object(builtins, "__import__", side_effect=fake_import):
            verdict = judge_plan_coherence(_plan(), _shopping_list())
        self.assertFalse(verdict.ran)
        self.assertEqual(verdict.error, "anthropic_not_installed")


class VerdictHelpersTest(SimpleTestCase):
    def test_as_stats_shape(self):
        v = JudgeVerdict(ran=True, verdict="minor_issues", shoppable=True,
                         cookable=True, human_sane=False, model="claude-opus-4-8",
                         issues=[{"severity": "high"}, {"severity": "low"}])
        stats = v.as_stats()
        self.assertEqual(stats["issue_count"], 2)
        self.assertEqual(stats["high_severity_count"], 1)
        self.assertEqual(stats["model"], "claude-opus-4-8")
