"""Refine endpoint v2 wiring: agent behind flag, accept-pool extension, job view.

Spec: docs/superpowers/specs/2026-07-27-chat-recipe-acquisition-design.md.
"""
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from diet_planner.models import CuratedRecipe, DietaryGoal, DietaryPlan, RecipeResearchJob
from diet_planner.services.refine_agent import AgentTurn
from diet_planner.tests.test_recipe_replace import make_recipe


class RefineAgentEndpointBase(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create(username='sefkuchar')
        self.goal = DietaryGoal.objects.create(
            user=self.user, prompt='týden jídel', num_days=1,
            country='CZ', currency='CZK', language_code='cs',
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.current = make_recipe(name_cs='Menemen', source_url='https://ex.test/menemen')
        self.other = make_recipe(name_cs='Rizoto', source_url='https://ex.test/rizoto')
        from diet_planner.services.recipe_retrieval import scale_recipe_to_meal
        meal = scale_recipe_to_meal(self.current)
        self.meal_identifier = f'{self.goal.id}:1:lunch:0'
        meal['meal_identifier'] = self.meal_identifier
        self.plan = DietaryPlan.objects.create(
            dietary_goal=self.goal,
            days=[{'day_number': 1, 'lunch': meal, 'small_meals': [], 'snacks': []}],
            currency='CZK',
        )

    def _url(self):
        return reverse('diet_planner:recipe-refine',
                       kwargs={'meal_identifier': self.meal_identifier})


@override_settings(REFINE_CHAT_AGENT_ENABLED=True)
class AgentPreviewTest(RefineAgentEndpointBase):
    @patch('diet_planner.views.run_refine_turn')
    def test_v2_response_shape(self, turn):
        turn.return_value = AgentTurn(
            reply_text='Co třeba Rizoto?', candidate=self.other, research_job_id=None,
        )
        r = self.client.post(self._url(), {
            'messages': [{'role': 'user', 'text': 'něco jiného'}], 'rejected_ids': [],
        }, format='json')
        data = r.json()['data']
        self.assertEqual(data['reply_text'], 'Co třeba Rizoto?')
        self.assertEqual(data['candidate']['curated_recipe_id'], self.other.id)
        self.assertIsNone(data['research_job_id'])

    @patch('diet_planner.views.run_refine_turn')
    def test_agent_crash_falls_back_to_v1(self, turn):
        turn.side_effect = RuntimeError('LLM down')
        with patch('diet_planner.views.refine_conversation') as v1:
            from diet_planner.services.prompt_facets import PromptFacets
            v1.return_value = (PromptFacets(), None)
            r = self.client.post(self._url(), {
                'messages': [{'role': 'user', 'text': 'něco'}], 'rejected_ids': [],
            }, format='json')
        data = r.json()['data']
        self.assertNotIn('reply_text', data)          # v1 shape
        self.assertIn('candidate', data)

    @patch('diet_planner.views.run_refine_turn')
    def test_flag_off_serves_v1(self, turn):
        with override_settings(REFINE_CHAT_AGENT_ENABLED=False):
            with patch('diet_planner.views.refine_conversation') as v1:
                from diet_planner.services.prompt_facets import PromptFacets
                v1.return_value = (PromptFacets(), None)
                self.client.post(self._url(), {
                    'messages': [{'role': 'user', 'text': 'x'}], 'rejected_ids': [],
                }, format='json')
        turn.assert_not_called()


class AcceptChatDraftTest(RefineAgentEndpointBase):
    def _chat_draft(self, owner, name='Web nález'):
        return make_recipe(
            name_cs=name, status=CuratedRecipe.Status.DRAFT,
            origin=CuratedRecipe.Origin.CHAT_WEB, created_for_user=owner,
            source_url=f'https://web.test/{name}',
            ingredients=[{'name': 'dračí ovoce', 'quantity': 1, 'unit': 'ks'}],  # unmapped
        )

    def test_own_unmapped_chat_draft_is_acceptable(self):
        draft = self._chat_draft(self.user)
        r = self.client.post(self._url(), {'accept': draft.id}, format='json')
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()['data']['replaced'])

    def test_foreign_chat_draft_is_rejected(self):
        stranger = get_user_model().objects.create(username='cizinec')
        draft = self._chat_draft(stranger, name='Cizí nález')
        r = self.client.post(self._url(), {'accept': draft.id}, format='json')
        self.assertEqual(r.status_code, 400)

    def test_ordinary_draft_still_rejected(self):
        d = make_recipe(name_cs='Neveřejný', status=CuratedRecipe.Status.DRAFT,
                        source_url='https://ex.test/nev')
        r = self.client.post(self._url(), {'accept': d.id}, format='json')
        self.assertEqual(r.status_code, 400)


class ResearchJobViewTest(RefineAgentEndpointBase):
    def _job(self, **kw):
        return RecipeResearchJob.objects.create(
            user=kw.pop('user', self.user), meal_identifier=self.meal_identifier,
            query='ramen', **kw,
        )

    def _jurl(self, job):
        return reverse('diet_planner:recipe-research-job', kwargs={'job_id': job.id})

    def test_owner_sees_status_and_ready_candidate(self):
        draft = make_recipe(name_cs='Ramen z webu', status=CuratedRecipe.Status.DRAFT,
                            origin=CuratedRecipe.Origin.CHAT_WEB,
                            created_for_user=self.user,
                            source_url='https://web.test/ramen')
        job = self._job(status=RecipeResearchJob.Status.READY,
                        result_recipe=draft, reply_text='Našel jsem: Ramen z webu.')
        r = self.client.get(self._jurl(job))
        data = r.json()['data']
        self.assertEqual(data['status'], 'ready')
        self.assertEqual(data['candidate']['curated_recipe_id'], draft.id)
        self.assertEqual(data['reply_text'], 'Našel jsem: Ramen z webu.')

    def test_pending_job_has_no_candidate(self):
        job = self._job()
        data = self.client.get(self._jurl(job)).json()['data']
        self.assertEqual(data['status'], 'queued')
        self.assertIsNone(data['candidate'])

    def test_foreign_job_404(self):
        stranger = get_user_model().objects.create(username='slidil')
        job = self._job(user=stranger)
        self.assertEqual(self.client.get(self._jurl(job)).status_code, 404)
