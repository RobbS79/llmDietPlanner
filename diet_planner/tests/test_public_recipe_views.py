"""Public showcase list: newest-per-name dedupe and slug/name consistency."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from diet_planner.models import DietaryGoal, Recipe


INSTRUCTIONS = [
    'Nakrájejte kuřecí prsa na plátky a osolte je ze všech stran.',
    'Obalte je ve strouhance a smažte dozlatova, poté zapečte se sýrem.',
    'Podávejte s rajčatovou omáčkou a čerstvou bazalkou navrchu.',
]


class PublicRecipeListDedupeTest(TestCase):
    def setUp(self):
        user = get_user_model().objects.create(username='chef')
        self.goal = DietaryGoal.objects.create(
            user=user, prompt='týden jídel', num_days=1,
            country='CZ', currency='CZK', language_code='cs',
        )
        self.client = APIClient()

    def _recipe(self, name, ident):
        return Recipe.objects.create(
            meal_identifier=ident, dietary_goal=self.goal, name=name,
            servings=4, instructions=INSTRUCTIONS,
            ingredients=[{'name': 'kuřecí prsa', 'quantity': 400, 'unit': 'g'}],
        )

    def test_duplicate_names_collapse_to_newest_row(self):
        older = self._recipe('Kuřecí parmigiana', 'g:1:lunch:0')
        newer = self._recipe('Kuřecí parmigiana', 'g:2:lunch:0')
        other = self._recipe('Hovězí guláš', 'g:3:lunch:0')

        resp = self.client.get('/api/recipes/public/')
        results = resp.data['data']['results']
        ids = {r['id'] for r in results}

        self.assertEqual(len(results), 2)
        self.assertIn(newer.pk, ids)
        self.assertIn(other.pk, ids)
        self.assertNotIn(older.pk, ids)
        self.assertEqual(resp.data['data']['count'], 2)

    def test_slug_follows_a_renamed_recipe(self):
        recipe = self._recipe('Ovesná kaše', 'g:1:breakfast:0')
        self.assertEqual(recipe.slug, 'ovesna-kase')

        recipe.name = 'Západoafrická arašídová polévka'
        recipe.save()

        recipe.refresh_from_db()
        self.assertEqual(recipe.slug, 'zapadoafricka-arasidova-polevka')

    def test_slug_follows_update_or_create_rewrite(self):
        # update_or_create saves with update_fields limited to the defaults
        # keys (Django ≥4.2) — the slug save() recomputes must still persist,
        # or a reused row keeps the previous dish's slug in its public URL.
        self._recipe('Thajský okurkový salát', 'g:1:lunch:0')

        recipe, created = Recipe.objects.update_or_create(
            meal_identifier='g:1:lunch:0',
            defaults=dict(
                dietary_goal=self.goal, name='Menemen',
                servings=4, instructions=INSTRUCTIONS,
                ingredients=[{'name': 'vejce', 'quantity': 4, 'unit': 'ks'}],
            ),
        )

        self.assertFalse(created)
        recipe.refresh_from_db()
        self.assertEqual(recipe.name, 'Menemen')
        self.assertEqual(recipe.slug, 'menemen')

    def test_publish_promotion_survives_update_or_create(self):
        thin = Recipe.objects.create(
            meal_identifier='g:1:dinner:0', dietary_goal=self.goal,
            name='Kostka čokolády', instructions=['Snězte kousek čokolády.'],
        )
        self.assertFalse(thin.is_public)

        recipe, _ = Recipe.objects.update_or_create(
            meal_identifier='g:1:dinner:0',
            defaults=dict(
                dietary_goal=self.goal, name='Kuřecí parmigiana',
                servings=4, instructions=INSTRUCTIONS,
                ingredients=[{'name': 'kuřecí prsa', 'quantity': 400, 'unit': 'g'}],
            ),
        )

        recipe.refresh_from_db()
        self.assertTrue(recipe.is_public)
