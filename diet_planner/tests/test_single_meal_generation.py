"""Gap fill: one Gemini call produces ONE meal for a named slot, with usage
accounting; restriction repair runs on a single meal."""
import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from diet_planner.llm_service import GeminiService
from diet_planner.services.restrictions import (
    RepairBudgetExhausted, ResolvedRestrictions, repair_single_meal,
)


def _no_exclusions():
    return ResolvedRestrictions(
        tags=frozenset(), exclusion_keywords=frozenset(), freeform_allergens=frozenset())


def _fake_response(payload: dict):
    usage = SimpleNamespace(prompt_token_count=10, candidates_token_count=20, total_token_count=30)
    return SimpleNamespace(text=json.dumps(payload), usage_metadata=usage, candidates=[])


class GenerateSlotMealTest(SimpleTestCase):
    def test_returns_meal_and_usage(self):
        goal = SimpleNamespace(language_code='cs', prompt='rychlé večeře')
        meal = {'name': 'Kuřecí nudličky', 'ingredients': [{'name': 'kuřecí prsa', 'quantity': 300, 'unit': 'g'}],
                'instructions': ['Osmahni.'], 'nutritional_info': {'calories': 520}}
        with patch('diet_planner.llm_service.genai.GenerativeModel') as gm:
            gm.return_value.generate_content.return_value = _fake_response(meal)
            out = GeminiService().generate_slot_meal(
                slot='dinner', user_prompt='rychlé večeře', goal=goal,
                exclusions=_no_exclusions(),
                avoid_names=['Guláš'],
            )
        self.assertEqual(out['meal']['name'], 'Kuřecí nudličky')
        self.assertEqual(out['input_tokens'], 10)
        self.assertEqual(out['output_tokens'], 20)
        brief = gm.return_value.generate_content.call_args.args[0]
        self.assertIn('Slot: dinner', brief)
        self.assertIn('Guláš', brief)
        self.assertIn('rychlé večeře', brief)

    def test_unwraps_days_shaped_reply(self):
        goal = SimpleNamespace(language_code='cs', prompt='x')
        wrapped = {'days': [{'day_number': 1, 'dinner': {'name': 'Zapečené těstoviny', 'ingredients': []}}]}
        with patch('diet_planner.llm_service.genai.GenerativeModel') as gm:
            gm.return_value.generate_content.return_value = _fake_response(wrapped)
            out = GeminiService().generate_slot_meal(
                slot='dinner', user_prompt='x', goal=goal,
                exclusions=_no_exclusions(), avoid_names=[])
        self.assertEqual(out['meal']['name'], 'Zapečené těstoviny')


class RepairSingleMealTest(SimpleTestCase):
    def _excl(self):
        # vegetarian has no DETERMINISTIC_SWAPS entry -> violations re-prompt
        return ResolvedRestrictions(
            tags=frozenset({'vegetarian'}), exclusion_keywords=frozenset({'kuřecí'}),
            freeform_allergens=frozenset())

    def test_clean_meal_passes_through(self):
        meal = {'name': 'Rizoto', 'ingredients': [{'name': 'rýže'}]}
        out, reprompts, swaps = repair_single_meal(
            meal, goal=None, exclusions=self._excl(), llm=MagicMock(), meal_key='dinner:0')
        self.assertIs(out, meal)
        self.assertEqual((reprompts, swaps), (0, 0))

    def test_reprompts_until_compliant(self):
        llm = MagicMock()
        llm.regenerate_meal.side_effect = [
            {'name': 'Kuřecí rizoto 2', 'ingredients': [{'name': 'kuřecí prsa'}]},
            {'name': 'Houbové rizoto', 'ingredients': [{'name': 'žampiony'}]},
        ]
        meal = {'name': 'Kuřecí rizoto', 'ingredients': [{'name': 'kuřecí prsa'}]}
        out, reprompts, _ = repair_single_meal(
            meal, goal=None, exclusions=self._excl(), llm=llm, meal_key='dinner:0')
        self.assertEqual(out['name'], 'Houbové rizoto')
        self.assertEqual(reprompts, 2)

    def test_budget_exhausted_raises(self):
        llm = MagicMock()
        llm.regenerate_meal.return_value = {'name': 'Kuře', 'ingredients': [{'name': 'kuřecí stehna'}]}
        meal = {'name': 'Kuře', 'ingredients': [{'name': 'kuřecí prsa'}]}
        with self.assertRaises(RepairBudgetExhausted):
            repair_single_meal(meal, goal=None, exclusions=self._excl(), llm=llm,
                               meal_key='dinner:0', max_reprompts=2)
