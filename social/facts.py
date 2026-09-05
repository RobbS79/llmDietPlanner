"""Facts for each post kind, from the database only.

Every public claim a post makes must be traceable to a row here. No LLM, no
network (the recipe photo fetch is injected and lives behind `recipe_photo`).
`NoFacts` means "nothing honest to say this week"; the generator records it
as status=skipped with the reason.
"""
from __future__ import annotations

import os
from datetime import timedelta
from typing import Callable, Optional

import requests
from django.conf import settings
from django.contrib.auth.models import User
from django.utils import timezone

from diet_planner.food_images import dish_image_url, has_dish_image
from diet_planner.models import DietaryGoal, DietaryPlan, Recipe
from diet_planner.services.recipe_deals import active_deal_index, recipe_deals

from .models import SocialPost
from .personas import PERSONA_PROMPTS, persona_for_week

MIN_DEAL_INGREDIENTS = 3
MAX_DEAL_INGREDIENTS = 8
RECIPE_REPOST_DAYS = 90
SHOWCASE_GOALS_TO_KEEP = 4
MEAL_SLOTS = ('breakfast', 'lunch', 'dinner')


class NoFacts(Exception):
    """Raised when a post kind has nothing truthful to say this week."""


def _site() -> str:
    return settings.SOCIAL_SITE_URL.rstrip('/')


def _link(path: str, kind: str, iso_week: str) -> str:
    """Signup/recipe link with UTM. `{channel}` is filled in at publish time."""
    return (f'{_site()}{path}?utm_source={{channel}}&utm_medium=social'
            f'&utm_campaign=auto-{kind}-{iso_week}')


def _public_recipes():
    return Recipe.objects.filter(is_public=True).exclude(slug='').exclude(name='')


# ---------------------------------------------------------------- deals

def deals_facts(iso_week: str) -> dict:
    index = active_deal_index()
    if len(index) < MIN_DEAL_INGREDIENTS:
        raise NoFacts(f'only {len(index)} ingredients on offer, need {MIN_DEAL_INGREDIENTS}')
    from diet_planner.models import CanonicalIngredient
    names = dict(CanonicalIngredient.objects.filter(slug__in=index.keys())
                 .values_list('slug', 'name_cs'))
    ranked = sorted(index.values(), key=lambda d: (d['valid_until'], d['shop']))
    deals = [{
        'canonical': d['canonical'],
        'ingredient': names.get(d['canonical']) or d['display_name'],
        'shop': d['shop'],
        'valid_until': d['valid_until'][:10],
    } for d in ranked[:MAX_DEAL_INGREDIENTS]]

    recipes = []
    for recipe in _public_recipes():
        if not recipe.has_substantive_instructions():
            continue
        hit = recipe_deals(recipe.ingredients, index)
        if hit['matched']:
            recipes.append({'recipe_id': recipe.pk, 'name': recipe.name,
                            'url': f'{_site()}{recipe.get_absolute_url()}',
                            'matched': hit['matched'], 'total': hit['total']})
    recipes.sort(key=lambda r: (-r['matched'], r['name']))
    return {
        'kind': 'deals', 'iso_week': iso_week,
        'deals': deals, 'recipes': recipes[:2],
        'link': _link('/', 'deals', iso_week),
    }


# ---------------------------------------------------------------- recipe

def _recently_posted_recipe_ids() -> set:
    since = timezone.now() - timedelta(days=RECIPE_REPOST_DAYS)
    rows = SocialPost.objects.filter(kind='recipe', status=SocialPost.Status.PUBLISHED,
                                     published_at__gte=since).values_list('facts', flat=True)
    return {f.get('recipe_id') for f in rows if f}


def _per_portion_kcal(nutritional_info, servings, curated: bool):
    """kcal for ONE portion, or None when we cannot say honestly.

    A corpus-backed meal (`curated_recipe_slug` set) was rendered by
    `scale_recipe_to_meal`, whose `nutritional_info` is the TOTAL for all
    `servings` portions — the site divides before showing "na porci"
    (frontend/src/lib/nutrition.ts `nutritionBasisFor`). For an LLM-authored
    meal the basis is unlabelled, so the frontend only guesses; a post may not
    guess, so we publish no number at all.
    """
    if not curated:
        return None
    calories = (nutritional_info or {}).get('calories')
    if not isinstance(calories, (int, float)) or isinstance(calories, bool) or calories <= 0:
        return None
    return round(calories / max(int(servings or 1), 1))


def recipe_facts(iso_week: str) -> dict:
    """Facts for the weekly recipe card. `kcal` is per portion and is only ever
    filled in for corpus-backed recipes, whose stored calories cover all
    `servings`; for LLM-authored rows the basis is a guess, so it stays None.
    """
    exclude = _recently_posted_recipe_ids()
    index = active_deal_index()
    candidates = []
    for recipe in _public_recipes().order_by('pk'):
        if recipe.pk in exclude or not recipe.has_substantive_instructions():
            continue
        if not has_dish_image(recipe.slug):
            continue
        hit = recipe_deals(recipe.ingredients, index)
        candidates.append((hit['matched'], recipe, hit))
    if not candidates:
        raise NoFacts('no public recipe with an image left to post '
                      f'(all posted within {RECIPE_REPOST_DAYS} days or missing images)')
    candidates.sort(key=lambda c: (-c[0], c[1].pk))
    _, recipe, hit = candidates[0]
    kcal = _per_portion_kcal(recipe.nutritional_info, recipe.servings,
                             bool(recipe.curated_recipe_slug))
    minutes = (recipe.preparation_time or 0) + (recipe.cooking_time or 0) or None
    return {
        'kind': 'recipe', 'iso_week': iso_week,
        'recipe_id': recipe.pk, 'name': recipe.name,
        'kcal': kcal,
        'minutes': minutes, 'servings': recipe.servings,
        'source_name': recipe.source_name, 'source_url': recipe.source_url,
        'deals_matched': hit['matched'], 'deals_total': hit['total'],
        'deal_shops': sorted({d['shop'] for d in hit['deals']}),
        'image_url': f'{_site()}{dish_image_url(recipe.slug)}',
        'link': _link(recipe.get_absolute_url(), 'recipe', iso_week),
    }


def _default_fetch(url: str) -> bytes:
    response = requests.get(url, timeout=20)
    response.raise_for_status()
    return response.content


def recipe_photo(facts: dict, fetch: Callable[[str], bytes] = _default_fetch) -> bytes:
    url = facts['image_url']   # missing key = programmer error, not a fetch failure
    try:
        return fetch(url)
    except Exception as exc:  # network, HTTP, decode — all mean "no honest card"
        raise NoFacts(f'recipe photo fetch failed: {exc}') from exc


# ---------------------------------------------------------------- showcase

def _default_run_plan(goal_id: int) -> None:
    from diet_planner.tasks import process_dietary_goal_task
    process_dietary_goal_task.apply(args=(goal_id,))


def _qa_user() -> User:
    username = os.environ.get('QA_TEST_USERNAME', '').strip()
    if not username:
        raise NoFacts('QA_TEST_USERNAME is not set; the showcase needs the QA account')
    try:
        return User.objects.get(username=username)
    except User.DoesNotExist:
        raise NoFacts(f'QA account {username!r} does not exist (run seed_qa_account)') from None


def _prune_showcase_goals(user: User) -> None:
    """Delete this pipeline's own old showcase goals, nothing else.

    The QA account is shared with the /qa-prod tester, whose goals must
    survive (Supabase cascades a goal's plan away with it). A goal is ours
    only when its prompt is one of the fixed persona prompts; `prompt` is
    encrypted, so the match happens in Python, not in SQL.
    """
    ours = [goal.id for goal in
            DietaryGoal.objects.filter(user=user).order_by('-id').only('id', 'prompt')
            if (goal.prompt or '') in PERSONA_PROMPTS]
    stale = ours[SHOWCASE_GOALS_TO_KEEP:]
    if stale:
        DietaryGoal.objects.filter(id__in=stale).delete()


def latest_showcase_goal(user: User) -> Optional[DietaryGoal]:
    """The newest goal this pipeline generated for `user` that completed, or
    None. Used by the dry run, which must not spend an LLM call or leave a
    goal behind. `prompt` is encrypted, so the persona match is in Python."""
    for goal in (DietaryGoal.objects
                 .filter(user=user, status=DietaryGoal.StatusChoices.COMPLETED)
                 .order_by('-id')):
        if (goal.prompt or '') in PERSONA_PROMPTS:
            return goal
    return None


def showcase_facts(iso_week: str, run_plan: Callable[[int], None] = _default_run_plan,
                   reuse_latest: bool = False) -> dict:
    user = _qa_user()
    prompt = persona_for_week(iso_week)
    if reuse_latest:
        # Dry run: read the last real showcase plan instead of generating one,
        # so a rehearsal costs no LLM call and prunes nothing.
        goal = latest_showcase_goal(user)
        if goal is None:
            raise NoFacts('no completed showcase plan to reuse in dry-run')
        prompt = goal.prompt or prompt
    else:
        goal = DietaryGoal.objects.create(user=user, prompt=prompt, country='CZ',
                                          num_days=1, language_code='cs')
        run_plan(goal.id)
        goal.refresh_from_db()
        _prune_showcase_goals(user)
        if goal.status != DietaryGoal.StatusChoices.COMPLETED:
            raise NoFacts(f'plan generation ended {goal.status}: {goal.error_message or "no detail"}')
    plan = DietaryPlan.objects.filter(dietary_goal=goal).first()
    day = next((d for d in (plan.days if plan else []) if d.get('day_number') == 1), None)
    if not day:
        raise NoFacts('plan completed but has no day 1')
    meals = []
    index = active_deal_index()
    for slot in MEAL_SLOTS:
        meal = day.get(slot)
        if not meal or not meal.get('name'):
            continue
        kcal = _per_portion_kcal(meal.get('nutritional_info'), meal.get('servings'),
                                 bool(meal.get('curated_recipe_slug')))
        hit = recipe_deals(meal.get('ingredients') or [], index)
        meals.append({'slot': slot, 'name': meal['name'],
                      'kcal': kcal,
                      'deals_matched': hit['matched']})
    if len(meals) < 2:
        raise NoFacts('day 1 has fewer than two named meals')
    return {
        'kind': 'showcase', 'iso_week': iso_week,
        'goal_id': goal.id, 'prompt': prompt, 'meals': meals,
        'total_kcal': sum(m['kcal'] or 0 for m in meals),
        'link': _link('/', 'showcase', iso_week),
    }


# ---------------------------------------------------------------- dispatch

def build_facts(kind: str, iso_week: str, *,
                run_plan: Optional[Callable[[int], None]] = None,
                reuse_latest: bool = False) -> dict:
    if kind != 'showcase':
        if run_plan is not None:
            raise ValueError(f'run_plan is only meaningful for showcase, not {kind!r}')
        if reuse_latest:
            raise ValueError(f'reuse_latest is only meaningful for showcase, not {kind!r}')
    if kind == 'deals':
        return deals_facts(iso_week)
    if kind == 'recipe':
        return recipe_facts(iso_week)
    if kind == 'showcase':
        return showcase_facts(iso_week, run_plan=run_plan or _default_run_plan,
                              reuse_latest=reuse_latest)
    raise ValueError(f'unknown kind {kind!r}')
