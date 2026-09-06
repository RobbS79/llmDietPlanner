"""Tests for the recipe-grounding retrieval layer (B3)."""
from types import SimpleNamespace

from django.test import TestCase

from diet_planner.models import CuratedRecipe
from diet_planner.services.recipe_retrieval import (
    _calorie_targets_from_days,
    eligible_recipes_for_slot,
    overlay_curated_recipes,
    parse_dietary_tags,
    required_tags_for_goal,
    scale_recipe_to_meal,
    score_recipe,
    select_recipes_for_plan,
    slot_target,
)


def make_recipe(**kw):
    defaults = dict(
        name_cs=kw.pop('name_cs', 'Test dish'),
        status=CuratedRecipe.Status.PUBLISHED,
        meal_types=['lunch', 'dinner'],
        dietary_tags=[],
        cuisine='czech',
        difficulty=CuratedRecipe.Difficulty.EASY,
        ingredients=[{'name': 'rýže', 'quantity': 100, 'unit': 'g', 'canonical': 'rice-basmati'}],
        instructions=[{'text': 'Uvař rýži.', 'time_min': 10, 'tip': None}],
        base_servings=1,
        base_nutrition={'calories': 500, 'protein': 30, 'carbs': 60, 'fat': 12},
        source_url='https://example.test/r',
        source_name='Example',
    )
    defaults.update(kw)
    return CuratedRecipe.objects.create(**defaults)


def goal(**kw):
    base = dict(
        id=1, num_days=1, breakfast=True, lunch=True, dinner=True,
        small_meals_per_day=0, snacks_per_day=0, dietary_restrictions='',
    )
    base.update(kw)
    return SimpleNamespace(**base)


class ParseDietaryTagsTest(TestCase):
    def test_czech_and_english_keywords(self):
        self.assertEqual(parse_dietary_tags('Jsem vegetarián'), {'vegetarian'})
        self.assertIn('vegan', parse_dietary_tags('vegan diet'))
        self.assertIn('gluten_free', parse_dietary_tags('bezlepková dieta, celiakie'))
        self.assertEqual(parse_dietary_tags(''), set())
        self.assertEqual(parse_dietary_tags(None), set())


class RequiredTagsForGoalTest(TestCase):
    """Profile preferences must be enforced, not just collected: the effective
    gate is goal.dietary_restrictions ∪ live profile styles/allergies."""

    _seq = 0

    def _goal(self, prefs=None, restrictions=''):
        from django.contrib.auth import get_user_model
        RequiredTagsForGoalTest._seq += 1
        user = get_user_model().objects.create(username=f'tag-user-{self._seq}')
        if prefs is not None:
            profile = user.profile
            profile.dietary_preferences = prefs
            profile.save()
        return SimpleNamespace(id=1, user=user, dietary_restrictions=restrictions)

    def test_profile_style_gluten_free_is_enforced(self):
        goal = self._goal({'dietary_styles': ['gluten_free'], 'allergies': ['none']})
        self.assertEqual(required_tags_for_goal(goal), {'gluten_free'})

    def test_profile_styles_map_to_corpus_tags(self):
        goal = self._goal({'dietary_styles': ['vegetarian', 'keto']})
        self.assertEqual(required_tags_for_goal(goal), {'vegetarian', 'low_carb'})

    def test_profile_allergies_map_to_corpus_tags(self):
        goal = self._goal({'dietary_styles': ['none'], 'allergies': ['lactose', 'gluten']})
        self.assertEqual(required_tags_for_goal(goal), {'dairy_free', 'gluten_free'})

    def test_high_protein_style_is_not_a_hard_gate(self):
        # A preference, not a restriction — hard-gating it would starve the pool.
        goal = self._goal({'dietary_styles': ['high_protein']})
        self.assertEqual(required_tags_for_goal(goal), set())

    def test_unenforceable_allergies_add_nothing(self):
        # No corpus tags exist for these; silently unenforced (documented gap).
        goal = self._goal({'allergies': ['nuts', 'eggs', 'fish', 'soy']})
        self.assertEqual(required_tags_for_goal(goal), set())

    def test_unions_with_restrictions_text(self):
        goal = self._goal({'dietary_styles': ['gluten_free']}, restrictions='vegan prosím')
        self.assertEqual(required_tags_for_goal(goal), {'vegan', 'gluten_free'})

    def test_goal_without_user_or_profile_falls_back_to_restrictions(self):
        bare = SimpleNamespace(id=1, dietary_restrictions='bezlepková dieta')
        self.assertEqual(required_tags_for_goal(bare), {'gluten_free'})

    def test_malformed_preferences_never_raise(self):
        goal = self._goal('not-a-dict')
        self.assertEqual(required_tags_for_goal(goal), set())
        goal2 = self._goal({'dietary_styles': 'gluten_free'})  # str, not list
        self.assertEqual(required_tags_for_goal(goal2), set())


class HardGateTest(TestCase):
    def test_excludes_wrong_meal_type(self):
        make_recipe(name_cs='A', meal_types=['breakfast'])
        self.assertEqual(eligible_recipes_for_slot('lunch', set()), [])

    def test_excludes_unpublished(self):
        make_recipe(name_cs='B', status=CuratedRecipe.Status.DRAFT)
        self.assertEqual(eligible_recipes_for_slot('lunch', set()), [])

    def test_requires_dietary_tags_superset(self):
        make_recipe(name_cs='C', dietary_tags=['vegetarian'])
        self.assertEqual(len(eligible_recipes_for_slot('lunch', {'vegetarian'})), 1)
        # recipe lacking 'vegan' is filtered out
        self.assertEqual(eligible_recipes_for_slot('lunch', {'vegan'}), [])

    def test_excludes_unmapped_ingredients(self):
        # a non-optional ingredient with no canonical/catalog_id fails the gate
        make_recipe(
            name_cs='D',
            ingredients=[{'name': 'mystery', 'quantity': 1, 'unit': 'g'}],
        )
        self.assertEqual(eligible_recipes_for_slot('lunch', set()), [])

    def test_optional_unmapped_ingredient_is_tolerated(self):
        make_recipe(
            name_cs='E',
            ingredients=[
                {'name': 'rýže', 'quantity': 100, 'unit': 'g', 'canonical': 'rice-basmati'},
                {'name': 'ozdoba', 'quantity': 1, 'unit': 'ks', 'optional': True},
            ],
        )
        self.assertEqual(len(eligible_recipes_for_slot('lunch', set())), 1)


class ScoreTest(TestCase):
    def test_repeat_recipe_is_penalised(self):
        r = make_recipe()
        fresh = score_recipe(r, used_recipe_ids=set(), used_cuisines=[])
        repeat = score_recipe(r, used_recipe_ids={r.id}, used_cuisines=[])
        self.assertLess(repeat, fresh)

    def test_calorie_proximity_rewarded(self):
        r = make_recipe(base_nutrition={'calories': 500})
        near = score_recipe(r, used_recipe_ids=set(), used_cuisines=[], target_calories=500)
        far = score_recipe(r, used_recipe_ids=set(), used_cuisines=[], target_calories=1000)
        self.assertGreater(near, far)

    def test_usage_count_does_not_affect_score(self):
        # No popularity feedback loop: a recipe served 10 times must not
        # outrank an identical recipe served never (rich-get-richer caused
        # 85% of the corpus to go unserved in prod).
        fresh = make_recipe(name_cs='Fresh dish', usage_count=0)
        popular = make_recipe(name_cs='Popular dish', usage_count=10)
        self.assertEqual(
            score_recipe(fresh, used_recipe_ids=set(), used_cuisines=[]),
            score_recipe(popular, used_recipe_ids=set(), used_cuisines=[]),
        )

    def test_ingredient_reuse_rewarded(self):
        # A recipe sharing canonicals with those already chosen scores higher,
        # so the plan converges on a smaller shopping list.
        r = make_recipe(ingredients=[
            {'name': 'kuřecí prsa', 'quantity': 150, 'unit': 'g', 'canonical': 'chicken-breast'},
            {'name': 'rýže', 'quantity': 100, 'unit': 'g', 'canonical': 'rice-basmati'},
        ])
        none = score_recipe(r, used_recipe_ids=set(), used_cuisines=[])
        shared = score_recipe(r, used_recipe_ids=set(), used_cuisines=[],
                              used_canonicals={'chicken-breast', 'rice-basmati'})
        self.assertGreater(shared, none)

    def test_select_prefers_ingredient_overlap_as_tiebreaker(self):
        # Among equally-eligible same-cuisine options for the 2nd slot, the one
        # reusing the first recipe's ingredient is chosen (overlap breaks the
        # tie without overriding the cuisine-variety penalty).
        from diet_planner.services.recipe_retrieval import select_recipes_for_plan
        # Slot eligibility fixes the first pick deterministically: chicken+rice
        # is the only lunch candidate, the two salads compete for dinner. The
        # reused option shares 5 canonicals (+3.0), outside the sampling
        # window (2.5), so the strong-reuse preference stays deterministic.
        shared = [
            {'name': n, 'quantity': 50, 'unit': 'g', 'canonical': c}
            for n, c in [
                ('kuřecí prsa', 'chicken-breast'), ('rýže', 'rice-basmati'),
                ('cibule', 'onion'), ('česnek', 'garlic'), ('máslo', 'butter'),
            ]
        ]
        make_recipe(name_cs='Kuře s rýží', cuisine='czech',
                    meal_types=['lunch'], ingredients=list(shared))
        make_recipe(name_cs='Kuřecí salát', cuisine='czech',
                    meal_types=['dinner'], ingredients=list(shared))
        make_recipe(name_cs='Zelný salát', cuisine='czech',
                    meal_types=['dinner'], ingredients=[
            {'name': 'zelí', 'quantity': 200, 'unit': 'g', 'canonical': 'cabbage'},
        ])
        result = select_recipes_for_plan(goal(num_days=1, breakfast=False))
        chosen = result['days'][0]['slots']
        cans = set()
        for r in chosen.values():
            cans |= {i['canonical'] for i in r.ingredients}
        # 2nd slot reuses chicken rather than introducing cabbage.
        self.assertIn('chicken-breast', cans)
        self.assertNotIn('cabbage', cans)


class RecentServePenaltyTest(TestCase):
    """Per-user novelty memory: recipes served to this user in recent plans
    rank lower, so regenerating doesn't produce the same menu forever."""

    def test_recently_served_scores_lower(self):
        r = make_recipe(name_cs='Polévka')
        fresh = score_recipe(r, used_recipe_ids=set(), used_cuisines=[])
        seen = score_recipe(r, used_recipe_ids=set(), used_cuisines=[],
                            recently_served_ids={r.id})
        self.assertLess(seen, fresh)

    def test_penalty_does_not_override_wanted_hit(self):
        from diet_planner.services.prompt_facets import PromptFacets
        facets = PromptFacets(wanted_ingredients={'kuřecí'})
        wanted_but_seen = make_recipe(name_cs='Kuřecí plátek', ingredients=[
            {'name': 'kuřecí prsa', 'quantity': 150, 'unit': 'g', 'canonical': 'chicken-breast'},
        ])
        fresh_no_hit = make_recipe(name_cs='Zelný salát', ingredients=[
            {'name': 'zelí', 'quantity': 200, 'unit': 'g', 'canonical': 'cabbage'},
        ])
        hit_score = score_recipe(
            wanted_but_seen, used_recipe_ids=set(), used_cuisines=[],
            facets=facets, recently_served_ids={wanted_but_seen.id})
        miss_score = score_recipe(
            fresh_no_hit, used_recipe_ids=set(), used_cuisines=[], facets=facets)
        self.assertGreater(hit_score, miss_score)

    def test_select_avoids_recently_served_when_tied(self):
        seen = make_recipe(name_cs='Včerejší jídlo', meal_types=['dinner'])
        fresh = make_recipe(name_cs='Nové jídlo', meal_types=['dinner'])
        sel = select_recipes_for_plan(
            goal(breakfast=False, lunch=False),
            recently_served_ids={seen.id})
        self.assertEqual(sel['days'][0]['slots']['dinner'].id, fresh.id)

    def test_history_helper_reads_users_recent_curated_serves(self):
        from django.contrib.auth import get_user_model
        from diet_planner.models import DietaryGoal, Recipe
        from diet_planner.services.recipe_retrieval import recently_served_curated_ids

        curated = make_recipe(name_cs='Západoafrická polévka', slug='zapadoafricka-polevka')
        user = get_user_model().objects.create_user('u1', 'u1@example.test', 'x')
        old_goal = DietaryGoal.objects.create(
            user=user, prompt='týden jídel', num_days=1,
            country='CZ', currency='CZK', language_code='cs',
        )
        Recipe.objects.create(
            meal_identifier='g:1:lunch:0', dietary_goal=old_goal,
            name='Západoafrická polévka', curated_recipe_slug='zapadoafricka-polevka',
            instructions=[], ingredients=[],
        )
        new_goal = DietaryGoal.objects.create(
            user=user, prompt='další týden', num_days=1,
            country='CZ', currency='CZK', language_code='cs',
        )
        self.assertEqual(recently_served_curated_ids(new_goal), {curated.id})
        # The goal being generated doesn't count its own (in-flight) recipes.
        self.assertEqual(recently_served_curated_ids(old_goal), set())
        # Goals without a persisted user (simulation namespaces) degrade to empty.
        self.assertEqual(recently_served_curated_ids(goal()), set())


class TopWindowSamplingTest(TestCase):
    """Near-tied candidates rotate across plans instead of a fixed argmax
    winner; dominant scores (wanted hits) still always win."""

    def _dinner_choice(self, goal_id):
        sel = select_recipes_for_plan(goal(id=goal_id, breakfast=False, lunch=False))
        return sel['days'][0]['slots']['dinner'].id

    def test_near_ties_rotate_across_goals(self):
        for i in range(4):
            make_recipe(name_cs=f'Stejné jídlo {i}', meal_types=['dinner'],
                        cuisine=['czech', 'italian', 'asian', 'mexican'][i])
        chosen = {self._dinner_choice(gid) for gid in range(1, 13)}
        self.assertGreater(len(chosen), 1)

    def test_same_goal_id_is_deterministic(self):
        for i in range(4):
            make_recipe(name_cs=f'Stejné jídlo {i}', meal_types=['dinner'],
                        cuisine=['czech', 'italian', 'asian', 'mexican'][i])
        self.assertEqual(self._dinner_choice(7), self._dinner_choice(7))

    def test_dominant_winner_always_chosen(self):
        from diet_planner.services.prompt_facets import PromptFacets
        wanted = make_recipe(name_cs='Kuřecí nudličky', meal_types=['dinner'], ingredients=[
            {'name': 'kuřecí prsa', 'quantity': 150, 'unit': 'g', 'canonical': 'chicken-breast'},
        ])
        for i in range(4):
            make_recipe(name_cs=f'Bez kuřete {i}', meal_types=['dinner'],
                        cuisine=['czech', 'italian', 'asian', 'mexican'][i])
        for gid in range(1, 13):
            sel = select_recipes_for_plan(
                goal(id=gid, breakfast=False, lunch=False),
                facets=PromptFacets(wanted_ingredients={'kuřecí'}))
            self.assertEqual(sel['days'][0]['slots']['dinner'].id, wanted.id)


class OverlayRescueTest(TestCase):
    """A hollow generated day (LLM returned nameless stubs, transform dropped
    them) must be rescued by the corpus: chosen curated recipes attach to
    empty slots instead of being discarded with the plan (prod goal 133)."""

    def _hollow_day(self):
        return [{'day_number': 1, 'small_meals': [], 'snacks': []}]

    def test_overlay_fills_empty_main_slot(self):
        from diet_planner.services.prompt_facets import PromptFacets
        make_recipe(name_cs='Záchranné jídlo', meal_types=['breakfast', 'lunch', 'dinner'])
        result = overlay_curated_recipes(self._hollow_day(), goal(), facets=PromptFacets())
        lunch = result['days'][0].get('lunch')
        self.assertIsNotNone(lunch)
        self.assertEqual(lunch['source'], 'curated')
        self.assertTrue(lunch['ingredients'])
        self.assertEqual(lunch['meal_identifier'], '1:1:lunch:0')

    def test_overlay_extends_short_meal_lists(self):
        from diet_planner.services.prompt_facets import PromptFacets
        make_recipe(name_cs='Svačinka', meal_types=['snack', 'small_meal'])
        result = overlay_curated_recipes(
            self._hollow_day(),
            goal(breakfast=False, lunch=False, dinner=False,
                 small_meals_per_day=1, snacks_per_day=1),
            facets=PromptFacets())
        day = result['days'][0]
        self.assertEqual(len(day['small_meals']), 1)
        self.assertEqual(day['small_meals'][0]['source'], 'curated')
        self.assertTrue(day['small_meals'][0]['ingredients'])

    def test_rescued_hollow_day_passes_completeness_guard(self):
        from diet_planner.services.prompt_facets import PromptFacets
        from diet_planner.tasks import _assert_plan_has_content
        make_recipe(name_cs='Záchranné jídlo', meal_types=['breakfast', 'lunch', 'dinner'])
        result = overlay_curated_recipes(self._hollow_day(), goal(), facets=PromptFacets())
        _assert_plan_has_content(result['days'], goal())  # must not raise


class SelectTest(TestCase):
    def test_fills_distinct_recipes_when_pool_allows(self):
        for i in range(3):
            make_recipe(name_cs=f'Dish {i}', meal_types=['breakfast', 'lunch', 'dinner'])
        sel = select_recipes_for_plan(goal())
        slots = sel['days'][0]['slots']
        self.assertEqual(sel['coverage'], {'filled': 3, 'total': 3})
        # breakfast/lunch/dinner each got a distinct recipe (variety penalty works)
        chosen_ids = {r.id for r in slots.values()}
        self.assertEqual(len(chosen_ids), 3)

    def test_uncovered_slot_is_absent(self):
        make_recipe(name_cs='Only lunch', meal_types=['lunch'])
        sel = select_recipes_for_plan(goal())
        slots = sel['days'][0]['slots']
        self.assertIn('lunch', slots)
        self.assertNotIn('breakfast', slots)
        self.assertEqual(sel['coverage']['filled'], 1)
        self.assertEqual(sel['coverage']['total'], 3)


class ScaleTest(TestCase):
    def test_render_shape_and_attribution(self):
        r = make_recipe(source_url='https://src.test/x', source_name='Src')
        meal = scale_recipe_to_meal(r)
        self.assertEqual(meal['name'], r.name_cs)
        self.assertEqual(meal['source'], 'curated')
        self.assertEqual(meal['curated_recipe_id'], r.id)
        self.assertEqual(meal['source_url'], 'https://src.test/x')
        self.assertEqual(meal['instructions'], ['Uvař rýži.'])
        self.assertEqual(meal['ingredients'][0]['canonical'], 'rice-basmati')

    def test_scaling_factor(self):
        r = make_recipe(
            base_nutrition={'calories': 400, 'protein': 20, 'carbs': 40, 'fat': 10},
            ingredients=[{'name': 'rýže', 'quantity': 100, 'unit': 'g', 'canonical': 'rice-basmati'}],
        )
        meal = scale_recipe_to_meal(r, factor=2.0)
        self.assertEqual(meal['ingredients'][0]['quantity'], 200)
        self.assertEqual(meal['nutritional_info']['calories'], 800)
        self.assertEqual(meal['nutritional_info']['protein'], '40g')

    def test_meal_carries_base_servings(self):
        r = make_recipe(base_servings=4)
        meal = scale_recipe_to_meal(r)
        self.assertEqual(meal['servings'], 4)

    def test_meal_servings_defaults_to_base_one(self):
        r = make_recipe(base_servings=1)
        meal = scale_recipe_to_meal(r)
        self.assertEqual(meal['servings'], 1)


class OverlayTest(TestCase):
    def _days(self):
        return [{
            'day_number': 1,
            'breakfast': {'name': 'Gen breakfast', 'meal_identifier': '1:1:breakfast:0'},
            'lunch': {'name': 'Gen lunch', 'meal_identifier': '1:1:lunch:0'},
            'dinner': {'name': 'Gen dinner', 'meal_identifier': '1:1:dinner:0'},
            'small_meals': [],
            'snacks': [],
        }]

    def test_covered_slot_replaced_uncovered_kept(self):
        make_recipe(name_cs='Real lunch', meal_types=['lunch'])
        out = overlay_curated_recipes(self._days(), goal())
        day = out['days'][0]
        # lunch overlaid with the curated recipe, identifier preserved
        self.assertEqual(day['lunch']['name'], 'Real lunch')
        self.assertEqual(day['lunch']['source'], 'curated')
        self.assertEqual(day['lunch']['meal_identifier'], '1:1:lunch:0')
        # breakfast had no eligible recipe -> kept, flagged generated
        self.assertEqual(day['breakfast']['name'], 'Gen breakfast')
        self.assertEqual(day['breakfast']['source'], 'generated')

    def test_usage_count_bumped(self):
        r = make_recipe(name_cs='Counted', meal_types=['lunch'])
        self.assertEqual(r.usage_count, 0)
        overlay_curated_recipes(self._days(), goal())
        r.refresh_from_db()
        self.assertEqual(r.usage_count, 1)


class DishRoleGateTest(TestCase):
    """Slot-fit role gate: a dish must be able to CARRY its slot, not merely be
    eatable then. A Czech oběd is a warm main — side salads, dips and breakfast
    dishes must not win lunch (prod goal 133: bean side salad served as oběd)."""

    def test_side_excluded_from_lunch(self):
        main = make_recipe(name_cs='Kuřecí s rýží', dish_role=CuratedRecipe.DishRole.MAIN)
        make_recipe(name_cs='Fazolový salát', dish_role=CuratedRecipe.DishRole.SIDE)
        elig = eligible_recipes_for_slot('lunch', set())
        self.assertEqual([r.id for r in elig], [main.id])

    def test_light_dish_allowed_for_dinner_but_not_lunch(self):
        om = make_recipe(name_cs='Omeleta', dish_role=CuratedRecipe.DishRole.LIGHT)
        self.assertEqual(eligible_recipes_for_slot('lunch', set()), [])
        self.assertEqual([r.id for r in eligible_recipes_for_slot('dinner', set())], [om.id])

    def test_soup_allowed_for_dinner_but_not_lunch_or_breakfast(self):
        soup = make_recipe(
            name_cs='Hrachová polévka', meal_types=['breakfast', 'lunch', 'dinner'],
            dish_role=CuratedRecipe.DishRole.SOUP)
        self.assertEqual(eligible_recipes_for_slot('lunch', set()), [])
        self.assertEqual(eligible_recipes_for_slot('breakfast', set()), [])
        self.assertEqual([r.id for r in eligible_recipes_for_slot('dinner', set())], [soup.id])

    def test_untagged_role_passes_everywhere(self):
        r = make_recipe(name_cs='Legacy dish', meal_types=['breakfast', 'lunch', 'dinner'])
        for slot in ('breakfast', 'lunch', 'dinner'):
            self.assertEqual([x.id for x in eligible_recipes_for_slot(slot, set())], [r.id])

    def test_side_ok_for_small_meal_and_snack(self):
        side = make_recipe(
            name_cs='Černofazolový dip', meal_types=['small_meal', 'snack'],
            dish_role=CuratedRecipe.DishRole.SIDE)
        self.assertIn(side.id, [r.id for r in eligible_recipes_for_slot('small_meal', set())])
        self.assertIn(side.id, [r.id for r in eligible_recipes_for_slot('snack', set())])

    def test_supper_allowed_for_dinner_only(self):
        leco = make_recipe(
            name_cs='Lečo', meal_types=['breakfast', 'lunch', 'dinner'],
            dish_role=CuratedRecipe.DishRole.SUPPER)
        self.assertEqual(eligible_recipes_for_slot('lunch', set()), [])
        self.assertEqual(eligible_recipes_for_slot('breakfast', set()), [])
        self.assertEqual([r.id for r in eligible_recipes_for_slot('dinner', set())], [leco.id])

    def test_breakfast_role_allowed_for_breakfast_only(self):
        kase = make_recipe(
            name_cs='Ovesná kaše', meal_types=['breakfast', 'lunch', 'dinner'],
            dish_role=CuratedRecipe.DishRole.BREAKFAST)
        self.assertEqual([r.id for r in eligible_recipes_for_slot('breakfast', set())], [kase.id])
        self.assertEqual(eligible_recipes_for_slot('lunch', set()), [])
        self.assertEqual(eligible_recipes_for_slot('dinner', set()), [])

    def test_main_no_longer_carries_breakfast(self):
        make_recipe(
            name_cs='Guláš', meal_types=['breakfast', 'lunch', 'dinner'],
            dish_role=CuratedRecipe.DishRole.MAIN)
        self.assertEqual(eligible_recipes_for_slot('breakfast', set()), [])

    def test_legacy_light_still_passes_breakfast_and_dinner(self):
        om = make_recipe(
            name_cs='Omeleta', meal_types=['breakfast', 'lunch', 'dinner'],
            dish_role=CuratedRecipe.DishRole.LIGHT)
        self.assertEqual([r.id for r in eligible_recipes_for_slot('breakfast', set())], [om.id])
        self.assertEqual([r.id for r in eligible_recipes_for_slot('dinner', set())], [om.id])
        self.assertEqual(eligible_recipes_for_slot('lunch', set()), [])

    def test_meal_types_still_gates_new_roles(self):
        make_recipe(
            name_cs='Lečo bez večeře', meal_types=['lunch'],
            dish_role=CuratedRecipe.DishRole.SUPPER)
        self.assertEqual(eligible_recipes_for_slot('lunch', set()), [])
        self.assertEqual(eligible_recipes_for_slot('dinner', set()), [])

    def test_lunch_relaxes_when_no_mains_exist(self):
        """'Unless nothing else exists': an all-sides pool still fills the slot
        rather than starving the plan, and the relaxation is recorded as a
        corpus gap so acquisition can react."""
        side = make_recipe(name_cs='Jen salát', dish_role=CuratedRecipe.DishRole.SIDE)
        sel = select_recipes_for_plan(goal(breakfast=False, dinner=False))
        self.assertEqual(sel['days'][0]['slots']['lunch'].id, side.id)
        self.assertEqual(sel['gaps'][0]['reason'], 'role_relaxed')
        self.assertEqual(sel['coverage']['filled'], 1)


class SuspectFacetsOverlayTest(TestCase):
    """When facet extraction is `suspect` (substantive prompt, empty facets),
    the generated plan is the ONLY prompt-aware artifact — the overlay must
    keep generated meals and only rescue genuinely empty slots."""

    def test_suspect_keeps_generated_mains_but_rescues_empty(self):
        from diet_planner.services.prompt_facets import PromptFacets
        make_recipe(name_cs='Kandidát', meal_types=['lunch', 'dinner'])
        days = [{
            'day_number': 1,
            'lunch': {'name': 'Gen lunch', 'meal_identifier': '1:1:lunch:0'},
            'small_meals': [], 'snacks': [],
        }]
        facets = PromptFacets()
        facets.suspect = True
        out = overlay_curated_recipes(days, goal(breakfast=False), facets=facets)
        day = out['days'][0]
        self.assertEqual(day['lunch']['name'], 'Gen lunch')      # kept, not overridden
        self.assertEqual(day['lunch']['source'], 'generated')
        self.assertEqual(day['dinner']['source'], 'curated')     # empty slot still rescued

    def test_suspect_keeps_generated_list_items_but_appends_missing(self):
        from diet_planner.services.prompt_facets import PromptFacets
        make_recipe(name_cs='Svačina k záchraně', meal_types=['small_meal'])
        days = [{
            'day_number': 1,
            'small_meals': [{'name': 'Gen svačina', 'meal_identifier': '1:1:small_meal:0'}],
            'snacks': [],
        }]
        facets = PromptFacets()
        facets.suspect = True
        out = overlay_curated_recipes(
            days,
            goal(breakfast=False, lunch=False, dinner=False, small_meals_per_day=2),
            facets=facets)
        meals = out['days'][0]['small_meals']
        self.assertEqual(meals[0]['name'], 'Gen svačina')        # kept
        self.assertEqual(meals[0]['source'], 'generated')
        self.assertEqual(meals[1]['source'], 'curated')          # appended rescue


class PerPortionScoringTest(TestCase):
    """base_nutrition is WHOLE-RECIPE (per base_servings). Scoring must compare
    per-portion calories to the slot target — comparing totals made a 2-serving
    side salad look like a perfect 600-kcal lunch while a 4-serving main
    scored zero (goal 133)."""

    def test_per_portion_fit_beats_whole_recipe_total_fit(self):
        side = make_recipe(name_cs='Salát malý', base_servings=2,
                           base_nutrition={'calories': 613})   # 307/portion
        main = make_recipe(name_cs='Kuře velké', base_servings=4,
                           base_nutrition={'calories': 2400})  # 600/portion
        kw = dict(used_recipe_ids=set(), used_cuisines=[], target_calories=600.0)
        self.assertGreater(score_recipe(main, **kw), score_recipe(side, **kw))


class PortionServingTest(TestCase):
    """The overlay must serve a portion sized to the slot, not the whole
    recipe (prod goal 133: a 6-serving, 1709-kcal salad rendered as one
    dinner)."""

    def test_scale_by_portions(self):
        r = make_recipe(name_cs='Velký hrnec', base_servings=4,
                        base_nutrition={'calories': 2000, 'protein': 100, 'carbs': 200, 'fat': 40},
                        ingredients=[{'name': 'rýže', 'quantity': 400, 'unit': 'g',
                                      'canonical': 'rice-basmati'}])
        meal = scale_recipe_to_meal(r, portions=1)
        self.assertEqual(meal['servings'], 1)
        self.assertEqual(meal['nutritional_info']['calories'], 500)
        self.assertEqual(meal['ingredients'][0]['quantity'], 100)

    def test_overlay_serves_target_sized_portion(self):
        make_recipe(name_cs='Cizrnový salát velký', meal_types=['lunch'], base_servings=6,
                    base_nutrition={'calories': 1709, 'protein': 60, 'carbs': 150, 'fat': 90},
                    ingredients=[{'name': 'cizrna', 'quantity': 600, 'unit': 'g',
                                  'canonical': 'chickpeas'}])
        days = [{
            'day_number': 1,
            'lunch': {'name': 'Gen lunch', 'meal_identifier': '1:1:lunch:0',
                      'nutritional_info': {'calories': 600}},
            'small_meals': [], 'snacks': [],
        }]
        out = overlay_curated_recipes(days, goal(breakfast=False, dinner=False))
        lunch = out['days'][0]['lunch']
        # 1709/6 ≈ 285 kcal/portion; two portions ≈ 570 kcal fits the 600 slot.
        self.assertEqual(lunch['servings'], 2)
        self.assertEqual(lunch['nutritional_info']['calories'], round(1709 / 6 * 2))
        self.assertEqual(lunch['ingredients'][0]['quantity'], round(600 * 2 / 6, 2))

    def test_overlay_sizes_rescue_by_slot_default_when_no_target(self):
        make_recipe(name_cs='Rescue kotlík', meal_types=['lunch'], base_servings=4,
                    base_nutrition={'calories': 2000, 'protein': 100, 'carbs': 200, 'fat': 40})
        days = [{'day_number': 1, 'small_meals': [], 'snacks': []}]  # hollow: no target
        out = overlay_curated_recipes(days, goal(breakfast=False, dinner=False))
        lunch = out['days'][0]['lunch']
        # 500 kcal/portion vs the 650-kcal lunch default → one portion.
        self.assertEqual(lunch['servings'], 1)
        self.assertEqual(lunch['nutritional_info']['calories'], 500)

    def test_portions_never_exceed_base_yield(self):
        make_recipe(name_cs='Mini jídlo', meal_types=['lunch'], base_servings=2,
                    base_nutrition={'calories': 400, 'protein': 20, 'carbs': 40, 'fat': 10})
        days = [{
            'day_number': 1,
            'lunch': {'name': 'Gen lunch', 'meal_identifier': '1:1:lunch:0',
                      'nutritional_info': {'calories': 900}},
            'small_meals': [], 'snacks': [],
        }]
        out = overlay_curated_recipes(days, goal(breakfast=False, dinner=False))
        # target wants 4.5 portions; recipe only yields 2 — serve the whole
        # recipe, never invent more food than it makes.
        self.assertEqual(out['days'][0]['lunch']['servings'], 2)
        self.assertEqual(out['days'][0]['lunch']['nutritional_info']['calories'], 400)


class CalorieTargetRobustnessTest(TestCase):
    """Gemini's nutritional_info is untrusted input: it arrives as a dict with
    numeric calories, a dict with string calories, a bare string blob, or not
    at all (prod goal 134: a string crashed attempt 1 with AttributeError; the
    unparseable shapes of attempt 2 silently dropped every target, so every
    slot fell back to one base-portion — a 16-kcal breakfast)."""

    def test_string_nutritional_info_does_not_crash_and_parses_kcal(self):
        days = [{'day_number': 1,
                 'lunch': {'name': 'X', 'nutritional_info': 'cca 650 kcal, 30 g bílkovin'},
                 'small_meals': [], 'snacks': []}]
        self.assertEqual(_calorie_targets_from_days(days)[1]['lunch'], 650.0)

    def test_string_calories_value_is_parsed(self):
        days = [{'day_number': 1,
                 'breakfast': {'name': 'X', 'nutritional_info': {'calories': '450 kcal'}},
                 'small_meals': [], 'snacks': []}]
        self.assertEqual(_calorie_targets_from_days(days)[1]['breakfast'], 450.0)

    def test_unparseable_shapes_yield_no_target(self):
        days = [{'day_number': 1,
                 'lunch': {'name': 'X', 'nutritional_info': 'vydatné jídlo'},
                 'dinner': {'name': 'Y', 'nutritional_info': {'calories': None}},
                 'small_meals': [], 'snacks': []}]
        self.assertEqual(_calorie_targets_from_days(days)[1], {})


class SlotDefaultTargetTest(TestCase):
    """When the generated plan gives no usable calorie signal for a slot, the
    overlay must fall back to a slot-sized default target — never to a single
    base-portion, which for piece-counted recipes is a fraction of a meal
    (prod goal 134: 1/12 of a muffin batch served as a 16-kcal breakfast)."""

    def test_slot_target_prefers_derived_value(self):
        self.assertEqual(slot_target({1: {'lunch': 700.0}}, 1, 'lunch'), 700.0)

    def test_slot_target_falls_back_per_slot_type(self):
        self.assertEqual(slot_target({}, 1, 'lunch'), 650.0)
        self.assertEqual(slot_target(None, 2, 'breakfast'), 450.0)
        self.assertEqual(slot_target({}, 1, 'small_meal:1'), 250.0)
        self.assertEqual(slot_target({}, 1, 'snack:0'), 250.0)

    def test_no_target_serves_slot_sized_portion_not_batch_fraction(self):
        # 12-piece batch whose base_nutrition is (bad data) 192 kcal total:
        # per-portion 16 kcal. The old no-target fallback served 1 portion =
        # 1/12 of the batch; the slot default must size the serving instead
        # (capped at the full batch).
        make_recipe(name_cs='Muffiny', meal_types=['breakfast'], base_servings=12,
                    base_nutrition={'calories': 192, 'protein': 4.5, 'carbs': 11.9, 'fat': 8.5})
        days = [{'day_number': 1, 'small_meals': [], 'snacks': []}]  # hollow: no target
        out = overlay_curated_recipes(days, goal(lunch=False, dinner=False))
        self.assertEqual(out['days'][0]['breakfast']['servings'], 12)
        self.assertEqual(out['days'][0]['breakfast']['nutritional_info']['calories'], 192)

    def test_overlay_survives_string_nutritional_info_end_to_end(self):
        make_recipe(name_cs='Oběd hlavní', meal_types=['lunch'], dish_role='main',
                    base_servings=4,
                    base_nutrition={'calories': 2000, 'protein': 100, 'carbs': 200, 'fat': 40})
        days = [{
            'day_number': 1,
            'lunch': {'name': 'Gen lunch', 'meal_identifier': '1:1:lunch:0',
                      'nutritional_info': '600 kcal'},
            'small_meals': [], 'snacks': [],
        }]
        out = overlay_curated_recipes(days, goal(breakfast=False, dinner=False))
        # 2000/4 = 500 kcal/portion; parsed 600-kcal target → 1 portion.
        self.assertEqual(out['days'][0]['lunch']['servings'], 1)
        self.assertEqual(out['days'][0]['lunch']['nutritional_info']['calories'], 500)


class PrilohaOnMealTest(TestCase):
    """The side is written INTO ingredients + nutrition so every downstream
    reader (shopping list, deals, public recipe, social facts) sees it."""

    def _leco(self, **kw):
        defaults = dict(
            name_cs='Lečo', base_servings=4,
            base_nutrition={'calories': 2000, 'protein': 80, 'carbs': 100, 'fat': 120},
            side_options=['chleb', 'brambory'], dish_role=CuratedRecipe.DishRole.SUPPER,
            meal_types=['dinner'])
        defaults.update(kw)
        return make_recipe(**defaults)

    def test_no_side_is_byte_identical_to_before(self):
        r = self._leco()
        meal = scale_recipe_to_meal(r, portions=1)
        self.assertNotIn('side', meal)
        self.assertEqual([i['name'] for i in meal['ingredients']], ['rýže'])
        self.assertEqual(meal['nutritional_info']['calories'], 500)

    def test_side_appended_as_role_side_ingredient(self):
        from diet_planner.services.priloha import SIDES
        r = self._leco()
        meal = scale_recipe_to_meal(r, portions=2, side=SIDES['chleb'])
        last = meal['ingredients'][-1]
        self.assertEqual(last['role'], 'side')
        self.assertEqual(last['name'], 'chléb')
        self.assertEqual(last['quantity'], 160.0)
        self.assertEqual(last['canonical'], 'bread-loaf')
        self.assertNotIn('role', meal['ingredients'][0])

    def test_side_counted_in_nutrition(self):
        from diet_planner.services.priloha import SIDES
        r = self._leco()
        meal = scale_recipe_to_meal(r, portions=2, side=SIDES['chleb'])
        self.assertEqual(meal['nutritional_info']['calories'], 1000 + 400)
        self.assertEqual(meal['nutritional_info']['carbs'], '126g')  # 50 + 76

    def test_meal_carries_side_meta(self):
        from diet_planner.services.priloha import SIDES
        meal = scale_recipe_to_meal(self._leco(), portions=1, side=SIDES['chleb'])
        self.assertEqual(meal['side'], {
            'key': 'chleb', 'name_cs': 'chléb', 'with_cs': 's chlebem', 'display': '2 krajíce'})

    def test_portions_for_target_counts_the_side(self):
        from diet_planner.services.priloha import SIDES
        from diet_planner.services.recipe_retrieval import portions_for_target
        r = self._leco()  # 500 kcal/portion; chléb adds 200
        self.assertEqual(portions_for_target(r, 1400), 3)
        self.assertEqual(portions_for_target(r, 1400, side=SIDES['chleb']), 2)

    def test_render_curated_meal_attaches_allowed_side(self):
        from diet_planner.services.recipe_retrieval import render_curated_meal
        meal, gap = render_curated_meal(self._leco(), target_kcal=700, required_tags=set())
        self.assertEqual(meal['side']['key'], 'chleb')
        self.assertIsNone(gap)

    def test_render_curated_meal_respects_diet(self):
        from diet_planner.services.recipe_retrieval import render_curated_meal
        meal, gap = render_curated_meal(self._leco(), target_kcal=700, required_tags={'gluten_free'})
        self.assertEqual(meal['side']['key'], 'brambory')
        self.assertIsNone(gap)

    def test_render_curated_meal_reports_unavailable_side(self):
        from diet_planner.services.recipe_retrieval import render_curated_meal
        r = self._leco(side_options=['chleb', 'knedlik'])
        meal, gap = render_curated_meal(r, target_kcal=700, required_tags={'gluten_free'})
        self.assertNotIn('side', meal)
        self.assertEqual(gap, 'side_unavailable')

    def test_render_curated_meal_no_options_no_gap(self):
        from diet_planner.services.recipe_retrieval import render_curated_meal
        meal, gap = render_curated_meal(self._leco(side_options=[]), target_kcal=700, required_tags=set())
        self.assertNotIn('side', meal)
        self.assertIsNone(gap)
