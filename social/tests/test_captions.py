import json

from django.test import SimpleTestCase, TestCase

from diet_planner.tests.factories import make_store
from social.captions import (
    CaptionRejected, known_recipe_names, known_shops, validate_caption, write_caption,
)

DEALS_FACTS = {
    'kind': 'deals', 'iso_week': '2026-W37',
    'deals': [{'ingredient': 'cibule', 'shop': 'Lidl', 'valid_until': '2026-09-13'},
              {'ingredient': 'mrkev', 'shop': 'Albert', 'valid_until': '2026-09-10'},
              {'ingredient': 'vepřové', 'shop': 'Lidl', 'valid_until': '2026-09-13'}],
    'recipes': [{'name': 'Vepřové s cibulí', 'url': 'https://eatalnicek.eu/recepty/1/x/',
                 'matched': 2, 'total': 4}],
    'link': 'https://eatalnicek.eu/?utm_source={channel}&utm_medium=social&utm_campaign=auto-deals-2026-W37',
}
SHOPS = {'Lidl', 'Albert', 'Kaufland'}
RECIPES = {'Vepřové s cibulí', 'Svíčková'}


class ValidateCaptionTests(SimpleTestCase):
    def test_clean_caption_passes(self):
        caption = 'Tenhle týden je v akci cibule (Lidl), mrkev (Albert) a vepřové. Vepřové s cibulí zvládnete ze 2 surovin ve slevě.'
        self.assertEqual(validate_caption(caption, DEALS_FACTS, known_shops=SHOPS,
                                          known_recipes=RECIPES), [])

    def test_number_not_in_facts_is_flagged(self):
        caption = 'Cibule v Lidlu za 9,90 Kč.'
        violations = validate_caption(caption, DEALS_FACTS, known_shops=SHOPS, known_recipes=RECIPES)
        self.assertTrue(any('9,90' in v for v in violations))

    def test_numbers_inside_the_link_are_ignored(self):
        caption = 'Více na https://eatalnicek.eu/?utm_campaign=auto-deals-2026-W37 — cibule v akci.'
        self.assertEqual(validate_caption(caption, DEALS_FACTS, known_shops=SHOPS,
                                          known_recipes=RECIPES), [])

    def test_shop_not_in_facts_is_flagged(self):
        caption = 'Cibule je v akci v Kauflandu.'
        violations = validate_caption(caption, DEALS_FACTS, known_shops=SHOPS, known_recipes=RECIPES)
        self.assertTrue(any('Kaufland' in v for v in violations))

    def test_recipe_not_in_facts_is_flagged(self):
        caption = 'Uvařte si svíčkovou z cibule.'
        violations = validate_caption(caption, DEALS_FACTS, known_shops=SHOPS, known_recipes=RECIPES)
        self.assertTrue(any('Svíčková' in v for v in violations))

    def test_banned_phrases_are_flagged(self):
        for phrase in ['Ušetříte stovky.', 'Exkluzivní slevy!', 'Nejlevnější nákup.', 'Zaručeně zhubnete.']:
            violations = validate_caption(phrase + ' cibule', DEALS_FACTS, known_shops=SHOPS,
                                          known_recipes=RECIPES)
            self.assertTrue(violations, phrase)

    def test_percentage_discount_is_flagged(self):
        violations = validate_caption('Cibule 20 % sleva.', DEALS_FACTS, known_shops=SHOPS,
                                      known_recipes=RECIPES)
        self.assertTrue(any('percentage discount' in v for v in violations))

    def test_length_limit(self):
        caption = 'cibule ' * 120
        violations = validate_caption(caption, DEALS_FACTS, known_shops=SHOPS, known_recipes=RECIPES)
        self.assertTrue(any('600' in v for v in violations))


class WriteCaptionTests(SimpleTestCase):
    def test_retries_once_with_violations_then_returns_valid_json(self):
        calls = []

        def generate(prompt):
            calls.append(prompt)
            if len(calls) == 1:
                return json.dumps({'caption': 'Cibule za 9,90 Kč v Lidlu.', 'group_variant': 'Cibule.'})
            return '```json\n' + json.dumps({'caption': 'Cibule v Lidlu je tenhle týden v akci.',
                                              'group_variant': 'Stavím appku, cibule je v akci.'}) + '\n```'
        result = write_caption(DEALS_FACTS, generate=generate, known_shops=SHOPS, known_recipes=RECIPES)
        self.assertEqual(result['caption'], 'Cibule v Lidlu je tenhle týden v akci.')
        self.assertEqual(result['group_variant'], 'Stavím appku, cibule je v akci.')
        self.assertEqual(len(calls), 2)
        self.assertIn('9,90', calls[1])          # violations fed back
        self.assertIn('"deals"', calls[0])        # facts JSON is in the prompt

    def test_gives_up_after_second_bad_caption(self):
        def generate(prompt):
            return json.dumps({'caption': 'Ušetříte 300 Kč.', 'group_variant': ''})
        with self.assertRaises(CaptionRejected):
            write_caption(DEALS_FACTS, generate=generate, known_shops=SHOPS, known_recipes=RECIPES)

    def test_unparseable_output_is_rejected(self):
        with self.assertRaises(CaptionRejected):
            write_caption(DEALS_FACTS, generate=lambda p: 'not json', known_shops=SHOPS,
                          known_recipes=RECIPES)

    def test_non_deals_kind_has_no_group_variant(self):
        facts = {'kind': 'recipe', 'name': 'Svíčková', 'kcal': 420, 'link': 'https://eatalnicek.eu/'}
        result = write_caption(facts, generate=lambda p: json.dumps({'caption': 'Svíčková má 420 kcal.'}),
                               known_shops=SHOPS, known_recipes=RECIPES)
        self.assertEqual(result['group_variant'], '')


class KnownSetsTests(TestCase):
    def test_known_shops_come_from_grocery_store_rows(self):
        make_store('LIDL', name='Lidl')
        self.assertIn('Lidl', known_shops())

    def test_known_recipe_names_come_from_public_recipes(self):
        from django.contrib.auth.models import User
        from diet_planner.models import DietaryGoal, Recipe
        goal = DietaryGoal.objects.create(user=User.objects.create_user('u', password='x'), country='CZ')
        Recipe.objects.create(meal_identifier='m', dietary_goal=goal, name='Svíčková', is_public=True)
        Recipe.objects.create(meal_identifier='n', dietary_goal=goal, name='Tajná', is_public=False)
        self.assertEqual(known_recipe_names(), {'Svíčková'})
