"""Shopping difficulty in retrieval: a hard gate plus a small soft penalty."""
from django.test import TestCase, override_settings

from diet_planner.models import CuratedRecipe
from diet_planner.models.catalog import Availability
from diet_planner.services.recipe_retrieval import eligible_recipes_for_slot, score_recipe


def _recipe(slug, difficulty=Availability.COMMON, blockers=None, **kw):
    defaults = dict(
        slug=slug, name_cs=slug, meal_types=['dinner'], base_servings=2,
        source_url=f'https://example.com/{slug}', source_name='Example',
        status=CuratedRecipe.Status.PUBLISHED,
        shopping_difficulty=difficulty, shopping_blockers=blockers or [],
        ingredients=[{'name': 'sůl', 'canonical': 'salt', 'quantity': 5,
                      'unit': 'g', 'catalog_id': 1}],
        instructions=[{'text': 'Uvařte.'}],
    )
    defaults.update(kw)
    return CuratedRecipe.objects.create(**defaults)


class EligibilityTests(TestCase):
    def test_specialty_is_excluded(self):
        common = _recipe('easy-dish')
        _recipe('hard-dish', difficulty=Availability.SPECIALTY, blockers=['tahini'])
        out = eligible_recipes_for_slot(
            'dinner', set(), pool=list(CuratedRecipe.objects.all()),
            enforce_mapping=False)
        self.assertEqual([r.slug for r in out], [common.slug])

    def test_findable_stays_eligible(self):
        _recipe('findable-dish', difficulty=Availability.FINDABLE,
                blockers=['maple-syrup'])
        out = eligible_recipes_for_slot(
            'dinner', set(), pool=list(CuratedRecipe.objects.all()),
            enforce_mapping=False)
        self.assertEqual(len(out), 1)

    def test_unrated_stays_eligible(self):
        """`unrated` is the model default, so gating it would empty the pool
        for every fixture and every not-yet-recomputed row."""
        _recipe('unrated-dish', difficulty=Availability.UNRATED)
        out = eligible_recipes_for_slot(
            'dinner', set(), pool=list(CuratedRecipe.objects.all()),
            enforce_mapping=False)
        self.assertEqual(len(out), 1)


class PenaltyTests(TestCase):
    def _score(self, recipe):
        return score_recipe(recipe, used_recipe_ids=set(), used_cuisines=[])

    @override_settings(AVAILABILITY_RANKING_ENABLED=True)
    def test_blocker_costs_one_point_each(self):
        common = _recipe('a')
        findable = _recipe('b', difficulty=Availability.FINDABLE,
                           blockers=['maple-syrup'])
        self.assertAlmostEqual(self._score(common) - self._score(findable), 1.0)

    @override_settings(AVAILABILITY_RANKING_ENABLED=True)
    def test_penalty_is_capped(self):
        common = _recipe('a')
        many = _recipe('b', difficulty=Availability.FINDABLE,
                       blockers=['x', 'y', 'z', 'w', 'v'])
        self.assertAlmostEqual(self._score(common) - self._score(many), 3.0)

    @override_settings(AVAILABILITY_RANKING_ENABLED=True)
    def test_unrated_without_blockers_is_not_penalised(self):
        """The rollup never writes 'unrated', so a row carrying it has simply
        not been recomputed — it must not lose rank for that."""
        common = _recipe('a')
        unrated = _recipe('b', difficulty=Availability.UNRATED)
        self.assertAlmostEqual(self._score(common), self._score(unrated))

    @override_settings(AVAILABILITY_RANKING_ENABLED=False)
    def test_flag_off_means_no_penalty(self):
        common = _recipe('a')
        findable = _recipe('b', difficulty=Availability.FINDABLE,
                           blockers=['maple-syrup'])
        self.assertAlmostEqual(self._score(common), self._score(findable))
