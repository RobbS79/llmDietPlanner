"""Build a meal pool for a goal: corpus first, Gemini only for the gaps.

Order of operations (spec §5):
  1. facets from the prompt (the one Gemini call on the happy path)
  2. select_recipes_for_pool — N curated recipes per slot
  3. render each into a meal dict (portions, příloha, attribution)
  4. for every position the corpus could not fill, ask Gemini for ONE meal
     and run the restriction repair on it; a failure is a SHORTFALL, never a
     crash and never a violating meal
  5. refuse an empty pool
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List

from django.conf import settings
from django.db.models import F

try:
    from billiard.exceptions import SoftTimeLimitExceeded
except ImportError:  # pragma: no cover — billiard ships with celery
    class SoftTimeLimitExceeded(Exception):
        """Stand-in so the re-raise clause stays valid without billiard."""

from diet_planner.models import CuratedRecipe
from diet_planner.services.meal_locator import MAIN_SLOTS, POOL_SLOTS, pool_identifier
from diet_planner.services.nutrition_lookups import nutrition_table
from diet_planner.services.prompt_facets import extract_prompt_facets
from diet_planner.services.recipe_retrieval import (
    _SLOT_DEFAULT_KCAL,
    pool_counts,
    published_cuisine_vocab,
    recently_served_curated_ids,
    render_curated_meal,
    required_tags_for_goal,
    select_recipes_for_pool,
    store_derived_dietary_tags,
)
from diet_planner.services.restrictions import (
    RepairBudgetExhausted, RestrictionResolver, repair_single_meal,
)

logger = logging.getLogger(__name__)

_USAGE_KEYS = ('input_tokens', 'output_tokens', 'total_tokens')
# Consecutive gap-fill failures after which Gemini is assumed down and the
# remaining positions become shortfall without further calls.
_BREAKER_THRESHOLD = 3


def _monotonic() -> float:
    """Indirection so tests can drive the gap-fill clock without patching
    the process-wide time.monotonic."""
    return time.monotonic()


def _normalise_generated(meal: Any) -> Dict[str, Any]:
    """Coerce an LLM meal into the shape the rest of the pipeline expects:
    list ingredients/instructions, str description, stripped str name."""
    if not isinstance(meal, dict):
        raise ValueError(f"generated meal is not a dict: {type(meal).__name__}")
    out = dict(meal)
    for key in ('ingredients', 'instructions'):
        if not isinstance(out.get(key), list):
            out[key] = []
    desc = out.get('description')
    out['description'] = '' if desc is None else str(desc)
    name = out.get('name')
    out['name'] = '' if name is None else str(name).strip()
    return out


def stamp_generated_nutrition(meal: Dict[str, Any], table) -> None:
    """Resolve canonicals for a Gemini meal and compute its nutrition when
    every line converts; otherwise keep Gemini's numbers, labelled estimated.
    Either way `nutritional_info` is the TOTAL for `servings` portions."""
    from diet_planner.services.recipe_curation import map_ingredients
    from diet_planner.services.recipe_nutrition import compute_recipe_nutrition
    mapped: List[Dict[str, Any]] = []
    for raw in meal.get('ingredients') or []:
        rows = map_ingredients([raw])
        if rows:  # keep any extra keys Gemini sent; map_ingredients' fields win
            extra = ({k: v for k, v in raw.items() if k != 'canonical'}
                     if isinstance(raw, dict) else {})
            mapped.append({**extra, **rows[0]})
    meal['ingredients'] = mapped
    try:
        servings = max(int(meal.get('servings') or 1), 1)
    except (TypeError, ValueError):
        servings = 1
    n = compute_recipe_nutrition(meal['ingredients'], table)
    # calories > 0: a meal whose only lines are to-taste "converts" to 0 kcal,
    # which is not a computation worth trusting over Gemini's estimate.
    if n.complete and n.calories > 0:
        meal['nutritional_info'] = {
            'calories': int(round(n.calories)), 'protein': f'{int(round(n.protein))}g',
            'carbs': f'{int(round(n.carbs))}g', 'fat': f'{int(round(n.fat))}g',
            'basis': 'total', 'servings': servings, 'nutrition_source': 'computed'}
    else:
        info = meal.get('nutritional_info')
        info = dict(info) if isinstance(info, dict) else {}
        info.update({'basis': 'total', 'servings': servings, 'nutrition_source': 'estimated'})
        meal['nutritional_info'] = info


@dataclass
class PoolResult:
    meals: List[Dict[str, Any]]
    grounding_debug: Dict[str, Any]
    llm_usage: Dict[str, Any] = field(default_factory=dict)


def _empty_usage() -> Dict[str, Any]:
    return {'input_tokens': 0, 'output_tokens': 0, 'total_tokens': 0, 'cost_usd': 0.0, 'model': None}


def _add_usage(total: Dict[str, Any], one: Dict[str, Any]) -> None:
    for key in _USAGE_KEYS:
        total[key] += int(one.get(key) or 0)
    total['cost_usd'] = float(total['cost_usd']) + float(one.get('cost_usd') or 0)
    total['model'] = one.get('model') or total['model']


def _protocol_prompt(goal: Any) -> str:
    """The user prompt with an attached specialist protocol prepended
    (moved here from the old day-grid task)."""
    user_prompt = getattr(goal, 'prompt', '') or ''
    ref = getattr(goal, 'historic_plan_reference_id', None)
    if not ref:
        return user_prompt
    from diet_planner.models import HistoricNutritionPlan
    try:
        protocol = HistoricNutritionPlan.objects.get(id=ref, processing_status='completed')
    except HistoricNutritionPlan.DoesNotExist:
        return user_prompt
    constraints = protocol.structured_constraints
    if not constraints:
        return user_prompt
    return (
        "[PROFESSIONAL DIET PROTOCOL - PRIORITY]\n"
        "The user has a professional diet protocol from a specialist. "
        f"The plan MUST respect these constraints:\n{constraints}\n\n"
        f"[USER REQUIREMENTS]\n{user_prompt}"
    )


def _render_curated(recipe: CuratedRecipe, slot: str, index: int, goal_id: Any,
                    required_tags, gaps: List[Dict[str, Any]], table) -> Dict[str, Any]:
    """Step 3 for one position: curated recipe -> positioned meal dict."""
    meal, side_gap = render_curated_meal(
        recipe, target_kcal=_SLOT_DEFAULT_KCAL.get(slot), required_tags=required_tags,
        table=table)
    if side_gap:
        gaps.append({'slot': slot, 'index': index, 'reason': side_gap,
                     'required_tags': sorted(required_tags), 'unmatched_wanted': []})
    meal.update({'slot': slot, 'index': index,
                 'meal_identifier': pool_identifier(goal_id, slot, index)})
    return meal


def build_meal_pool(goal: Any, *, llm: Any = None,
                    status: str = CuratedRecipe.Status.PUBLISHED) -> PoolResult:
    if llm is None:
        from diet_planner.llm_service import GeminiService
        llm = GeminiService()

    language = getattr(goal, 'language_code', 'cs') or 'cs'
    facets = extract_prompt_facets(
        getattr(goal, 'prompt', '') or '', language=language,
        cuisine_vocab=published_cuisine_vocab(status=status),
    )
    store_derived_dietary_tags(goal, getattr(facets, 'dietary', set()))
    required_tags = required_tags_for_goal(goal)
    counts = pool_counts(goal)
    goal_id = getattr(goal, 'id', None) or getattr(goal, 'pk', 0)

    # Suspect facets: the user said something concrete and we failed to parse
    # it, so corpus ranking is blind to it. Mains then come from Gemini with
    # the raw prompt; small meals/snacks are prompt-agnostic and stay curated.
    skip = MAIN_SLOTS if getattr(facets, 'suspect', False) else ()
    if skip:
        logger.warning("Facet extraction suspect for goal %s: mains go to the LLM", goal_id)

    selection = select_recipes_for_pool(
        goal, status=status, facets=facets,
        recently_served_ids=recently_served_curated_ids(goal), skip_slots=skip,
    )
    gaps: List[Dict[str, Any]] = list(selection['gaps'])
    meals: List[Dict[str, Any]] = []
    served_ids = set()
    table = nutrition_table()  # once per pool: sides + gap-fill meals
    for entry in selection['meals']:
        slot, index, recipe = entry['slot'], entry['index'], entry['recipe']
        meals.append(_render_curated(recipe, slot, index, goal_id, required_tags, gaps, table))
        served_ids.add(recipe.id)

    # Gap fill: every requested position with no curated meal. Bounded by a
    # wall-clock budget (Celery soft limit is 300 s) and a circuit breaker so a
    # dead Gemini costs 3 calls, not one per position.
    covered = {(m['slot'], m['index']) for m in meals}
    usage = _empty_usage()
    shortfall: Dict[str, int] = {}
    shortfall_reasons: Dict[str, str] = {}
    exclusions = RestrictionResolver().resolve(goal)
    user_prompt = _protocol_prompt(goal)
    budget = getattr(settings, 'MEAL_POOL_GAP_FILL_BUDGET_SECONDS', 240)
    consecutive_failures = 0

    def _short(slot: str, index: int, reason: str) -> None:
        shortfall[slot] = shortfall.get(slot, 0) + 1
        shortfall_reasons[f'{slot}:{index}'] = reason

    started = _monotonic()
    for slot in POOL_SLOTS:
        for index in range(counts.get(slot, 0)):
            if (slot, index) in covered:
                continue
            key = f'{slot}:{index}'
            if _monotonic() - started > budget:
                logger.warning("Pool gap goal=%s %s: gap-fill time budget (%ss) spent — shortfall",
                               goal_id, key, budget)
                _short(slot, index, 'time_budget')
                continue
            if consecutive_failures >= _BREAKER_THRESHOLD:
                logger.warning("Pool gap goal=%s %s: breaker open after %d consecutive failures "
                               "— shortfall", goal_id, key, consecutive_failures)
                _short(slot, index, 'breaker')
                continue
            try:
                out = llm.generate_slot_meal(
                    slot=slot, user_prompt=user_prompt, goal=goal, exclusions=exclusions,
                    avoid_names=[m.get('name', '') for m in meals],
                )
                _add_usage(usage, out)

                def _regen(bad_meal, _slot=slot):
                    # Slot-aware re-prompt: keeps prompt + avoid list, counts usage.
                    again = llm.generate_slot_meal(
                        slot=_slot, user_prompt=user_prompt, goal=goal, exclusions=exclusions,
                        avoid_names=[m.get('name', '') for m in meals] + [bad_meal.get('name', '')],
                    )
                    _add_usage(usage, again)
                    return _normalise_generated(again['meal'])
                meal, _r, _s = repair_single_meal(
                    _normalise_generated(out['meal']), goal=goal, exclusions=exclusions,
                    llm=llm, meal_key=key, regenerate=_regen)
                meal = _normalise_generated(meal)
                stamp_generated_nutrition(meal, table)
            except SoftTimeLimitExceeded:
                raise
            except RepairBudgetExhausted as exc:
                logger.warning("Pool gap goal=%s %s: restriction repair exhausted (%s: %s; "
                               "violations=%s) — shortfall", goal_id, key, type(exc).__name__,
                               exc, exc.violations)
                _short(slot, index, 'repair_exhausted')
                consecutive_failures += 1
                continue
            except Exception as exc:  # noqa: BLE001 — a gap must never sink the plan
                logger.warning("Pool gap goal=%s %s: LLM fill failed (%s: %s) — shortfall",
                               goal_id, key, type(exc).__name__, exc,
                               exc_info=not isinstance(exc, ValueError))
                _short(slot, index, 'llm_error')
                consecutive_failures += 1
                continue
            consecutive_failures = 0
            meal.setdefault('servings', 1)
            meal.update({'source': 'generated', 'slot': slot, 'index': index,
                         'meal_identifier': pool_identifier(goal_id, slot, index)})
            meals.append(meal)
            covered.add((slot, index))

    # Suspect facets sent the mains to Gemini; if Gemini could not deliver,
    # a prompt-blind curated main beats a plan with no mains at all.
    if skip:
        missing = [(slot, index) for slot in MAIN_SLOTS
                   for index in range(counts.get(slot, 0)) if (slot, index) not in covered]
        if missing:
            logger.warning("Pool goal=%s: suspect facets and LLM short on %d main(s) — "
                           "falling back to prompt-blind corpus", goal_id, len(missing))
            fallback = select_recipes_for_pool(
                goal, status=status, facets=None,
                recently_served_ids=recently_served_curated_ids(goal),
            )
            by_pos = {(e['slot'], e['index']): e['recipe'] for e in fallback['meals']}
            for slot, index in missing:
                recipe = by_pos.get((slot, index))
                if recipe is None or recipe.id in served_ids:
                    continue
                meal = _render_curated(recipe, slot, index, goal_id, required_tags, gaps, table)
                meal['source'] = 'curated'
                meal['fallback'] = 'prompt_blind'
                meals.append(meal)
                covered.add((slot, index))
                served_ids.add(recipe.id)
                if shortfall_reasons.pop(f'{slot}:{index}', None) is not None:
                    shortfall[slot] -= 1
                    if not shortfall[slot]:
                        del shortfall[slot]
                gaps.append({'slot': slot, 'index': index, 'reason': 'suspect_fallback_corpus',
                             'required_tags': sorted(required_tags), 'unmatched_wanted': []})

    if not meals:
        raise ValueError(f"Meal pool for goal {goal_id} is empty (corpus + LLM both came up short)")

    order = {s: i for i, s in enumerate(POOL_SLOTS)}
    meals.sort(key=lambda m: (order[m['slot']], m['index']))

    if served_ids:
        CuratedRecipe.objects.filter(pk__in=served_ids).update(usage_count=F('usage_count') + 1)

    return PoolResult(
        meals=meals,
        grounding_debug={
            'facets': facets.to_debug(),
            'coverage': selection['coverage'],
            'gaps': gaps,
            'shortfall': shortfall,
            'shortfall_reasons': shortfall_reasons,
            'counts': counts,
        },
        llm_usage=usage,
    )
