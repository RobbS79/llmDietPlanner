"""Gap fill: one Gemini call produces ONE meal for a named slot, with usage
accounting; restriction repair runs on a single meal."""
import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from diet_planner.llm_service import GeminiService
from diet_planner.services.restrictions import (
    DETERMINISTIC_SWAPS, RepairBudgetExhausted, ResolvedRestrictions, repair_single_meal,
)


def _no_exclusions():
    return ResolvedRestrictions(
        tags=frozenset(), exclusion_keywords=frozenset(), freeform_allergens=frozenset())


def _fake_response(payload, finish='STOP'):
    usage = SimpleNamespace(prompt_token_count=10, candidates_token_count=20, total_token_count=30)
    cand = SimpleNamespace(finish_reason=SimpleNamespace(name=finish))
    return SimpleNamespace(text=json.dumps(payload), usage_metadata=usage, candidates=[cand],
                           prompt_feedback=None)


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


def _slot_call(response, *, avoid_names=None, slot='dinner'):
    goal = SimpleNamespace(language_code='cs', prompt='x')
    with patch('diet_planner.llm_service.genai.GenerativeModel') as gm:
        gm.return_value.generate_content.return_value = response
        out = GeminiService().generate_slot_meal(
            slot=slot, user_prompt='x', goal=goal, exclusions=_no_exclusions(),
            avoid_names=avoid_names or [])
    return out, gm


class UnwrapSingleMealTest(SimpleTestCase):
    unwrap = staticmethod(GeminiService._unwrap_single_meal)

    def test_bare_list_returns_first_dict(self):
        self.assertEqual(self.unwrap([{'name': 'A'}, {'name': 'B'}], 'dinner'), {'name': 'A'})

    def test_meal_envelope(self):
        self.assertEqual(self.unwrap({'meal': {'name': 'A'}}, 'lunch'), {'name': 'A'})

    def test_snack_slot_prefers_snacks_list_over_lunch(self):
        parsed = {'days': [{'day_number': 1, 'lunch': {'name': 'Oběd'},
                            'snacks': [{'name': 'Jablko'}]}]}
        self.assertEqual(self.unwrap(parsed, 'snack'), {'name': 'Jablko'})

    def test_small_meal_slot_prefers_small_meals_list(self):
        parsed = {'days': [{'lunch': {'name': 'Oběd'}, 'snacks': [{'name': 'S'}],
                            'small_meals': [{'name': 'Svačina'}]}]}
        self.assertEqual(self.unwrap(parsed, 'small_meal'), {'name': 'Svačina'})


class GenerateSlotMealEdgeTest(SimpleTestCase):
    def test_reply_without_name_raises(self):
        with self.assertRaises(ValueError):
            _slot_call(_fake_response({'ingredients': []}))

    def test_empty_avoid_names_renders_none(self):
        _, gm = _slot_call(_fake_response({'name': 'X'}), avoid_names=[])
        self.assertIn('(none)', gm.return_value.generate_content.call_args.args[0])

    def test_max_tokens_finish_raises(self):
        with self.assertRaises(ValueError) as cm:
            _slot_call(_fake_response({'name': 'X'}, finish='MAX_TOKENS'))
        self.assertIn('MAX_TOKENS', str(cm.exception))

    def test_empty_candidates_raises(self):
        resp = _fake_response({'name': 'X'})
        resp.candidates = []
        with self.assertRaises(ValueError):
            _slot_call(resp)

    def test_text_accessor_error_propagates(self):
        class _Resp:
            candidates = [SimpleNamespace(finish_reason=SimpleNamespace(name='STOP'))]
            usage_metadata = None

            @property
            def text(self):
                raise RuntimeError('blocked')
        with self.assertRaises(RuntimeError):
            _slot_call(_Resp())

    def test_trailing_comma_json_is_tolerated(self):
        resp = _fake_response({})
        resp.text = '{"name": "X", "ingredients": [],}'
        out, _ = _slot_call(resp)
        self.assertEqual(out['meal']['name'], 'X')

    def test_system_prompt_uses_slot_task_line_without_catalog(self):
        _, gm = _slot_call(_fake_response({'name': 'X'}))
        system_prompt = gm.call_args.kwargs['system_instruction']
        self.assertIn('TASK: produce ONE new meal for the given slot honoring all rules.', system_prompt)
        self.assertNotIn('AVAILABLE PRODUCTS', system_prompt)
        self.assertNotIn('replacement meal', system_prompt)


class RegenerateMealTest(SimpleTestCase):
    def test_unwraps_days_reply_and_returns_meal_dict(self):
        wrapped = {'days': [{'day_number': 1, 'lunch': {'name': 'Rizoto', 'ingredients': []}}]}
        goal = SimpleNamespace(language_code='cs')
        with patch('diet_planner.llm_service.genai.GenerativeModel') as gm:
            gm.return_value.generate_content.return_value = _fake_response(wrapped)
            out = GeminiService().regenerate_meal(
                original_meal={'name': 'Kuře', 'food_category': 'lunch', 'ingredients': []},
                goal=goal, exclusions=_no_exclusions())
        self.assertEqual(out, {'name': 'Rizoto', 'ingredients': []})
        self.assertIn('Slot: lunch', gm.return_value.generate_content.call_args.args[0])


class RepairSingleMealExtraTest(SimpleTestCase):
    def _veg(self):
        return ResolvedRestrictions(
            tags=frozenset({'vegetarian'}), exclusion_keywords=frozenset({'kuřecí'}),
            freeform_allergens=frozenset())

    def test_deterministic_swap_path(self):
        self.assertIn('mouka', DETERMINISTIC_SWAPS['gluten_free'])
        excl = ResolvedRestrictions(
            tags=frozenset({'gluten_free'}), exclusion_keywords=frozenset({'mouka'}),
            freeform_allergens=frozenset())
        meal = {'name': 'Palačinky', 'ingredients': [{'name': 'mouka', 'quantity': 200}]}
        llm = MagicMock()
        out, reprompts, swaps = repair_single_meal(
            meal, goal=None, exclusions=excl, llm=llm, meal_key='breakfast:0')
        self.assertEqual((reprompts, swaps), (0, 1))
        self.assertEqual(out['ingredients'][0]['name'], DETERMINISTIC_SWAPS['gluten_free']['mouka'])
        self.assertEqual(meal['ingredients'][0]['name'], 'mouka')  # original unmutated
        llm.regenerate_meal.assert_not_called()

    def test_zero_reprompt_budget_raises_immediately(self):
        llm = MagicMock()
        meal = {'name': 'Kuře', 'ingredients': [{'name': 'kuřecí prsa'}]}
        with self.assertRaises(RepairBudgetExhausted):
            repair_single_meal(meal, goal=None, exclusions=self._veg(), llm=llm,
                               meal_key='dinner:0', max_reprompts=0)
        llm.regenerate_meal.assert_not_called()

    def test_injected_regenerate_is_used(self):
        llm = MagicMock()
        regen = MagicMock(return_value={'name': 'Houby', 'ingredients': [{'name': 'žampiony'}]})
        meal = {'name': 'Kuře', 'ingredients': [{'name': 'kuřecí prsa'}]}
        out, reprompts, _ = repair_single_meal(
            meal, goal=None, exclusions=self._veg(), llm=llm, meal_key='dinner:0',
            regenerate=regen)
        self.assertEqual(out['name'], 'Houby')
        self.assertEqual(reprompts, 1)
        regen.assert_called_once_with(meal)
        llm.regenerate_meal.assert_not_called()

    def test_swap_guard_counts_per_meal_version(self):
        # 2 swaps + non-swappable 'seitan' -> re-prompt -> 2-ingredient reply
        # needing 2 more swaps. Cumulative 4 exceeds that reply's cap (2*1+1=3),
        # so the guard must count swaps per version, not cumulatively.
        excl = ResolvedRestrictions(
            tags=frozenset({'gluten_free'}),
            exclusion_keywords=frozenset({'mouka', 'těstoviny', 'seitan'}),
            freeform_allergens=frozenset())
        meal = {'name': 'A', 'ingredients': [
            {'name': 'mouka'}, {'name': 'těstoviny'}, {'name': 'seitan'}]}
        regen = MagicMock(return_value={'name': 'B', 'ingredients': [
            {'name': 'mouka'}, {'name': 'těstoviny'}]})
        out, reprompts, swaps = repair_single_meal(
            meal, goal=None, exclusions=excl, llm=MagicMock(), meal_key='dinner:0',
            regenerate=regen)
        self.assertEqual((reprompts, swaps), (1, 4))
        self.assertEqual(out['name'], 'B')
