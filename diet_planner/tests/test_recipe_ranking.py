"""
Issue #47: preferences must RANK, not GATE.

Covers the retrieval-layer rework: WantedIngredientMatcher (category /
canonical / word-boundary matching), dominant wanted weight in score_recipe,
the hard total-time gate, per-slot calorie targets, and the lunch/dinner
prompt-fit threshold with corpus-gap reporting in select_recipes_for_plan.
"""
from django.test import TestCase

from diet_planner.models import CanonicalIngredient, CuratedRecipe
from diet_planner.services.canonical_lookup import clear_cache
from diet_planner.services.prompt_facets import PromptFacets
from diet_planner.services.recipe_retrieval import (
    WantedIngredientMatcher,
    eligible_recipes_for_slot,
    overlay_curated_recipes,
    recipe_matches_facets,
    score_recipe,
    select_recipes_for_plan,
)


def _canonical(slug, category, name=None, name_cs=''):
    # update_or_create: migrations seed a real canonical catalog, so some of
    # these slugs already exist — pin the fields this test suite relies on.
    ci, _ = CanonicalIngredient.objects.update_or_create(
        slug=slug,
        defaults=dict(
            name=name or slug.replace('-', ' '), name_cs=name_cs,
            category=category,
        ),
    )
    return ci


def _recipe(slug, canonicals, **kw):
    defaults = dict(
        name_cs=slug, slug=slug,
        meal_types=['lunch', 'dinner'], cuisine='czech',
        dietary_tags=[], status=CuratedRecipe.Status.PUBLISHED,
        ingredients=[
            {'name': c.replace('-', ' '), 'canonical': c, 'quantity': 100, 'unit': 'g'}
            for c in canonicals
        ],
        instructions=[{'text': 'cook'}], base_nutrition={'calories': 500},
        source_url='https://example.com/r', source_name='Example',
    )
    defaults.update(kw)
    return CuratedRecipe.objects.create(**defaults)


class SeededTestCase(TestCase):
    """Canonical vocabulary mirroring the prod shapes from issue #47."""

    @classmethod
    def setUpTestData(cls):
        cat = CanonicalIngredient.Category
        _canonical('chicken-breast', cat.MEAT, name_cs='kuřecí prsa')
        _canonical('salmon', cat.FISH, name_cs='losos')
        _canonical('rice', cat.GRAINS, name_cs='rýže')
        _canonical('basmati-rice', cat.GRAINS, name_cs='rýže basmati')
        _canonical('rice-vinegar', cat.CONDIMENTS, name_cs='rýžový ocet')
        _canonical('cucumber', cat.VEGETABLES, name_cs='okurka')
        clear_cache()

    @classmethod
    def tearDownClass(cls):
        clear_cache()
        super().tearDownClass()


class WantedIngredientMatcherTest(SeededTestCase):
    def test_broad_category_word_matches_by_category(self):
        meat = _recipe('kureci-maso', ['chicken-breast'])
        salad = _recipe('okurkovy-salat', ['cucumber', 'rice-vinegar'])
        matcher = WantedIngredientMatcher.build({'maso'})
        self.assertEqual(matcher.hits(meat), 1)
        self.assertEqual(matcher.hits(salad), 0)

    def test_fish_category_word_in_english_and_czech(self):
        fish = _recipe('losos-recept', ['salmon'])
        for token in ('ryba', 'fish'):
            self.assertEqual(WantedIngredientMatcher.build({token}).hits(fish), 1, token)

    def test_specific_ingredient_matches_variant_same_category(self):
        # 'rýže' resolves to canonical rice (grains); basmati-rice is also
        # grains and shares the 'rice' slug token -> counts as rice.
        basmati = _recipe('basmati', ['basmati-rice'])
        matcher = WantedIngredientMatcher.build({'rýže'})
        self.assertEqual(matcher.hits(basmati), 1)

    def test_no_rice_vinegar_false_positive(self):
        # The plan-131 bug: 'rice' ⊂ 'rice-vinegar' used to count as rice.
        # rice-vinegar is condiments, not grains -> must NOT match.
        salad = _recipe('okurkovy-salat-2', ['cucumber', 'rice-vinegar'])
        for token in ('rýže', 'rice'):
            self.assertEqual(WantedIngredientMatcher.build({token}).hits(salad), 0, token)

    def test_unresolvable_token_falls_back_to_word_boundary_text_match(self):
        r = _recipe('kuskus-recept', ['cucumber'])
        r.ingredients.append({'name': 'kuskus', 'quantity': 100, 'unit': 'g'})
        r.save()
        self.assertEqual(WantedIngredientMatcher.build({'kuskus'}).hits(r), 1)
        # substring of a word must not match
        self.assertEqual(WantedIngredientMatcher.build({'kus'}).hits(r), 0)

    def test_hits_counts_distinct_concepts(self):
        r = _recipe('losos-s-ryzi', ['salmon', 'basmati-rice'])
        matcher = WantedIngredientMatcher.build({'ryba', 'rýže', 'maso'})
        self.assertEqual(matcher.hits(r), 2)  # fish + rice, no meat


class RankNotGateTest(SeededTestCase):
    def test_wanted_ingredients_no_longer_gate_eligibility(self):
        salad = _recipe('salat', ['cucumber'])
        facets = PromptFacets(wanted_ingredients={'maso'})
        self.assertTrue(recipe_matches_facets(salad, facets))
        eligible = eligible_recipes_for_slot('lunch', set(), facets=facets)
        self.assertIn(salad.id, {r.id for r in eligible})

    def test_avoided_ingredients_still_gate(self):
        salad = _recipe('salat-2', ['cucumber'])
        facets = PromptFacets(avoided_ingredients={'okurka'})
        self.assertFalse(recipe_matches_facets(salad, facets))

    def test_wanted_hit_dominates_ranking(self):
        # Worst case for the meat main: the side is easy, popular, calorie-fit
        # and shares canonicals with the plan; the main has none of that. The
        # wanted-ingredient hit must still win ("maso nebo ryba" dominates).
        side = _recipe(
            'okurkovy-salat-3', ['cucumber', 'rice-vinegar'],
            difficulty=CuratedRecipe.Difficulty.EASY, usage_count=10,
            base_nutrition={'calories': 700},
        )
        main = _recipe(
            'kureci-prsa-recept', ['chicken-breast'],
            difficulty=CuratedRecipe.Difficulty.MEDIUM, usage_count=0,
            base_nutrition={'calories': 450},
        )
        facets = PromptFacets(wanted_ingredients={'maso', 'ryba'})
        kw = dict(
            used_recipe_ids=set(), used_cuisines=[], facets=facets,
            target_calories=700.0, used_canonicals={'cucumber', 'rice-vinegar'},
        )
        self.assertGreater(score_recipe(main, **kw), score_recipe(side, **kw))


class TimeGateTest(SeededTestCase):
    def test_max_time_minutes_hard_gates_slow_recipes(self):
        _recipe('rychly', ['chicken-breast'], prep_time=10, cook_time=15)
        _recipe('pomaly', ['chicken-breast'], prep_time=15, cook_time=40)
        _recipe('bez-casu', ['chicken-breast'], prep_time=None, cook_time=None)
        facets = PromptFacets(max_time_minutes=30)
        slugs = {r.slug for r in eligible_recipes_for_slot('lunch', set(), facets=facets)}
        self.assertEqual(slugs, {'rychly', 'bez-casu'})  # unknown time passes


def _goal(**kw):
    class G:
        pass
    g = G()
    g.dietary_restrictions = kw.get('dietary_restrictions')
    g.num_days = kw.get('num_days', 1)
    g.small_meals_per_day = kw.get('small_meals_per_day', 0)
    g.snacks_per_day = kw.get('snacks_per_day', 0)
    g.breakfast = kw.get('breakfast', False)
    g.lunch = kw.get('lunch', True)
    g.dinner = kw.get('dinner', False)
    return g


class SelectFitThresholdTest(SeededTestCase):
    def test_lunch_uncovered_and_gap_reported_when_no_wanted_fit(self):
        _recipe('salat-only', ['cucumber'], meal_types=['lunch'])
        facets = PromptFacets(wanted_ingredients={'maso'})
        result = select_recipes_for_plan(_goal(), facets=facets)
        self.assertEqual(result['coverage']['filled'], 0)
        self.assertEqual(result['days'][0]['slots'], {})
        self.assertEqual(len(result['gaps']), 1)
        gap = result['gaps'][0]
        self.assertEqual(gap['slot'], 'lunch')
        self.assertEqual(gap['day_number'], 1)
        self.assertIn('maso', gap['unmatched_wanted'])

    def test_lunch_covered_when_wanted_fit_exists(self):
        _recipe('salat-b', ['cucumber'], meal_types=['lunch'])
        meat = _recipe('maso-b', ['chicken-breast'], meal_types=['lunch'])
        facets = PromptFacets(wanted_ingredients={'maso'})
        result = select_recipes_for_plan(_goal(), facets=facets)
        self.assertEqual(result['days'][0]['slots']['lunch'].id, meat.id)
        self.assertEqual(result['gaps'], [])

    def test_breakfast_not_subject_to_wanted_fit_threshold(self):
        # Wanted tokens describe the plan's mains; a meatless breakfast is fine.
        granola = _recipe('granola', ['basmati-rice'], meal_types=['breakfast'])
        facets = PromptFacets(wanted_ingredients={'maso'})
        result = select_recipes_for_plan(
            _goal(breakfast=True, lunch=False), facets=facets,
        )
        self.assertEqual(result['days'][0]['slots']['breakfast'].id, granola.id)

    def test_empty_pool_reports_gap(self):
        result = select_recipes_for_plan(_goal(), facets=PromptFacets())
        self.assertEqual(len(result['gaps']), 1)
        self.assertEqual(result['gaps'][0]['reason'], 'no_eligible_recipes')

    def test_calorie_targets_prefer_right_sized_recipe(self):
        _recipe('side-414', ['cucumber'], base_nutrition={'calories': 414},
                meal_types=['lunch'])
        main = _recipe('main-680', ['basmati-rice'], base_nutrition={'calories': 680},
                       meal_types=['lunch'])
        result = select_recipes_for_plan(
            _goal(), facets=None, calorie_targets={1: {'lunch': 700.0}},
        )
        self.assertEqual(result['days'][0]['slots']['lunch'].id, main.id)


class Plan131RegressionTest(SeededTestCase):
    """Prod plan 131 (issue #47): GF + 'maso nebo ryba, rýže, zelenina, max 30
    minut' served a side-dish cucumber salad as lunch and 45-55 min dinners.
    With rank-not-gate + category matching + the time gate, protein mains must
    win both main slots and slow / non-GF recipes must stay ineligible."""

    def _corpus(self):
        salad = _recipe(
            'thajsky-okurkovy-salat', ['cucumber', 'rice-vinegar'],
            dietary_tags=['gluten_free'], base_nutrition={'calories': 414},
            difficulty=CuratedRecipe.Difficulty.EASY, usage_count=10,
            prep_time=15, cook_time=0,
        )
        chicken = _recipe(
            'kureci-prsa-s-ryzi', ['chicken-breast', 'basmati-rice'],
            dietary_tags=['gluten_free'], base_nutrition={'calories': 650},
            difficulty=CuratedRecipe.Difficulty.MEDIUM, usage_count=0,
            prep_time=10, cook_time=15,
        )
        salmon = _recipe(
            'losos-s-ryzi', ['salmon', 'basmati-rice'],
            dietary_tags=['gluten_free'], base_nutrition={'calories': 620},
            difficulty=CuratedRecipe.Difficulty.MEDIUM, usage_count=0,
            prep_time=10, cook_time=18,
        )
        slow = _recipe(
            'pomale-maso', ['chicken-breast'],
            dietary_tags=['gluten_free'], prep_time=15, cook_time=40,
        )
        gluten = _recipe(
            'smazene-kure', ['chicken-breast'],
            dietary_tags=[], prep_time=10, cook_time=15,
        )
        return salad, chicken, salmon, slow, gluten

    def test_protein_mains_win_lunch_and_dinner(self):
        salad, chicken, salmon, slow, gluten = self._corpus()
        facets = PromptFacets(
            wanted_ingredients={'maso', 'ryba', 'rýže', 'zelenina'},
            max_time_minutes=30,
        )
        goal = _goal(dietary_restrictions='bezlepková dieta', dinner=True)
        result = select_recipes_for_plan(goal, facets=facets)

        slots = result['days'][0]['slots']
        mains = {chicken.id, salmon.id}
        self.assertIn(slots['lunch'].id, mains)
        self.assertIn(slots['dinner'].id, mains)
        self.assertNotEqual(slots['lunch'].id, slots['dinner'].id)
        # The plan-131 failure mode: the side salad must not take a main slot.
        self.assertNotIn(salad.id, {slots['lunch'].id, slots['dinner'].id})
        # Time + dietary hard gates.
        self.assertNotIn(slow.id, {slots['lunch'].id, slots['dinner'].id})
        self.assertNotIn(gluten.id, {slots['lunch'].id, slots['dinner'].id})
        self.assertEqual(result['gaps'], [])


class OverlayTargetsAndGapsTest(SeededTestCase):
    def _days(self, calories=700):
        return [{
            'day_number': 1,
            'lunch': {
                'name': 'LLM lunch', 'meal_identifier': 'g:1:lunch:0',
                'nutritional_info': {'calories': calories},
            },
        }]

    def test_overlay_derives_calorie_target_from_generated_meal(self):
        _recipe('side-o', ['cucumber'], base_nutrition={'calories': 414},
                meal_types=['lunch'])
        _recipe('main-o', ['basmati-rice'], base_nutrition={'calories': 680},
                meal_types=['lunch'])
        result = overlay_curated_recipes(self._days(700), _goal(), facets=PromptFacets())
        self.assertEqual(result['days'][0]['lunch']['name'], 'main-o')

    def test_overlay_keeps_generated_lunch_and_reports_gap_when_no_wanted_fit(self):
        _recipe('salat-o', ['cucumber'], meal_types=['lunch'])
        facets = PromptFacets(wanted_ingredients={'maso'})
        result = overlay_curated_recipes(self._days(), _goal(), facets=facets)
        lunch = result['days'][0]['lunch']
        self.assertEqual(lunch['name'], 'LLM lunch')
        self.assertEqual(lunch['source'], 'generated')
        self.assertEqual(len(result['gaps']), 1)
        self.assertEqual(result['gaps'][0]['reason'], 'wanted_fit_below_threshold')
