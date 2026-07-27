"""Web recipe acquisition: models, source discovery, research job runner.

Spec: docs/superpowers/specs/2026-07-27-chat-recipe-acquisition-design.md.
"""
from django.contrib.auth import get_user_model
from django.test import TestCase

from diet_planner.models import CuratedRecipe, RecipeResearchJob
from diet_planner.tests.test_recipe_replace import make_recipe


class ChatWebFieldsTest(TestCase):
    def test_defaults_keep_existing_rows_curated_and_ownerless(self):
        r = make_recipe(name_cs='Obyčejný guláš')
        self.assertEqual(r.origin, CuratedRecipe.Origin.CURATED)
        self.assertIsNone(r.created_for_user)

    def test_chat_web_draft_carries_owner(self):
        user = get_user_model().objects.create(username='hledac')
        r = make_recipe(
            name_cs='Web nález', status=CuratedRecipe.Status.DRAFT,
            origin=CuratedRecipe.Origin.CHAT_WEB, created_for_user=user,
        )
        self.assertEqual(r.created_for_user, user)
        self.assertEqual(user.chat_recipes.count(), 1)


class RecipeResearchJobModelTest(TestCase):
    def test_lifecycle_fields(self):
        user = get_user_model().objects.create(username='hledac2')
        job = RecipeResearchJob.objects.create(
            user=user, meal_identifier='1:1:lunch:0', query='pravé thajské curry',
        )
        self.assertEqual(job.status, RecipeResearchJob.Status.QUEUED)
        self.assertIsNone(job.result_recipe)
        self.assertEqual(job.fail_reason, '')
        self.assertEqual(job.reply_text, '')
