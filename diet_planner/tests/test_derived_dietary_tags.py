"""Prompt-stated dietary restrictions must bind every machine gate.

Regression for the 2026-08-09 prod QA finding: a plan whose prompt said
"vegetariánská strava" offered 3/3 meat swap candidates, because the restriction
lived only in the free-text prompt and `required_tags_for_goal` never looked
there.
"""
from django.contrib.auth import get_user_model
from django.test import TestCase

from diet_planner.models import DietaryGoal
from diet_planner.services.recipe_retrieval import (
    eligible_recipes_for_slot,
    parse_derived_dietary_tags,
    published_pool,
    required_tags_for_goal,
    store_derived_dietary_tags,
)
from diet_planner.tests.test_recipe_replace import make_recipe

VEG_PROMPT = 'Chci jíst zdravěji. vegetariánská strava. Pro 2 osoby. Max 30 minut.'


class DerivedDietaryTagsTest(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create(username='veg')
        self.goal = DietaryGoal.objects.create(
            user=self.user, prompt=VEG_PROMPT, num_days=1,
            country='CZ', currency='CZK', language_code='cs',
        )

    def test_prompt_only_restriction_is_invisible_without_the_derived_field(self):
        # The state that shipped the bug: nothing to enforce anywhere.
        self.assertEqual(self.goal.dietary_restrictions or '', '')
        self.assertEqual(required_tags_for_goal(self.goal), set())

    def test_stored_tags_become_a_hard_gate(self):
        store_derived_dietary_tags(self.goal, {'vegetarian'})
        self.goal.refresh_from_db()
        self.assertEqual(required_tags_for_goal(self.goal), {'vegetarian'})

    def test_meat_recipe_is_no_longer_eligible_for_a_vegetarian_goal(self):
        meat = make_recipe(name_cs='Čevabčiči', dietary_tags=[])
        veg = make_recipe(name_cs='Zeleninové rizoto', dietary_tags=['vegetarian'])
        store_derived_dietary_tags(self.goal, {'vegetarian'})
        self.goal.refresh_from_db()

        eligible = eligible_recipes_for_slot(
            'lunch', required_tags_for_goal(self.goal), pool=published_pool(),
            exclude_ids=set(), facets=None,
        )
        names = {r.name_cs for r in eligible}
        self.assertIn(veg.name_cs, names)
        self.assertNotIn(meat.name_cs, names)

    def test_storing_only_ever_adds(self):
        # A flaky extraction must not drop a restriction the goal already has.
        store_derived_dietary_tags(self.goal, {'vegetarian'})
        store_derived_dietary_tags(self.goal, {'gluten_free'})
        self.goal.refresh_from_db()
        self.assertEqual(required_tags_for_goal(self.goal), {'vegetarian', 'gluten_free'})

    def test_unenforceable_and_junk_tags_are_dropped(self):
        store_derived_dietary_tags(self.goal, {'high_protein', 'paleo', 'vegan', ''})
        self.goal.refresh_from_db()
        self.assertEqual(required_tags_for_goal(self.goal), {'vegan'})

    def test_empty_extraction_writes_nothing(self):
        store_derived_dietary_tags(self.goal, set())
        self.goal.refresh_from_db()
        self.assertFalse(self.goal.derived_dietary_tags)

    def test_unsaved_goal_is_not_written(self):
        ghost = DietaryGoal(user=self.user, prompt=VEG_PROMPT)
        store_derived_dietary_tags(ghost, {'vegan'})  # must not raise
        self.assertIsNone(ghost.pk)

    def test_derived_parsing_is_exact_not_substring(self):
        # parse_dietary_tags maps the substring 'sacharid' onto low_carb, which
        # any sentence mentioning sacharidy trips. The derived field must not
        # inherit that: it holds exact slugs only.
        self.assertEqual(parse_derived_dietary_tags('vegetarian,gluten_free'),
                         {'vegetarian', 'gluten_free'})
        self.assertEqual(parse_derived_dietary_tags('sacharidy, zdravě'), set())
        self.assertEqual(parse_derived_dietary_tags(None), set())

    def test_profile_and_prompt_restrictions_union(self):
        from login_app.models import UserProfile
        UserProfile.objects.update_or_create(
            user=self.user,
            defaults={'dietary_preferences': {'dietary_styles': ['gluten_free']}},
        )
        store_derived_dietary_tags(self.goal, {'vegetarian'})
        self.goal.refresh_from_db()
        self.assertEqual(required_tags_for_goal(self.goal), {'vegetarian', 'gluten_free'})
