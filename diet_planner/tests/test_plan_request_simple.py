from types import SimpleNamespace

from django.test import TestCase
from pydantic import ValidationError

from diet_planner.models import CuratedRecipe
from diet_planner.schemas import DietaryGoalCreateRequest
from diet_planner.services.recipe_retrieval import select_recipes_for_pool


def _r(slug, meal_types=('dinner',), dietary_tags=(), status=CuratedRecipe.Status.PUBLISHED):
    return CuratedRecipe.objects.create(
        slug=slug, name_cs=slug, meal_types=list(meal_types), dish_role='main',
        dietary_tags=list(dietary_tags),
        ingredients=[{'name': 'rýže', 'canonical': 'rice'}], instructions=['x'],
        source_url='https://e.com', source_name='E', status=status)


def _goal(pins, **counts):
    base = dict(breakfasts=0, lunches=0, dinners=0, small_meals=0, snacks=0)
    base.update(counts)
    return SimpleNamespace(pk=1, id=1, dietary_restrictions='', prompt='', user=None,
                           derived_dietary_tags='', pinned_recipe_ids=pins, **base)


class SimplePlanRequestTest(TestCase):
    def test_city_optional_country_defaults(self):
        req = DietaryGoalCreateRequest(prompt='5 večeří na týden', dinners=5)
        self.assertEqual(req.city, '')
        self.assertEqual(req.country.value, 'CZ')
        self.assertEqual(req.language_code, 'cs')
        self.assertEqual(req.pinned_recipe_ids, [])

    def test_explicit_city_country_still_accepted(self):
        req = DietaryGoalCreateRequest(prompt='5 večeří na týden', dinners=5, country='SK', city='Bratislava')
        self.assertEqual(req.country.value, 'SK')
        self.assertEqual(req.city, 'Bratislava')

    def test_pinned_ids_capped(self):
        with self.assertRaises(ValidationError):
            DietaryGoalCreateRequest(prompt='5 večeří na týden', dinners=5, pinned_recipe_ids=list(range(13)))

    def test_pinned_recipes_fill_first(self):
        recipes = [_r(f'r{i}') for i in range(4)]
        out = select_recipes_for_pool(_goal([recipes[3].id], dinners=3))
        ids = [m['recipe'].id for m in out['meals']]
        self.assertEqual(ids[0], recipes[3].id)
        self.assertEqual(len(set(ids)), 3)
        self.assertEqual(out['coverage'], {'filled': 3, 'total': 3})

    def test_pin_only_fills_a_slot_it_supports(self):
        breakfast = _r('snidane', meal_types=['breakfast'])
        dinners = [_r(f'd{i}') for i in range(2)]
        out = select_recipes_for_pool(_goal([breakfast.id], dinners=2))
        ids = {m['recipe'].id for m in out['meals']}
        self.assertNotIn(breakfast.id, ids)
        self.assertEqual(ids, {d.id for d in dinners})

    def test_duplicate_pin_used_once(self):
        recipes = [_r(f'r{i}') for i in range(3)]
        pid = recipes[0].id
        out = select_recipes_for_pool(_goal([pid, pid, pid], dinners=3))
        ids = [m['recipe'].id for m in out['meals']]
        self.assertEqual(ids.count(pid), 1)
        self.assertEqual(len(set(ids)), 3)

    def test_unpublished_or_unknown_pin_ignored(self):
        draft = _r('draft', status=CuratedRecipe.Status.DRAFT)
        published = [_r(f'r{i}') for i in range(2)]
        out = select_recipes_for_pool(_goal([draft.id, 999999], dinners=2))
        ids = {m['recipe'].id for m in out['meals']}
        self.assertEqual(ids, {r.id for r in published})

    def test_pin_violating_dietary_gate_ignored(self):
        meat = _r('maso')
        veg = [_r(f'v{i}', dietary_tags=['vegetarian']) for i in range(2)]
        goal = _goal([meat.id], dinners=2)
        goal.derived_dietary_tags = 'vegetarian'
        out = select_recipes_for_pool(goal)
        ids = {m['recipe'].id for m in out['meals']}
        self.assertNotIn(meat.id, ids)
        self.assertEqual(ids, {v.id for v in veg})
