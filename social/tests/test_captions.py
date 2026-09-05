import json

from django.test import SimpleTestCase, TestCase

from diet_planner.tests.factories import make_store
from social.captions import (
    shorten,
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
        self.assertTrue(any('states a percentage' in v for v in violations))

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


class ShopMentionTests(SimpleTestCase):
    """A shop name is a proper noun; a common noun that merely starts the same is not."""

    ROHLIK_FACTS = {
        'kind': 'deals', 'iso_week': '2026-W37',
        'deals': [{'ingredient': 'cibule', 'shop': 'Rohlik', 'valid_until': '2026-09-13'}],
        'link': 'https://eatalnicek.eu/',
    }

    def check(self, caption, facts=None, shops=None):
        return validate_caption(caption, facts if facts is not None else DEALS_FACTS,
                                known_shops=shops if shops is not None else SHOPS,
                                known_recipes=set())

    def test_domain_suffix_does_not_split_a_shop_in_two(self):
        self.assertEqual(self.check('Cibule je v akci na Rohlíku.', facts=self.ROHLIK_FACTS,
                                    shops={'Rohlik.cz', 'Lidl'}), [])

    def test_common_noun_rohlik_is_not_the_shop(self):
        self.assertEqual(self.check('K polévce si dej rohlík.', shops={'Rohlik.cz'}), [])

    def test_common_noun_kosik_is_not_the_shop(self):
        self.assertEqual(self.check('Hoď cibuli do košíku.', shops={'Kosik.cz'}), [])

    def test_common_noun_penne_is_not_penny(self):
        self.assertEqual(self.check('Uvař penne s cibulí.', shops={'Penny'}), [])

    def test_inflected_shop_outside_the_facts_is_flagged(self):
        self.assertTrue(any('Kaufland' in v for v in self.check('Cibule je v akci v Kauflandu.')))

    def test_longer_lookalike_is_not_the_shop(self):
        self.assertEqual(self.check('Kaufmann je jméno.'), [])

    def test_lowercase_shop_name_is_still_a_mention(self):
        self.assertTrue(any('Kaufland' in v for v in self.check('cibule je v akci v kauflandu.')))

    def test_each_missing_shop_is_reported_once(self):
        violations = self.check('Cibule je v akci v tescu a v kauflandu.',
                                shops={'Tesco', 'Kaufland'})
        self.assertEqual(len(violations), 2, violations)

    def test_common_noun_base_still_needs_a_capital(self):
        # 'do košíku' is a basket; only 'Kosik' the shop is capitalized.
        self.assertEqual(self.check('cibule hoď do košíku.', shops={'Kosik.cz'}), [])

    def test_capitalized_common_noun_is_a_known_false_positive(self):
        # Documented FP: a sentence-initial bread roll reads as the shop. The
        # human ✅ in Slack is the backstop; a missed real shop would not be.
        self.assertTrue(self.check('Rohlík k polévce.', shops={'Rohlik.cz'}))


class RecipeMentionTests(SimpleTestCase):
    def check(self, caption, recipes):
        return validate_caption(caption, DEALS_FACTS, known_shops=SHOPS, known_recipes=recipes)

    def test_declined_recipe_name_is_flagged(self):
        self.assertTrue(any('Svíčková' in v for v in self.check('Uvařte si svíčkovou.', {'Svíčková'})))

    def test_shorter_lookalike_word_is_not_the_recipe(self):
        self.assertEqual(self.check('Zapal si svíčku u večeře.', {'Svíčková'}), [])

    def test_ingredient_word_is_not_the_dish(self):
        self.assertEqual(self.check('Brambory jsou v akci.', {'Bramborák'}), [])

    def test_plural_dish_is_flagged(self):
        self.assertTrue(self.check('Bramboráky z brambor', {'Bramborák'}))

    def test_unrelated_word_sharing_a_prefix_is_not_the_recipe(self):
        self.assertEqual(self.check('Zvaž rizika, cibule je v akci.', {'Rizoto'}), [])

    def test_recipe_that_is_in_the_facts_is_allowed(self):
        self.assertEqual(self.check('Vepřové s cibulí zvládneš dnes.', RECIPES), [])

    def test_short_name_does_not_fire_on_a_folded_lookalike(self):
        self.assertEqual(self.check('Kasa v obchodě je vzadu.', {'Kaše'}), [])

    def test_short_name_does_not_fire_on_a_diacritic_lookalike(self):
        self.assertEqual(self.check('Ryze česká klasika, cibule v akci.', {'Rýže'}), [])

    def test_short_name_still_matches_its_own_declension(self):
        self.assertTrue(any('Kaše' in v for v in self.check('Dej si kaši.', {'Kaše'})))


class NumberRuleTests(SimpleTestCase):
    def check(self, caption, facts=None):
        return validate_caption(caption, facts if facts is not None else DEALS_FACTS,
                                known_shops=SHOPS, known_recipes=RECIPES)

    def test_czech_rendering_of_a_fact_date_is_allowed(self):
        self.assertEqual(self.check('Akce platí do 13. 9. 2026.'), [])

    def test_price_is_banned_even_when_the_digit_appears_in_the_facts(self):
        violations = self.check('Cibule za 4 Kč v Lidlu.')          # 4 == recipes[0]["total"]
        self.assertTrue(any('price' in v for v in violations))

    def test_percentage_is_banned(self):
        self.assertTrue(any('percentage' in v for v in self.check('Cibule je levnější o 37 procent.')))

    def test_identifier_digits_do_not_whitelist_a_number(self):
        facts = {'kind': 'recipe', 'name': 'Svíčková', 'recipe_id': 37,
                 'link': 'https://eatalnicek.eu/'}
        self.assertTrue(any("'37'" in v for v in self.check('Svíčková má 37 fanoušků.', facts=facts)))

    def test_counting_number_from_the_facts_is_allowed(self):
        self.assertEqual(self.check('Máme pro tebe 2 recepty s cibulí.'), [])


class GroupVariantRequiredTests(SimpleTestCase):
    def test_deals_without_group_variant_is_rejected(self):
        def generate(prompt):
            return json.dumps({'caption': 'Cibule je tenhle týden v akci.'})
        with self.assertRaises(CaptionRejected) as ctx:
            write_caption(DEALS_FACTS, generate=generate, known_shops=SHOPS, known_recipes=RECIPES)
        self.assertIn('group_variant', str(ctx.exception))


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


class ShortenTests(SimpleTestCase):
    def test_short_text_is_unchanged(self):
        self.assertEqual(shorten('Cibule v akci.', 350), 'Cibule v akci.')

    def test_cuts_at_sentence_boundary_and_keeps_the_link(self):
        body = ('Cibule je tenhle týden v akci. ' * 12).strip()
        text = body + '\nhttps://eatalnicek.eu/?utm_source={channel}&utm_campaign=auto-deals-2026-W37'
        out = shorten(text, 350)
        self.assertLessEqual(len(out), 350)
        self.assertTrue(out.endswith('utm_campaign=auto-deals-2026-W37'))
        self.assertTrue(out.split('\n')[0].endswith('.'))

    def test_falls_back_to_a_space_with_ellipsis(self):
        text = 'cibule ' * 80
        out = shorten(text.strip(), 100)
        self.assertLessEqual(len(out), 100)
        self.assertTrue(out.endswith('…'))

    def test_write_caption_shortens_instead_of_rejecting(self):
        long_group = ('Stavím appku, cibule je v akci. ' * 15).strip()
        result = write_caption(DEALS_FACTS, generate=lambda p: json.dumps(
            {'caption': 'Cibule v Lidlu je tenhle týden v akci.', 'group_variant': long_group}),
            known_shops=SHOPS, known_recipes=RECIPES)
        self.assertLessEqual(len(result['group_variant']), 350)
        self.assertTrue(result['group_variant'].endswith('.'))
