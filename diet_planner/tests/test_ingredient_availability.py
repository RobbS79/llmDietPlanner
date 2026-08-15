"""Availability rating: model defaults and the pure rollup."""
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from diet_planner.models import Availability, CanonicalIngredient, CuratedRecipe
from diet_planner.services.ingredient_availability import (
    availability_index,
    compute_shopping_difficulty,
    unshoppable_ingredients,
)
from diet_planner.tests.factories import make_canonical


class AvailabilityFieldTest(TestCase):
    def test_new_canonical_defaults_to_unrated(self):
        ci = CanonicalIngredient.objects.create(
            name='tahini', name_cs='tahini', slug='tahini',
        )
        ci.refresh_from_db()
        self.assertEqual(ci.availability, Availability.UNRATED)
        self.assertEqual(ci.availability_note, '')

    def test_availability_note_is_optional_free_text(self):
        ci = CanonicalIngredient.objects.create(
            name='kale', name_cs='kadeřávek', slug='kale',
            availability=Availability.FINDABLE,
            availability_note='velké Albert/Kaufland sezónně',
        )
        ci.refresh_from_db()
        self.assertEqual(ci.availability, 'findable')
        self.assertEqual(ci.availability_note, 'velké Albert/Kaufland sezónně')


class ShoppingDifficultyFieldTest(TestCase):
    def _recipe(self, **kw):
        defaults = dict(
            slug='test-dish', name_cs='Testovací jídlo',
            source_url='https://example.test/x', source_name='Example',
        )
        defaults.update(kw)
        return CuratedRecipe.objects.create(**defaults)

    def test_defaults_mean_not_yet_computed(self):
        r = self._recipe()
        self.assertEqual(r.shopping_difficulty, Availability.UNRATED)
        self.assertEqual(r.shopping_blockers, [])
        self.assertEqual(r.adaptation_note, '')
        self.assertIsNone(r.original_ingredients)

    def test_fields_round_trip(self):
        r = self._recipe(
            slug='test-dish-2',
            shopping_difficulty=Availability.SPECIALTY,
            shopping_blockers=['tahini', 'sumac'],
            adaptation_note='Upraveno pro dostupnost v českých obchodech',
            original_ingredients=[{'name': 'tahini', 'quantity': 30, 'unit': 'g'}],
        )
        r.refresh_from_db()
        self.assertEqual(r.shopping_difficulty, 'specialty')
        self.assertEqual(r.shopping_blockers, ['tahini', 'sumac'])
        self.assertEqual(r.original_ingredients[0]['name'], 'tahini')


class ComputeShoppingDifficultyTest(TestCase):
    def setUp(self):
        make_canonical('sůl', availability=Availability.COMMON)
        make_canonical('kadeřávek', availability=Availability.FINDABLE)
        make_canonical('tahini', availability=Availability.SPECIALTY)
        make_canonical('záhadná věc')  # left UNRATED on purpose

    def _ings(self, *specs):
        return [{'name': n, 'canonical': s, 'optional': o} for n, s, o in specs]

    def test_all_common_is_common_with_no_blockers(self):
        r = CuratedRecipe(ingredients=self._ings(('sůl', 'sul', False)))
        tier, blockers = compute_shopping_difficulty(r)
        self.assertEqual(tier, Availability.COMMON)
        self.assertEqual(blockers, [])

    def test_worst_ingredient_wins(self):
        r = CuratedRecipe(ingredients=self._ings(
            ('sůl', 'sul', False),
            ('kadeřávek', 'kaderavek', False),
            ('tahini', 'tahini', False),
        ))
        tier, blockers = compute_shopping_difficulty(r)
        self.assertEqual(tier, Availability.SPECIALTY)
        self.assertEqual(blockers, ['kaderavek', 'tahini'])

    def test_optional_ingredients_are_ignored(self):
        r = CuratedRecipe(ingredients=self._ings(
            ('sůl', 'sul', False),
            ('tahini', 'tahini', True),
        ))
        tier, blockers = compute_shopping_difficulty(r)
        self.assertEqual(tier, Availability.COMMON)
        self.assertEqual(blockers, [])

    def test_unrated_ingredient_ranks_as_findable_but_is_recorded(self):
        r = CuratedRecipe(ingredients=self._ings(('záhadná věc', 'zahadna-vec', False)))
        tier, blockers = compute_shopping_difficulty(r)
        self.assertEqual(tier, Availability.FINDABLE)
        self.assertEqual(blockers, ['zahadna-vec'])

    def test_rollup_never_writes_unrated(self):
        r = CuratedRecipe(ingredients=self._ings(('záhadná věc', 'zahadna-vec', False)))
        tier, _ = compute_shopping_difficulty(r)
        self.assertNotEqual(tier, Availability.UNRATED)

    def test_unresolvable_name_is_treated_as_unrated(self):
        r = CuratedRecipe(ingredients=[{'name': 'blorptium', 'quantity': 1}])
        tier, blockers = compute_shopping_difficulty(r)
        self.assertEqual(tier, Availability.FINDABLE)
        self.assertEqual(blockers, ['blorptium'])

    def test_empty_recipe_is_common(self):
        tier, blockers = compute_shopping_difficulty(CuratedRecipe(ingredients=[]))
        self.assertEqual(tier, Availability.COMMON)
        self.assertEqual(blockers, [])

    def test_plain_string_ingredients_do_not_crash(self):
        # Generated (non-corpus) meals carry bare strings; see normalize_ingredient_entries.
        r = CuratedRecipe(ingredients=['sůl', 'tahini'])
        tier, _ = compute_shopping_difficulty(r)
        self.assertEqual(tier, Availability.COMMON)

    def test_index_avoids_per_ingredient_queries(self):
        idx = availability_index()
        r = CuratedRecipe(ingredients=self._ings(('tahini', 'tahini', False)))
        with self.assertNumQueries(0):
            tier, _ = compute_shopping_difficulty(r, index=idx)
        self.assertEqual(tier, Availability.SPECIALTY)


class UnshoppableIngredientsTest(TestCase):
    def setUp(self):
        make_canonical('sůl', availability=Availability.COMMON)
        make_canonical('kadeřávek', availability=Availability.FINDABLE)
        make_canonical('tahini', availability=Availability.SPECIALTY)

    def test_specialty_and_unrated_block_findable_does_not(self):
        ings = [
            {'name': 'sůl', 'canonical': 'sul'},
            {'name': 'kadeřávek', 'canonical': 'kaderavek'},
            {'name': 'tahini', 'canonical': 'tahini'},
            {'name': 'blorptium'},
        ]
        self.assertEqual(unshoppable_ingredients(ings), ['blorptium', 'tahini'])

    def test_optional_specialty_does_not_block(self):
        ings = [{'name': 'tahini', 'canonical': 'tahini', 'optional': True}]
        self.assertEqual(unshoppable_ingredients(ings), [])


class RecomputeShoppingDifficultyTest(TestCase):
    def setUp(self):
        make_canonical('sůl', availability=Availability.COMMON)
        make_canonical('tahini', availability=Availability.SPECIALTY)

    def _recipe(self, slug, ings, status=CuratedRecipe.Status.PUBLISHED):
        return CuratedRecipe.objects.create(
            slug=slug, name_cs=slug, status=status, ingredients=ings,
            source_url=f'https://example.test/{slug}', source_name='Example',
        )

    def test_sets_difficulty_and_blockers(self):
        r = self._recipe('a', [{'name': 'tahini', 'canonical': 'tahini'}])
        call_command('recompute_shopping_difficulty', stdout=StringIO())
        r.refresh_from_db()
        self.assertEqual(r.shopping_difficulty, Availability.SPECIALTY)
        self.assertEqual(r.shopping_blockers, ['tahini'])

    def test_covers_drafts_not_just_published(self):
        r = self._recipe('b', [{'name': 'tahini', 'canonical': 'tahini'}],
                         status=CuratedRecipe.Status.DRAFT)
        call_command('recompute_shopping_difficulty', stdout=StringIO())
        r.refresh_from_db()
        self.assertEqual(r.shopping_difficulty, Availability.SPECIALTY)

    def test_dry_run_writes_nothing(self):
        r = self._recipe('c', [{'name': 'tahini', 'canonical': 'tahini'}])
        call_command('recompute_shopping_difficulty', dry_run=True, stdout=StringIO())
        r.refresh_from_db()
        self.assertEqual(r.shopping_difficulty, Availability.UNRATED)

    def test_is_idempotent(self):
        r = self._recipe('d', [{'name': 'sůl', 'canonical': 'sul'}])
        call_command('recompute_shopping_difficulty', stdout=StringIO())
        out = StringIO()
        call_command('recompute_shopping_difficulty', stdout=out)
        self.assertIn('changed=0', out.getvalue())
        r.refresh_from_db()
        self.assertEqual(r.shopping_difficulty, Availability.COMMON)
