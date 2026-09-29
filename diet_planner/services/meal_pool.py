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
from dataclasses import dataclass, field
from typing import Any, Dict, List

from django.db.models import F

from diet_planner.models import CuratedRecipe
from diet_planner.services.meal_locator import MAIN_SLOTS, POOL_SLOTS, pool_identifier
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
    (moved here from tasks._build_protocol_prompt)."""
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
    for entry in selection['meals']:
        slot, index, recipe = entry['slot'], entry['index'], entry['recipe']
        meal, side_gap = render_curated_meal(
            recipe, target_kcal=_SLOT_DEFAULT_KCAL.get(slot), required_tags=required_tags)
        if side_gap:
            gaps.append({'slot': slot, 'index': index, 'reason': side_gap,
                         'required_tags': sorted(required_tags), 'unmatched_wanted': []})
        meal.update({'slot': slot, 'index': index,
                     'meal_identifier': pool_identifier(goal_id, slot, index)})
        meals.append(meal)
        served_ids.add(recipe.id)

    # Gap fill: every requested position with no curated meal.
    covered = {(m['slot'], m['index']) for m in meals}
    usage = _empty_usage()
    shortfall: Dict[str, int] = {}
    exclusions = RestrictionResolver().resolve(goal)
    user_prompt = _protocol_prompt(goal)
    for slot in POOL_SLOTS:
        for index in range(counts.get(slot, 0)):
            if (slot, index) in covered:
                continue
            key = f'{slot}:{index}'
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
                    return again['meal']
                meal, _r, _s = repair_single_meal(
                    out['meal'], goal=goal, exclusions=exclusions, llm=llm, meal_key=key,
                    regenerate=_regen)
            except RepairBudgetExhausted as exc:
                logger.warning("Pool gap %s: restriction repair exhausted (%s) — shortfall", key, exc)
                shortfall[slot] = shortfall.get(slot, 0) + 1
                continue
            except Exception as exc:  # noqa: BLE001 — a gap must never sink the plan
                logger.warning("Pool gap %s: LLM fill failed (%s) — shortfall", key, exc)
                shortfall[slot] = shortfall.get(slot, 0) + 1
                continue
            meal = dict(meal)
            meal.setdefault('servings', 1)
            meal.update({'source': 'generated', 'slot': slot, 'index': index,
                         'meal_identifier': pool_identifier(goal_id, slot, index)})
            meals.append(meal)

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
            'counts': counts,
        },
        llm_usage=usage,
    )
