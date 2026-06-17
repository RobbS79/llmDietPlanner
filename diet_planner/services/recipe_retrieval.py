"""
Recipe-grounding retrieval layer (Direction B, B3).

Turns plan constraints into concrete `CuratedRecipe` selections, then renders
each into the meal-object shape the rest of the pipeline already speaks (see
`tasks.transform_days_to_new_format` and `llm_service.generate_meal_plan_only`).

Design (docs/recipe-grounding-plan.md §5/§6), deliberately simple — SQL filters
+ greedy assembly, no pgvector (premature for a few hundred rows):

  * HARD GATE (a recipe is eligible for a slot iff ALL hold):
      - status == published
      - the slot is in meal_types
      - dietary_tags ⊇ the user's parsed restrictions
      - is_catalog_mapped(): every non-optional ingredient resolves to a
        canonical/catalog id. THIS is the gate that makes worldwide sourcing
        safe — an unbuyable recipe can never enter a plan.
  * SOFT RANK (higher = better): variety (penalise a cuisine/recipe already
    used in this plan), difficulty (prefer easy), popularity (usage_count),
    and optional calorie proximity to a per-meal target.
  * ASSEMBLY: greedy per-slot against the day, avoiding repeats until the
    eligible pool is exhausted.

Integration is an OVERLAY: the existing LLM path still produces a full plan
(guaranteed fallback for every slot), and `overlay_curated_recipes` swaps in a
real, attributed recipe wherever the corpus covers a slot. Uncovered slots keep
their generated meal, flagged source=generated. This is safe with a sparse
corpus and gets stronger as the corpus grows (B2).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Set

from django.conf import settings
from django.db.models import F

from diet_planner.models import CuratedRecipe
from diet_planner.services.prompt_facets import PromptFacets, extract_prompt_facets


# Free-text dietary restrictions -> structured dietary_tags. Substring match,
# case-folded, Czech + English. Conservative: only tags we can enforce against
# the corpus's dietary_tags vocabulary.
_DIETARY_KEYWORDS: Dict[str, str] = {
    'vegan': 'vegan', 'vegán': 'vegan', 'rostlinn': 'vegan',
    'vegetari': 'vegetarian', 'bezmas': 'vegetarian',
    'gluten': 'gluten_free', 'lepek': 'gluten_free', 'bezlepk': 'gluten_free',
    'celiak': 'gluten_free',
    'lakt': 'dairy_free', 'dairy': 'dairy_free', 'bez mlék': 'dairy_free',
    'mléčn': 'dairy_free',
    'low carb': 'low_carb', 'low-carb': 'low_carb', 'keto': 'low_carb',
    'nízkosacharid': 'low_carb', 'sacharid': 'low_carb',
}

# Plan slot -> the meal_types value used in the corpus. Our slots already match
# the corpus vocabulary 1:1, but keep the indirection explicit.
_SLOT_TO_MEAL_TYPE = {
    'breakfast': 'breakfast',
    'lunch': 'lunch',
    'dinner': 'dinner',
    'small_meal': 'small_meal',
    'snack': 'snack',
}


def parse_dietary_tags(text: Optional[str]) -> Set[str]:
    """Best-effort map free-text restrictions onto enforceable dietary_tags."""
    if not text:
        return set()
    low = text.casefold()
    return {tag for needle, tag in _DIETARY_KEYWORDS.items() if needle in low}


def published_pool(status: str = CuratedRecipe.Status.PUBLISHED) -> List[CuratedRecipe]:
    """All recipes of a status, loaded once. Membership in meal_types/dietary_tags
    is filtered in Python — JSONField `__contains` is unsupported on SQLite, and
    the corpus is small enough (a few hundred rows) that in-memory filtering is
    cheaper than the portability cost."""
    return list(CuratedRecipe.objects.filter(status=status))


def published_cuisine_vocab(
    *,
    status: str = CuratedRecipe.Status.PUBLISHED,
    pool: Optional[List[CuratedRecipe]] = None,
) -> List[str]:
    """Sorted distinct non-empty cuisines (lowercased) among published recipes."""
    recipes = pool if pool is not None else published_pool(status)
    return sorted({(r.cuisine or '').strip().lower() for r in recipes} - {''})


def _recipe_ingredient_tokens(recipe: CuratedRecipe) -> Set[str]:
    """Lowercased canonical + name tokens for ingredient matching."""
    tokens: Set[str] = set()
    for ing in (recipe.ingredients or []):
        for key in ('canonical', 'name'):
            val = ing.get(key)
            if val:
                tokens.add(str(val).strip().lower())
    return tokens


def _ingredient_present(needle: str, tokens: Set[str]) -> bool:
    return any(needle in tok for tok in tokens)


def recipe_matches_facets(recipe: CuratedRecipe, facets: PromptFacets) -> bool:
    """Hard gate. Only non-empty facet sets constrain eligibility."""
    if facets.cuisines:
        cuisine = (recipe.cuisine or '').strip().lower()
        if not cuisine or cuisine not in facets.cuisines:
            return False

    tokens = _recipe_ingredient_tokens(recipe)
    if facets.wanted_ingredients:
        if not any(_ingredient_present(w, tokens) for w in facets.wanted_ingredients):
            return False
    if facets.avoided_ingredients:
        if any(_ingredient_present(a, tokens) for a in facets.avoided_ingredients):
            return False
    return True


def eligible_recipes_for_slot(
    slot: str,
    required_tags: Set[str],
    *,
    pool: Optional[List[CuratedRecipe]] = None,
    status: str = CuratedRecipe.Status.PUBLISHED,
    exclude_ids: Optional[Set[int]] = None,
    facets: Optional[PromptFacets] = None,
) -> List[CuratedRecipe]:
    """Recipes that pass the HARD GATE for one slot (incl. prompt facets)."""
    meal_type = _SLOT_TO_MEAL_TYPE.get(slot, slot)
    candidates = pool if pool is not None else published_pool(status)
    exclude_ids = exclude_ids or set()

    out: List[CuratedRecipe] = []
    for r in candidates:
        if r.id in exclude_ids:
            continue
        if meal_type not in (r.meal_types or []):
            continue
        if not required_tags.issubset(set(r.dietary_tags or [])):
            continue
        if not r.is_catalog_mapped():
            continue
        if facets is not None and not recipe_matches_facets(r, facets):
            continue
        out.append(r)
    return out


def score_recipe(
    recipe: CuratedRecipe,
    *,
    used_recipe_ids: Set[int],
    used_cuisines: Sequence[str],
    target_calories: Optional[float] = None,
    facets: Optional[PromptFacets] = None,
) -> float:
    """Soft-ranking score; higher is better."""
    score = 0.0

    # Variety: strongly avoid the exact same dish twice; nudge away from a
    # cuisine already used in the plan so a week isn't monotone.
    if recipe.id in used_recipe_ids:
        score -= 100.0
    if recipe.cuisine and recipe.cuisine in used_cuisines:
        score -= 5.0 * list(used_cuisines).count(recipe.cuisine)

    # Difficulty: prefer easy (novice-friendly is the whole point).
    if recipe.difficulty == CuratedRecipe.Difficulty.EASY:
        score += 2.0

    # Popularity as a mild tie-breaker.
    score += min(recipe.usage_count, 10) * 0.1

    # Optional macro fit: closeness of base calories to the per-meal target.
    if target_calories:
        base_cal = (recipe.base_nutrition or {}).get('calories')
        if base_cal:
            rel = abs(base_cal - target_calories) / target_calories
            score += max(0.0, 3.0 * (1.0 - rel))  # full 3 pts at exact, 0 at >=100% off

    # Soft prompt-fit bonuses (additive; never override the variety/difficulty
    # /popularity terms above). Only the best-fitting *eligible* recipe wins.
    if facets is not None:
        tokens = _recipe_ingredient_tokens(recipe)
        wanted_hits = sum(1 for w in facets.wanted_ingredients if _ingredient_present(w, tokens))
        score += 0.5 * wanted_hits
        tags = set(recipe.dietary_tags or [])
        score += 1.0 * len(facets.emphases & tags)
        if 'quick' in facets.styles and recipe.total_time and recipe.total_time <= 20:
            score += 1.0

    return score


def select_recipes_for_plan(
    goal: Any,
    *,
    status: str = CuratedRecipe.Status.PUBLISHED,
    facets: Optional[PromptFacets] = None,
) -> Dict[str, Any]:
    """Greedy per-slot selection across the whole plan.

    Returns {'days': [{'day_number', 'slots': {slot_key: CuratedRecipe}}, ...],
             'coverage': {'filled': int, 'total': int}} where slot_key is
    'breakfast'/'lunch'/'dinner' or 'small_meal:N'/'snack:N'. Uncovered slots
    are simply absent — the caller falls back to the generated meal.
    """
    required_tags = parse_dietary_tags(getattr(goal, 'dietary_restrictions', None))
    num_days = int(getattr(goal, 'num_days', 7) or 7)
    small_n = int(getattr(goal, 'small_meals_per_day', 0) or 0)
    snack_n = int(getattr(goal, 'snacks_per_day', 0) or 0)

    main_slots = [s for s in ('breakfast', 'lunch', 'dinner') if getattr(goal, s, True)]
    slot_plan: List[tuple] = [(s, s) for s in main_slots]
    slot_plan += [('small_meal', f'small_meal:{i}') for i in range(small_n)]
    slot_plan += [('snack', f'snack:{i}') for i in range(snack_n)]

    pool = published_pool(status)
    used_recipe_ids: Set[int] = set()
    used_cuisines: List[str] = []
    days: List[Dict[str, Any]] = []
    filled = total = 0

    for day_number in range(1, num_days + 1):
        chosen: Dict[str, Any] = {}
        for slot_type, slot_key in slot_plan:
            total += 1
            candidates = eligible_recipes_for_slot(slot_type, required_tags, pool=pool, facets=facets)
            if not candidates:
                continue
            best = max(candidates, key=lambda r: score_recipe(
                r, used_recipe_ids=used_recipe_ids, used_cuisines=used_cuisines,
                facets=facets,
            ))
            chosen[slot_key] = best
            used_recipe_ids.add(best.id)
            if best.cuisine:
                used_cuisines.append(best.cuisine)
            filled += 1
        days.append({'day_number': day_number, 'slots': chosen})

    return {'days': days, 'coverage': {'filled': filled, 'total': total}}


# ---------------------------------------------------------------------------
# Rendering: CuratedRecipe -> the meal-object shape the pipeline consumes
# ---------------------------------------------------------------------------

def _fmt_grams(value: Optional[float]) -> Optional[str]:
    if value is None:
        return None
    iv = int(round(value))
    return f"{iv}g"


def scale_recipe_to_meal(
    recipe: CuratedRecipe,
    *,
    factor: float = 1.0,
) -> Dict[str, Any]:
    """Render a CuratedRecipe into a meal object, scaling quantities/nutrition by
    `factor` (default 1.0 = base servings). Ingredients keep their canonical /
    catalog_id so the shopping list stays coherent by construction. Source
    attribution is attached for the frontend credit line."""
    ingredients: List[Dict[str, Any]] = []
    for ing in (recipe.ingredients or []):
        qty = ing.get('quantity')
        ingredients.append({
            'name': ing.get('name'),
            'quantity': (round(qty * factor, 2) if isinstance(qty, (int, float)) else qty),
            'unit': ing.get('unit'),
            'canonical': ing.get('canonical'),
            'catalog_id': ing.get('catalog_id'),
            'optional': bool(ing.get('optional', False)),
        })

    instructions = [
        s.get('text') if isinstance(s, dict) else str(s)
        for s in (recipe.instructions or [])
        if (s.get('text') if isinstance(s, dict) else s)
    ]

    base = recipe.base_nutrition or {}
    nutritional_info = {
        'calories': int(round(base.get('calories', 0) * factor)) if base.get('calories') else None,
        'protein': _fmt_grams(base.get('protein', 0) * factor) if base.get('protein') is not None else None,
        'carbs': _fmt_grams(base.get('carbs', 0) * factor) if base.get('carbs') is not None else None,
        'fat': _fmt_grams(base.get('fat', 0) * factor) if base.get('fat') is not None else None,
    }

    return {
        'name': recipe.name_cs,
        'description': recipe.description or '',
        'food_category': '',  # stock-image slug; left blank -> generic fallback
        'preparation_time': recipe.total_time or recipe.prep_time or None,
        'ingredients': ingredients,
        'instructions': instructions,
        'nutritional_info': nutritional_info,
        # --- grounding provenance (consumed by RecipePage attribution) ---
        'source': 'curated',
        'curated_recipe_id': recipe.id,
        'curated_recipe_slug': recipe.slug,
        'source_name': recipe.source_name,
        'source_url': recipe.source_url,
        'source_author': recipe.source_author or '',
    }


def overlay_curated_recipes(
    transformed_days: List[Dict[str, Any]],
    goal: Any,
    *,
    status: str = CuratedRecipe.Status.PUBLISHED,
    facets: Optional[PromptFacets] = None,
) -> Dict[str, Any]:
    """Overlay real curated recipes onto facet-eligible slots of an already-
    generated plan. Uncovered/ineligible slots keep their generated meal
    (flagged source=generated). Preserves each meal's existing `meal_identifier`.
    Returns {'days', 'coverage', 'facets'}.
    """
    if facets is None:
        vocab = published_cuisine_vocab(status=status)
        facets = extract_prompt_facets(
            getattr(goal, 'prompt', '') or '',
            language=getattr(goal, 'language_code', 'cs') or 'cs',
            cuisine_vocab=vocab,
        )

    selection = select_recipes_for_plan(goal, status=status, facets=facets)
    sel_by_day = {d['day_number']: d['slots'] for d in selection['days']}

    promoted_ids: Set[int] = set()

    for idx, day in enumerate(transformed_days):
        day_number = day.get('day_number', idx + 1)
        slots = sel_by_day.get(day_number, {})

        # Main meals: breakfast/lunch/dinner are single objects.
        for slot in ('breakfast', 'lunch', 'dinner'):
            recipe = slots.get(slot)
            if recipe is not None and day.get(slot):
                meal = scale_recipe_to_meal(recipe)
                meal['meal_identifier'] = day[slot].get('meal_identifier')
                day[slot] = meal
                promoted_ids.add(recipe.id)

        # small_meals / snacks are lists; overlay positionally.
        for slot_type, list_key in (('small_meal', 'small_meals'), ('snack', 'snacks')):
            meals = day.get(list_key) or []
            for i, existing in enumerate(meals):
                recipe = slots.get(f'{slot_type}:{i}')
                if recipe is not None:
                    meal = scale_recipe_to_meal(recipe)
                    if isinstance(existing, dict):
                        meal['meal_identifier'] = existing.get('meal_identifier')
                    meals[i] = meal
                    promoted_ids.add(recipe.id)
            day[list_key] = meals

    # Mark every non-curated meal explicitly as generated for the frontend.
    for day in transformed_days:
        for slot in ('breakfast', 'lunch', 'dinner'):
            m = day.get(slot)
            if isinstance(m, dict) and 'source' not in m:
                m['source'] = 'generated'
        for list_key in ('small_meals', 'snacks'):
            for m in (day.get(list_key) or []):
                if isinstance(m, dict) and 'source' not in m:
                    m['source'] = 'generated'

    # Bump usage_count for what we served (variety/popularity signal).
    if promoted_ids:
        CuratedRecipe.objects.filter(pk__in=promoted_ids).update(
            usage_count=F('usage_count') + 1
        )

    return {
        'days': transformed_days,
        'coverage': selection['coverage'],
        'facets': facets.to_debug(),
    }


def grounding_enabled() -> bool:
    return bool(getattr(settings, 'RECIPE_GROUNDING_ENABLED', False))
