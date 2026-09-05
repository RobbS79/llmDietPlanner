from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone
from django.utils.text import slugify

from diet_planner.models import (DietaryGoal, DietaryPlan, PriceRecord, PriceSourceType,
                                 Recipe)
from diet_planner.services.canonical_lookup import clear_cache
from diet_planner.services.recipe_deals import active_deal_index
from diet_planner.tests.factories import make_canonical, make_price, make_store
from social.facts import (NoFacts, _per_portion_kcal, build_facts, latest_showcase_goal,
                          recipe_photo)
from social.models import SocialPost
from social.personas import PERSONA_PROMPTS, persona_for_week


def _public_recipe(goal, name, slug, ingredients, kcal=840, prep=10, cook=20,
                   source='Apetit', source_url='https://apetit.cz/x',
                   curated_slug='kureci-rizoto'):
    """`kcal` is the stored total for all `servings`, the way a corpus-backed
    row really stores it; pass curated_slug='' for an LLM-authored row."""
    return Recipe.objects.create(
        meal_identifier=f'g{goal.id}:1:dinner:{slug}', dietary_goal=goal, name=name,
        slug=slug, ingredients=ingredients, servings=2, is_public=True,
        instructions=['Nakrájejte cibuli a osmahněte ji.'] * 6,
        nutritional_info={'calories': kcal}, preparation_time=prep, cooking_time=cook,
        source_name=source, source_url=source_url, curated_recipe_slug=curated_slug,
    )


def _curated_meal(name, calories, ingredients, servings=2, curated=True):
    """A day-plan meal the way `scale_recipe_to_meal` renders one: nutrition is
    the total for `servings` portions and provenance is carried on the dict."""
    meal = {'name': name, 'servings': servings, 'ingredients': ingredients,
            'nutritional_info': {'calories': calories}}
    if curated:
        meal.update({'source': 'curated', 'curated_recipe_slug': slugify(name)})
    return meal


def _seed_deal(name, name_cs, store_code='LIDL', days=6):
    """One active leaflet deal on a fresh canonical ingredient."""
    make_store(store_code, name=store_code.title())
    canonical = make_canonical(name, default_unit='ks', name_cs=name_cs)
    clear_cache()
    make_price(store_code=store_code, normalized_name=name_cs, price='9.90',
               source_type=PriceSourceType.LEAFLET_DISCOUNT, canonical=canonical,
               source_url='http://x', valid_for_days=days)
    return canonical


class PerPortionKcalTests(TestCase):
    def test_curated_total_is_divided_by_servings(self):
        self.assertEqual(_per_portion_kcal({'calories': 840}, 2, True), 420)
        self.assertEqual(_per_portion_kcal({'calories': 835}, 2, True), 418)

    def test_uncurated_basis_is_unknown_so_no_number_is_published(self):
        self.assertIsNone(_per_portion_kcal({'calories': 840}, 2, False))

    def test_missing_or_unusable_calories_give_none(self):
        self.assertIsNone(_per_portion_kcal(None, 2, True))
        self.assertIsNone(_per_portion_kcal({}, 2, True))
        self.assertIsNone(_per_portion_kcal({'calories': 0}, 2, True))
        self.assertIsNone(_per_portion_kcal({'calories': '840 kcal'}, 2, True))

    def test_missing_servings_falls_back_to_one_portion(self):
        self.assertEqual(_per_portion_kcal({'calories': 420}, None, True), 420)
        self.assertEqual(_per_portion_kcal({'calories': 420}, 0, True), 420)


class DealsFactsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('u1', password='x')
        self.goal = DietaryGoal.objects.create(user=self.user, country='CZ')
        make_store('LIDL', name='Lidl')
        make_store('ALBERT', name='Albert')
        self.onion = make_canonical('onion', default_unit='ks', name_cs='cibule')
        self.carrot = make_canonical('carrot', default_unit='ks', name_cs='mrkev')
        self.pork = make_canonical('pork', default_unit='g', name_cs='vepřové')
        clear_cache()
        for canonical, name, store in [(self.onion, 'cibule', 'LIDL'),
                                       (self.carrot, 'mrkev', 'ALBERT'),
                                       (self.pork, 'vepřové', 'LIDL')]:
            make_price(store_code=store, normalized_name=name, price='9.90',
                       source_type=PriceSourceType.LEAFLET_DISCOUNT, canonical=canonical,
                       source_url='http://x', valid_for_days=6)

    def test_deals_facts_list_ingredients_and_recipes_that_use_them(self):
        r = _public_recipe(self.goal, 'Vepřové s cibulí', 'veprove-s-cibuli',
                           [{'name': 'vepřové', 'canonical': 'pork'},
                            {'name': 'cibule', 'canonical': 'onion'}])
        _public_recipe(self.goal, 'Mrkvový salát', 'mrkvovy-salat',
                       [{'name': 'mrkev', 'canonical': 'carrot'}])
        facts = build_facts('deals', '2026-W37')
        self.assertEqual({d['ingredient'] for d in facts['deals']},
                         {'cibule', 'mrkev', 'vepřové'})
        self.assertEqual(facts['deals'][0].keys() >= {'ingredient', 'shop', 'valid_until'}, True)
        self.assertEqual(facts['recipes'][0]['name'], r.name)
        self.assertEqual(facts['recipes'][0]['matched'], 2)
        self.assertEqual(facts['recipes'][0]['url'],
                         f'https://eatalnicek.eu/recepty/{r.pk}/veprove-s-cibuli/')
        self.assertIn('utm_campaign=auto-deals-2026-W37', facts['link'])
        self.assertIn('utm_source={channel}', facts['link'])

    def test_deals_facts_need_at_least_three_ingredients(self):
        from diet_planner.models import PriceRecord
        PriceRecord.objects.filter(store_product__canonical_ingredient=self.pork).delete()
        with self.assertRaises(NoFacts) as ctx:
            build_facts('deals', '2026-W37')
        self.assertIn('2 ingredients', str(ctx.exception))

    def test_deals_are_listed_soonest_expiry_first(self):
        PriceRecord.objects.all().delete()          # drop setUp's equal-length deals
        _seed_deal('leek', 'pórek', days=9)
        _seed_deal('apple', 'jablko', days=2)
        _seed_deal('butter', 'máslo', days=5)
        facts = build_facts('deals', '2026-W37')
        self.assertEqual([d['ingredient'] for d in facts['deals']],
                         ['jablko', 'máslo', 'pórek'])

    def test_at_most_eight_deals_are_published(self):
        for i in range(7):
            _seed_deal(f'extra{i}', f'surovina {i}', days=3 + i)
        self.assertEqual(len(active_deal_index()), 10)
        facts = build_facts('deals', '2026-W37')
        self.assertEqual(len(facts['deals']), 8)


class RecipeFactsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('u1', password='x')
        self.goal = DietaryGoal.objects.create(user=self.user, country='CZ')

    def test_recipe_facts_pick_public_recipe_with_image_not_recently_posted(self):
        old = _public_recipe(self.goal, 'Stará', 'stara', [{'name': 'cibule'}])
        fresh = _public_recipe(self.goal, 'Nová', 'nova', [{'name': 'cibule'}])
        SocialPost.objects.create(kind='recipe', iso_week='2026-W30', scheduled_for='2026-07-22',
                                  status='published', facts={'recipe_id': old.pk},
                                  published_at=timezone.now())
        with patch('social.facts.has_dish_image', return_value=True):
            facts = build_facts('recipe', '2026-W37')
        self.assertEqual(facts['recipe_id'], fresh.pk)
        self.assertEqual(facts['name'], 'Nová')
        self.assertEqual(facts['kcal'], 420)   # 840 stored / 2 servings
        self.assertEqual(facts['minutes'], 30)
        self.assertEqual(facts['source_name'], 'Apetit')
        self.assertEqual(facts['image_url'], 'https://eatalnicek.eu/static/food-images/dishes/nova.webp')
        self.assertEqual(facts['link'], f'https://eatalnicek.eu/recepty/{fresh.pk}/nova/?utm_source={{channel}}&utm_medium=social&utm_campaign=auto-recipe-2026-W37')

    def test_recipe_facts_publish_no_kcal_for_an_llm_authored_recipe(self):
        _public_recipe(self.goal, 'Nová', 'nova', [{'name': 'cibule'}], curated_slug='')
        with patch('social.facts.has_dish_image', return_value=True):
            facts = build_facts('recipe', '2026-W37')
        self.assertIsNone(facts['kcal'])

    def test_recipe_facts_raise_when_pool_is_exhausted(self):
        _public_recipe(self.goal, 'Bez obrázku', 'bez-obrazku', [{'name': 'cibule'}])
        with patch('social.facts.has_dish_image', return_value=False):
            with self.assertRaises(NoFacts):
                build_facts('recipe', '2026-W37')

    def test_recipe_facts_prefer_the_recipe_with_more_active_deals(self):
        _seed_deal('leek', 'pórek')
        plain = _public_recipe(self.goal, 'Bez akce', 'bez-akce', [{'name': 'rýže'}])
        with_deal = _public_recipe(self.goal, 'S akcí', 's-aci',
                                   [{'name': 'pórek', 'canonical': 'leek'}])
        self.assertLess(plain.pk, with_deal.pk)     # not just "first row wins"
        with patch('social.facts.has_dish_image', return_value=True):
            facts = build_facts('recipe', '2026-W37')
        self.assertEqual(facts['recipe_id'], with_deal.pk)
        self.assertEqual(facts['deals_matched'], 1)
        self.assertEqual(facts['deal_shops'], ['Lidl'])

    def test_a_recipe_posted_over_ninety_days_ago_is_eligible_again(self):
        old = _public_recipe(self.goal, 'Stará', 'stara', [{'name': 'cibule'}])
        SocialPost.objects.create(kind='recipe', iso_week='2026-W20',
                                  scheduled_for='2026-05-13', status='published',
                                  facts={'recipe_id': old.pk},
                                  published_at=timezone.now() - timedelta(days=100))
        with patch('social.facts.has_dish_image', return_value=True):
            facts = build_facts('recipe', '2026-W37')
        self.assertEqual(facts['recipe_id'], old.pk)

    def test_recipe_photo_uses_injected_fetcher_and_wraps_failure(self):
        facts = {'image_url': 'https://eatalnicek.eu/static/food-images/dishes/x.webp'}
        self.assertEqual(recipe_photo(facts, fetch=lambda url: b'PNG'), b'PNG')

        def boom(url):
            raise OSError('timeout')
        with self.assertRaises(NoFacts):
            recipe_photo(facts, fetch=boom)


class ShowcaseFactsTests(TestCase):
    def setUp(self):
        self.qa = User.objects.create_user('qa_bot', password='x')

    def _fake_run(self, goal_id):
        goal = DietaryGoal.objects.get(pk=goal_id)
        goal.status = DietaryGoal.StatusChoices.COMPLETED
        goal.save(update_fields=['status'])
        DietaryPlan.objects.create(dietary_goal=goal, days=[{
            'day_number': 1,
            'breakfast': _curated_meal('Ovesná kaše', 700, [{'name': 'ovesné vločky'}]),
            'lunch': _curated_meal('Kuřecí rizoto', 1240, [{'name': 'rýže'}]),
            # LLM-authored: no provenance, so its calories have no known basis.
            'dinner': _curated_meal('Zeleninová polévka', 280, [{'name': 'mrkev'}],
                                    curated=False),
            'small_meals': [], 'snacks': [],
        }])

    def test_showcase_creates_goal_for_qa_user_and_reads_day_one(self):
        with patch.dict('os.environ', {'QA_TEST_USERNAME': 'qa_bot'}):
            facts = build_facts('showcase', '2026-W37', run_plan=self._fake_run)
        self.assertEqual(facts['prompt'], persona_for_week('2026-W37'))
        self.assertEqual([m['name'] for m in facts['meals']],
                         ['Ovesná kaše', 'Kuřecí rizoto', 'Zeleninová polévka'])
        self.assertEqual([m['kcal'] for m in facts['meals']], [350, 620, None])
        self.assertEqual(facts['total_kcal'], 970)   # only the meals we can stand behind
        goal = DietaryGoal.objects.get(pk=facts['goal_id'])
        self.assertEqual(goal.user, self.qa)
        self.assertEqual(goal.num_days, 1)

    def test_showcase_raises_when_generation_fails(self):
        def failing(goal_id):
            DietaryGoal.objects.filter(pk=goal_id).update(status='failed', error_message='LLM down')
        with patch.dict('os.environ', {'QA_TEST_USERNAME': 'qa_bot'}):
            with self.assertRaises(NoFacts) as ctx:
                build_facts('showcase', '2026-W37', run_plan=failing)
        self.assertIn('LLM down', str(ctx.exception))

    def test_showcase_requires_qa_account(self):
        with patch.dict('os.environ', {'QA_TEST_USERNAME': ''}):
            with self.assertRaises(NoFacts):
                build_facts('showcase', '2026-W37', run_plan=self._fake_run)

    def test_showcase_keeps_only_four_most_recent_goals(self):
        with patch.dict('os.environ', {'QA_TEST_USERNAME': 'qa_bot'}):
            for week in range(30, 36):
                build_facts('showcase', f'2026-W{week}', run_plan=self._fake_run)
        self.assertEqual(DietaryGoal.objects.filter(user=self.qa).count(), 4)

    def test_showcase_pruning_leaves_other_qa_goals_alone(self):
        # The QA account is also driven by the /qa-prod tester; its goals (and
        # the plans that cascade with them) must survive our housekeeping.
        theirs = DietaryGoal.objects.create(user=self.qa, prompt='QA smoke run',
                                            country='CZ', num_days=1)
        with patch.dict('os.environ', {'QA_TEST_USERNAME': 'qa_bot'}):
            for week in range(30, 36):
                build_facts('showcase', f'2026-W{week}', run_plan=self._fake_run)
        self.assertTrue(DietaryGoal.objects.filter(pk=theirs.pk).exists())
        self.assertEqual(DietaryGoal.objects.filter(user=self.qa).count(), 5)

    # The three NoFacts reasons below have no test in the plan; they are the
    # remaining honest-refusal paths of showcase_facts and are cheap to pin.
    def test_showcase_requires_the_qa_account_to_exist(self):
        with patch.dict('os.environ', {'QA_TEST_USERNAME': 'nobody'}):
            with self.assertRaises(NoFacts) as ctx:
                build_facts('showcase', '2026-W37', run_plan=self._fake_run)
        self.assertIn('seed_qa_account', str(ctx.exception))

    def test_showcase_raises_when_the_plan_has_no_day_one(self):
        def empty(goal_id):
            goal = DietaryGoal.objects.get(pk=goal_id)
            goal.status = DietaryGoal.StatusChoices.COMPLETED
            goal.save(update_fields=['status'])
            DietaryPlan.objects.create(dietary_goal=goal, days=[])
        with patch.dict('os.environ', {'QA_TEST_USERNAME': 'qa_bot'}):
            with self.assertRaises(NoFacts) as ctx:
                build_facts('showcase', '2026-W37', run_plan=empty)
        self.assertIn('no day 1', str(ctx.exception))

    def test_dry_run_reuses_the_newest_completed_showcase_plan(self):
        with patch.dict('os.environ', {'QA_TEST_USERNAME': 'qa_bot'}):
            real = build_facts('showcase', '2026-W37', run_plan=self._fake_run)
            # No run_plan: reuse must not generate, or this would hit Celery.
            reused = build_facts('showcase', '2026-W38', reuse_latest=True)
        self.assertEqual(reused['goal_id'], real['goal_id'])
        self.assertEqual(reused['iso_week'], '2026-W38')
        self.assertEqual(reused['prompt'], real['prompt'])
        self.assertEqual([m['name'] for m in reused['meals']],
                         [m['name'] for m in real['meals']])
        self.assertEqual(DietaryGoal.objects.filter(user=self.qa).count(), 1)

    def test_reuse_refuses_when_no_showcase_plan_has_completed(self):
        DietaryGoal.objects.create(user=self.qa, prompt=PERSONA_PROMPTS[0], country='CZ',
                                   num_days=1)   # still pending
        with patch.dict('os.environ', {'QA_TEST_USERNAME': 'qa_bot'}):
            with self.assertRaises(NoFacts) as ctx:
                build_facts('showcase', '2026-W37', reuse_latest=True)
        self.assertIn('no completed showcase plan to reuse', str(ctx.exception))

    def test_latest_showcase_goal_ignores_goals_this_pipeline_did_not_write(self):
        DietaryGoal.objects.create(user=self.qa, prompt='QA smoke run', country='CZ', num_days=1,
                                   status=DietaryGoal.StatusChoices.COMPLETED)
        self.assertIsNone(latest_showcase_goal(self.qa))
        older = DietaryGoal.objects.create(user=self.qa, prompt=PERSONA_PROMPTS[0], country='CZ',
                                           num_days=1,
                                           status=DietaryGoal.StatusChoices.COMPLETED)
        newer = DietaryGoal.objects.create(user=self.qa, prompt=PERSONA_PROMPTS[1], country='CZ',
                                           num_days=1,
                                           status=DietaryGoal.StatusChoices.COMPLETED)
        self.assertEqual(latest_showcase_goal(self.qa), newer)
        newer.delete()
        self.assertEqual(latest_showcase_goal(self.qa), older)

    def test_showcase_raises_when_day_one_has_a_single_meal(self):
        def thin(goal_id):
            goal = DietaryGoal.objects.get(pk=goal_id)
            goal.status = DietaryGoal.StatusChoices.COMPLETED
            goal.save(update_fields=['status'])
            DietaryPlan.objects.create(dietary_goal=goal, days=[{
                'day_number': 1,
                'breakfast': _curated_meal('Ovesná kaše', 700, []),
                'lunch': {}, 'dinner': None, 'small_meals': [], 'snacks': [],
            }])
        with patch.dict('os.environ', {'QA_TEST_USERNAME': 'qa_bot'}):
            with self.assertRaises(NoFacts) as ctx:
                build_facts('showcase', '2026-W37', run_plan=thin)
        self.assertIn('fewer than two', str(ctx.exception))


class BuildFactsDispatchTests(TestCase):
    def test_run_plan_is_rejected_for_a_kind_that_generates_no_plan(self):
        with self.assertRaises(ValueError):
            build_facts('deals', '2026-W37', run_plan=lambda goal_id: None)

    def test_reuse_latest_is_rejected_for_a_kind_that_generates_no_plan(self):
        with self.assertRaises(ValueError):
            build_facts('deals', '2026-W37', reuse_latest=True)

    def test_unknown_kind_is_a_value_error(self):
        with self.assertRaises(ValueError):
            build_facts('brunch', '2026-W37')
