"""Refine agent tool loop (refine chat v2).

Spec: docs/superpowers/specs/2026-07-27-chat-recipe-acquisition-design.md.
"""
from django.contrib.auth import get_user_model
from django.test import TestCase

from diet_planner.models import RecipeResearchJob
from diet_planner.services import refine_agent
from diet_planner.tests.test_recipe_replace import make_recipe


class FakeSession:
    """Scripted agent session. Each entry is what send()/send_tool_result()
    should return next: {'text': ..., 'tool_call': ...}."""

    def __init__(self, steps):
        self.steps = list(steps)
        self.tool_results = []

    def send_text(self, text):
        self.first_message = text
        return self.steps.pop(0)

    def send_tool_result(self, name, payload):
        self.tool_results.append((name, payload))
        return self.steps.pop(0)


def _final(reply, candidate_id=None):
    import json
    return {'tool_call': None,
            'text': json.dumps({'reply': reply, 'candidate_id': candidate_id})}


def _call(name, **args):
    return {'tool_call': {'name': name, 'args': args}, 'text': None}


class RefineAgentTest(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create(username='agentik')
        self.recipe = make_recipe(name_cs='Kuřecí rizoto')

    def _turn(self, steps, **kw):
        session = FakeSession(steps)
        result = refine_agent.run_refine_turn(
            user=self.user,
            meal_identifier=kw.pop('meal_identifier', '1:1:lunch:0'),
            meal_type='lunch',
            current_meal={'name': 'Menemen', 'description': 'vejce s rajčaty'},
            required_tags=kw.pop('required_tags', set()),
            pool=kw.pop('pool', [self.recipe]),
            exclude_ids=set(),
            used_recipe_ids=set(),
            used_cuisines=[],
            messages=[{'role': 'user', 'text': 'něco jiného k obědu'}],
            session_factory=lambda system_prompt: session,
        )
        return result, session

    def test_plain_conversation_no_tools(self):
        result, session = self._turn([_final('Rád pomůžu — na co máte chuť?')])
        self.assertEqual(result.reply_text, 'Rád pomůžu — na co máte chuť?')
        self.assertIsNone(result.candidate)
        self.assertIsNone(result.research_job_id)
        # Current recipe context must reach the model.
        self.assertIn('Menemen', session.first_message)
        self.assertIn('lunch', session.first_message)

    def test_corpus_pick_resolves_candidate_from_tool_results(self):
        result, session = self._turn([
            _call('search_corpus', wanted_ingredients=['kuřecí']),
            _final('Co třeba Kuřecí rizoto?', candidate_id=self.recipe.id),
        ])
        self.assertEqual(result.candidate.id, self.recipe.id)
        name, payload = session.tool_results[0]
        self.assertEqual(name, 'search_corpus')
        self.assertEqual(payload['candidates'][0]['id'], self.recipe.id)

    def test_runners_up_ride_along_as_alternatives(self):
        # The model talks about one dish; the next-best two are offered next to
        # it so the user picks rather than takes what came back first.
        others = [make_recipe(name_cs=f'Jídlo {i}') for i in range(3)]
        result, session = self._turn(
            [_call('search_corpus'), _final('Co třeba Kuřecí rizoto?',
                                            candidate_id=self.recipe.id)],
            pool=[self.recipe, *others],
        )
        _, payload = session.tool_results[0]
        offered = [c['id'] for c in payload['candidates']]
        self.assertEqual(result.candidate.id, self.recipe.id)
        # Rank order preserved, the pick itself never repeated, capped at 2.
        self.assertEqual(
            [r.id for r in result.alternatives],
            [i for i in offered if i != self.recipe.id][:2],
        )

    def test_no_alternatives_without_a_pick(self):
        # A pure conversational turn must not dump cards under a question.
        others = [make_recipe(name_cs=f'Jídlo {i}') for i in range(3)]
        result, _ = self._turn(
            [_call('search_corpus'), _final('Na co máte chuť?')],
            pool=[self.recipe, *others],
        )
        self.assertIsNone(result.candidate)
        self.assertEqual(result.alternatives, [])

    def test_alternatives_empty_when_pick_was_the_only_result(self):
        result, _ = self._turn([
            _call('search_corpus'),
            _final('Co třeba Kuřecí rizoto?', candidate_id=self.recipe.id),
        ])
        self.assertEqual(result.candidate.id, self.recipe.id)
        self.assertEqual(result.alternatives, [])

    def test_fabricated_candidate_id_is_dropped(self):
        result, _ = self._turn([
            _call('search_corpus'),
            _final('Co třeba tohle?', candidate_id=999999),
        ])
        self.assertIsNone(result.candidate)
        self.assertEqual(result.reply_text, 'Co třeba tohle?')

    def test_dietary_tags_always_reach_the_gate(self):
        # Pool recipe lacks the vegan tag -> tool must return zero candidates
        # no matter what the model asked for.
        result, session = self._turn(
            [
                _call('search_corpus', wanted_ingredients=['kuřecí']),
                _final('Nic veganského tu nemám.'),
            ],
            required_tags={'vegan'},
        )
        _, payload = session.tool_results[0]
        self.assertEqual(payload['candidates'], [])

    def test_research_web_creates_job_and_returns_id(self):
        result, session = self._turn([
            _call('research_web', query='pravý ramen'),
            _final('Hledám recept na webu, chvilku strpení…'),
        ])
        job = RecipeResearchJob.objects.get(id=result.research_job_id)
        self.assertEqual(job.user, self.user)
        self.assertEqual(job.query, 'pravý ramen')
        self.assertEqual(job.meal_identifier, '1:1:lunch:0')

    def test_cap_reached_is_reported_as_tool_error(self):
        from diet_planner.services import recipe_research
        for i in range(recipe_research.DAILY_CAP):
            RecipeResearchJob.objects.create(
                user=self.user, meal_identifier='1:1:lunch:0', query=f'q{i}',
            )
        result, session = self._turn([
            _call('research_web', query='pátý pokus'),
            _final('Dnes už jsme limit hledání vyčerpali.'),
        ])
        self.assertIsNone(result.research_job_id)
        _, payload = session.tool_results[0]
        self.assertEqual(payload.get('error'), 'cap_reached')
        # No sixth job row.
        self.assertEqual(RecipeResearchJob.objects.filter(user=self.user).count(),
                         recipe_research.DAILY_CAP)

    def test_tool_round_bound_forces_reply(self):
        # Model keeps calling tools; after MAX_TOOL_ROUNDS the loop must stop
        # and surface whatever text is available (fallback line).
        steps = [_call('search_corpus')] * (refine_agent.MAX_TOOL_ROUNDS + 1)
        result, _ = self._turn(steps)
        self.assertTrue(result.reply_text)  # never empty

    def test_unparseable_final_message_degrades_to_raw_text(self):
        result, _ = self._turn([{'tool_call': None, 'text': 'prostě text bez JSONu'}])
        self.assertEqual(result.reply_text, 'prostě text bez JSONu')
        self.assertIsNone(result.candidate)

    # --- prod QA 2026-07-27 regressions: Gemini emits prose+JSON and string ids ---

    def test_prose_prefixed_json_does_not_leak_into_reply(self):
        # 5/6 prod turns: model narrates, then appends the JSON contract.
        leaked = ('Rozumím, najdu ti něco jiného k obědu. '
                  '{"reply": "Co třeba Kuřecí rizoto?", "candidate_id": %d}' % self.recipe.id)
        result, _ = self._turn([
            _call('search_corpus'),
            {'tool_call': None, 'text': leaked},
        ])
        self.assertEqual(result.reply_text, 'Co třeba Kuřecí rizoto?')
        self.assertNotIn('{', result.reply_text)
        self.assertEqual(result.candidate.id, self.recipe.id)

    def test_string_candidate_id_resolves(self):
        # Prod: model emitted candidate_id as a string ("18944").
        import json
        result, _ = self._turn([
            _call('search_corpus'),
            {'tool_call': None,
             'text': json.dumps({'reply': 'Co třeba Kuřecí rizoto?',
                                 'candidate_id': str(self.recipe.id)})},
        ])
        self.assertEqual(result.candidate.id, self.recipe.id)

    def test_prose_with_string_id_full_prod_shape(self):
        # The exact prod failure shape: prose + JSON with a quoted id.
        leaked = ('Je to syté a chutné jídlo.'
                  '{"reply": "Co bys řekl na Kuřecí rizoto?", "candidate_id": "%d"}'
                  % self.recipe.id)
        result, _ = self._turn([
            _call('search_corpus'),
            {'tool_call': None, 'text': leaked},
        ])
        self.assertEqual(result.reply_text, 'Co bys řekl na Kuřecí rizoto?')
        self.assertEqual(result.candidate.id, self.recipe.id)

    def test_non_numeric_string_candidate_id_is_dropped(self):
        import json
        result, _ = self._turn([
            _call('search_corpus'),
            {'tool_call': None,
             'text': json.dumps({'reply': 'Tohle?', 'candidate_id': 'abc'})},
        ])
        self.assertEqual(result.reply_text, 'Tohle?')
        self.assertIsNone(result.candidate)


class SearchCorpusCandidateCaloriesTest(TestCase):
    """Candidate calories are what the chat card shows and what the model reasons
    over when picking a dish. base_nutrition is the WHOLE-recipe total for
    base_servings portions, so it must be divided down to per-portion first —
    otherwise a 4-portion dish is offered as a 2150 kcal lunch."""

    def _candidates(self, recipe):
        return refine_agent._tool_search_corpus(
            {},
            meal_type='lunch',
            required_tags=set(),
            pool=[recipe],
            exclude_ids=set(),
            used_recipe_ids=set(),
            used_cuisines=[],
        )['candidates']

    def test_multi_portion_recipe_reports_per_portion_calories(self):
        recipe = make_recipe(
            name_cs='Zapečené těstoviny',
            base_servings=4,
            base_nutrition={'calories': 2150, 'protein': 100, 'carbs': 200, 'fat': 80},
        )
        self.assertEqual(self._candidates(recipe)[0]['calories'], 538)

    def test_single_portion_recipe_is_unchanged(self):
        recipe = make_recipe(name_cs='Omeleta', base_servings=1,
                             base_nutrition={'calories': 420})
        self.assertEqual(self._candidates(recipe)[0]['calories'], 420)

    def test_missing_nutrition_stays_none(self):
        recipe = make_recipe(name_cs='Bez hodnot', base_servings=2, base_nutrition={})
        self.assertIsNone(self._candidates(recipe)[0]['calories'])
