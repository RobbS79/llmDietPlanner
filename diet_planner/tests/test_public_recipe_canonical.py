"""One public page per recipe.

Every user plan stores its own Recipe rows and Recipe.save() auto-publishes
them, so the same corpus recipe became public several times (kulajda 31/32,
parmigiana 30/39, ...). Search Console 2026-10-29 would flag those as duplicate
content. The oldest row of a (name, source_url) group is the public one; the
copies 301 to it. Same name + different source = a different recipe, kept.
"""
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from diet_planner.models import DietaryGoal, Recipe

INSTRUCTIONS = [
    'Houby namočte, brambory oloupejte a nakrájejte na kostičky.',
    'Vše vařte ve vodě s kmínem doměkka, přidejte smetanu a koprem dochuťte.',
    'Nakonec do polévky vklepněte vejce a nechte je zastavit.',
]
_TEMPLATE = (
    '<html><head><title>x</title></head><body><!--ssr-outlet--></body></html>'
)
SRC = 'https://www.toprecepty.cz/recept/31243-kulajda/'


class PublicRecipeCanonicalTest(TestCase):
    def setUp(self):
        user = get_user_model().objects.create(username='chef')
        self.goal = DietaryGoal.objects.create(user=user, country='CZ')
        self.n = 0

    def _recipe(self, name, source_url=SRC):
        self.n += 1
        return Recipe.objects.create(
            meal_identifier=f'g:{self.n}:dinner:0', dietary_goal=self.goal,
            name=name, servings=2, instructions=INSTRUCTIONS,
            ingredients=['houby'], source_url=source_url,
        )

    def _ssr(self, url):
        with patch('llm_diet_planner_project.views._get_index_template',
                   return_value=_TEMPLATE):
            return self.client.get(url)

    def test_copy_redirects_permanently_to_oldest(self):
        first = self._recipe('Kulajda')
        copy = self._recipe('Kulajda')
        resp = self._ssr(copy.get_absolute_url())
        self.assertEqual(resp.status_code, 301)
        self.assertEqual(resp['Location'], first.get_absolute_url())
        self.assertEqual(self._ssr(first.get_absolute_url()).status_code, 200)

    def test_sitemap_lists_each_recipe_once(self):
        first = self._recipe('Kulajda')
        copy = self._recipe('Kulajda')
        body = self.client.get('/sitemap.xml').content.decode()
        self.assertIn(first.get_absolute_url(), body)
        self.assertNotIn(copy.get_absolute_url(), body)

    def test_ssr_index_lists_each_recipe_once(self):
        first = self._recipe('Kulajda')
        copy = self._recipe('Kulajda')
        body = self._ssr('/recepty/').content.decode()
        self.assertIn(first.get_absolute_url(), body)
        self.assertNotIn(copy.get_absolute_url(), body)

    def test_api_list_shows_oldest(self):
        first = self._recipe('Kulajda')
        copy = self._recipe('Kulajda')
        ids = {r['id'] for r in
               APIClient().get('/api/recipes/public/').data['data']['results']}
        self.assertEqual(ids, {first.pk})
        self.assertNotIn(copy.pk, ids)

    def test_same_name_different_source_are_different_recipes(self):
        a = self._recipe('Segedínský guláš', 'https://www.toprecepty.cz/recept/38145/')
        b = self._recipe('Segedínský guláš', 'https://www.toprecepty.cz/recept/30046/')
        self.assertEqual(self._ssr(b.get_absolute_url()).status_code, 200)
        body = self.client.get('/sitemap.xml').content.decode()
        self.assertIn(a.get_absolute_url(), body)
        self.assertIn(b.get_absolute_url(), body)

    def test_name_match_ignores_case_and_whitespace(self):
        first = self._recipe('Kulajda')
        copy = self._recipe('  kulajda ')
        self.assertEqual(self._ssr(copy.get_absolute_url())['Location'],
                         first.get_absolute_url())

    def test_renamed_oldest_row_hands_over_to_next_copy(self):
        first = self._recipe('Kulajda')
        copy = self._recipe('Kulajda')
        first.name = 'Bramboračka'
        first.save()
        self.assertEqual(self._ssr(copy.get_absolute_url()).status_code, 200)
