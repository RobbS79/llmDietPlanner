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
      - dish_role can CARRY the slot (oběd needs a 'main'; snídaně needs a
        'breakfast' dish or a 'dessert'; večeře also takes a 'supper' dish or
        a 'soup'; a 'main' no longer carries snídaně; sides/dips never fill
        main slots; untagged '' passes until retag_dish_roles has run), with
        a select-time relaxation when a slot would otherwise starve
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

import logging
import random
import re
from typing import Any, Dict, List, Optional, Sequence, Set

from django.conf import settings
from django.db.models import F

from diet_planner.models import CanonicalIngredient, CuratedRecipe
from diet_planner.models.catalog import Availability
from diet_planner.services.canonical_lookup import fold_diacritics, resolve_canonical
from diet_planner.services.prompt_facets import (
    ENFORCEABLE_DIETARY_TAGS,
    PromptFacets,
    _coerce_time_minutes,
    extract_prompt_facets,
)

logger = logging.getLogger(__name__)


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

# Which dish roles can CARRY each slot (Czech meal culture: oběd is a warm
# main; večeře may also be a quick supper dish or a soup; snídaně is its own
# family of dishes). None = no role gate. Untagged ('') always passes —
# rollout safety until `retag_dish_roles` has tagged the corpus. 'light' is
# the legacy breakfast+supper bucket and keeps its old reach until retagged.
_SLOT_ALLOWED_ROLES = {
    'breakfast': {'breakfast', 'dessert', 'light'},
    'lunch': {'main'},
    'dinner': {'main', 'supper', 'soup', 'light'},
    'small_meal': None,
    'snack': None,
}


def _role_allowed(slot: str, role: str) -> bool:
    allowed = _SLOT_ALLOWED_ROLES.get(slot)
    return allowed is None or not role or role in allowed


def parse_dietary_tags(text: Optional[str]) -> Set[str]:
    """Best-effort map free-text restrictions onto enforceable dietary_tags."""
    if not text:
        return set()
    low = text.casefold()
    return {tag for needle, tag in _DIETARY_KEYWORDS.items() if needle in low}


# Profile preference ids (login_app onboarding quiz) -> enforceable corpus tags.
# high_protein is deliberately absent: it is a preference, not a restriction —
# hard-gating it would starve the pool. Allergies without a corpus tag
# (nuts/eggs/fish/soy) cannot be enforced yet and are skipped.
_PROFILE_STYLE_TAGS = {
    'vegetarian': 'vegetarian',
    'vegan': 'vegan',
    'gluten_free': 'gluten_free',
    'keto': 'low_carb',
}
_PROFILE_ALLERGY_TAGS = {
    'gluten': 'gluten_free',
    'lactose': 'dairy_free',
}


def parse_derived_dietary_tags(text: Optional[str]) -> Set[str]:
    """Read back the tags persisted by `store_derived_dietary_tags`.

    Exact comma-separated slugs, NOT the fuzzy matching `parse_dietary_tags`
    does: that one maps the substring 'sacharid' onto low_carb, which any
    sentence mentioning sacharidy would trip. Fine as a hint over a short
    restrictions field, catastrophic over a whole prompt.
    """
    if not text:
        return set()
    return {t.strip() for t in text.split(',') if t.strip()} & ENFORCEABLE_DIETARY_TAGS


def store_derived_dietary_tags(goal, tags: Set[str]) -> None:
    """Persist prompt-stated restrictions on the goal so later machine gates can
    enforce what the generator honoured. Never raises and never widens: tags are
    only ever added, so a flaky extraction can't silently drop a restriction the
    user already has."""
    clean = {str(t).strip() for t in (tags or set())} & ENFORCEABLE_DIETARY_TAGS
    if not clean or not getattr(goal, 'pk', None):
        return
    merged = clean | parse_derived_dietary_tags(getattr(goal, 'derived_dietary_tags', None))
    value = ','.join(sorted(merged))
    if value == (goal.derived_dietary_tags or ''):
        return
    try:
        goal.derived_dietary_tags = value
        goal.save(update_fields=['derived_dietary_tags'])
        logger.info("derived_dietary_tags goal=%s tags=%s", goal.pk, value)
    except Exception:  # never break generation over a bookkeeping write
        logger.warning("derived_dietary_tags_save_failed goal=%s", goal.pk, exc_info=True)


def plan_time_budget(plan) -> Optional[int]:
    """The cooking-time cap the user stated in the plan prompt, read back off
    the plan's stored facets. None when no cap was stated.

    `grounding_debug` was written at generation and never read again, so a limit
    typed into the prompt applied to the generated plan and then evaporated:
    prod goal 141 asked for "max 30 minut" and the chef chat offered 35, 45 and
    90 minute swaps. Restrictions must outlive the turn that stated them — the
    same reason `required_tags_for_goal` reads `derived_dietary_tags` back.

    Never raises: a plan from before grounding, or with a half-written blob,
    reads as "no limit" rather than breaking the swap.
    """
    debug = getattr(plan, 'grounding_debug', None)
    if not isinstance(debug, dict):
        return None
    facets = debug.get('facets')
    if not isinstance(facets, dict):
        return None
    return _coerce_time_minutes(facets.get('max_time_minutes'))


def required_tags_for_goal(goal) -> Set[str]:
    """The effective hard dietary gate for a goal: free-text restrictions on the
    goal UNIONed with the user's live profile styles/allergies AND anything the
    user stated in the prompt itself (see `derived_dietary_tags`). Preferences
    the user stored once apply everywhere (generation, replace, refine) without
    re-stating them per plan; profile edits take effect immediately. Never
    raises — any missing/malformed piece just contributes nothing."""
    tags = parse_dietary_tags(getattr(goal, 'dietary_restrictions', None))
    tags |= parse_derived_dietary_tags(getattr(goal, 'derived_dietary_tags', None))
    try:
        prefs = goal.user.profile.dietary_preferences or {}
    except AttributeError:
        return tags
    if not isinstance(prefs, dict):
        return tags
    styles = prefs.get('dietary_styles')
    if isinstance(styles, list):
        tags |= {_PROFILE_STYLE_TAGS[s] for s in styles if s in _PROFILE_STYLE_TAGS}
    allergies = prefs.get('allergies')
    if isinstance(allergies, list):
        tags |= {_PROFILE_ALLERGY_TAGS[a] for a in allergies if a in _PROFILE_ALLERGY_TAGS}
    return tags


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


def _recipe_canonicals(recipe: CuratedRecipe) -> Set[str]:
    """Canonical ingredient slugs for a recipe — the unit for ingredient reuse.

    Using canonicals (not free-text names) means two recipes that both use
    chicken count as sharing it even if named differently.
    """
    out: Set[str] = set()
    for ing in (recipe.ingredients or []):
        c = ing.get('canonical')
        if c:
            out.add(str(c).strip().lower())
    return out


# Broad food-group words (EN + common Czech forms) -> CanonicalIngredient
# category. "maso nebo ryba" is a claim about ingredient CATEGORIES, not about
# any substring — the plan-131 bug was matching these as English substrings
# against Czech names (zero hits corpus-wide).
_WANTED_CATEGORY_WORDS: Dict[str, str] = {
    'meat': 'meat', 'maso': 'meat', 'masa': 'meat', 'masem': 'meat',
    'fish': 'fish', 'ryba': 'fish', 'ryby': 'fish', 'rybu': 'fish',
    'seafood': 'fish',
    'vegetable': 'vegetables', 'vegetables': 'vegetables',
    'zelenina': 'vegetables', 'zeleninu': 'vegetables', 'zeleniny': 'vegetables',
    'fruit': 'fruits', 'fruits': 'fruits', 'ovoce': 'fruits',
    'legumes': 'legumes', 'luštěniny': 'legumes',
    'nuts': 'nuts', 'ořechy': 'nuts',
    'egg': 'eggs', 'eggs': 'eggs', 'vejce': 'eggs',
    'dairy': 'dairy',
}

# Accent-free lookup ("lusteniny", "orechy") — folded keys must not shadow
# exact ones, so this is a separate fallback dict.
_WANTED_CATEGORY_WORDS_FOLDED = {
    fold_diacritics(k): v for k, v in _WANTED_CATEGORY_WORDS.items()
}


class WantedIngredientMatcher:
    """Match a user's ingredient tokens against a recipe's ingredients.

    Each token becomes one concept, resolved at build time (one DB pass):
      1. a broad food-group word ("maso", "fish") -> any ingredient whose
         canonical belongs to that CanonicalIngredient.category;
      2. a resolvable ingredient name ("rýže" -> canonical `rice`, grains) ->
         slug equality, or slug-token superset within the SAME category, so
         basmati-rice counts as rice but rice-vinegar (condiments) never does;
      3. otherwise a word-boundary text match on ingredient names/canonicals
         (no substring false positives).

    `hits()` returns the number of DISTINCT concepts a recipe satisfies —
    the ranking weight in `score_recipe`, and the prompt-fit signal for the
    overlay threshold.
    """

    def __init__(self, concepts: List[tuple], slug_category: Dict[str, str]):
        self._concepts = concepts
        self._slug_category = slug_category

    @classmethod
    def build(cls, tokens) -> 'WantedIngredientMatcher':
        clean = {str(t).strip().lower() for t in (tokens or ()) if str(t).strip()}
        if not clean:
            return cls([], {})
        slug_category = dict(CanonicalIngredient.objects.values_list('slug', 'category'))
        concepts: List[tuple] = []
        for tok in sorted(clean):
            category = (_WANTED_CATEGORY_WORDS.get(tok)
                        or _WANTED_CATEGORY_WORDS_FOLDED.get(fold_diacritics(tok)))
            if category:
                concepts.append(('category', category))
                continue
            ci = resolve_canonical(tok)
            if ci is not None:
                concepts.append((
                    'canonical', ci.slug, ci.category, frozenset(ci.slug.split('-')),
                ))
                continue
            concepts.append(('text', re.compile(
                r'\b' + re.escape(tok) + r'\b', re.IGNORECASE,
            )))
        return cls(concepts, slug_category)

    def has_concepts(self) -> bool:
        return bool(self._concepts)

    def hits(self, recipe: CuratedRecipe) -> int:
        ings = recipe.ingredients or []
        slugs = [
            str(i.get('canonical')).strip().lower()
            for i in ings if i.get('canonical')
        ]
        texts = [
            str(i.get(key)).replace('-', ' ')
            for i in ings for key in ('name', 'canonical') if i.get(key)
        ]
        count = 0
        for concept in self._concepts:
            kind = concept[0]
            if kind == 'category':
                matched = any(self._slug_category.get(s) == concept[1] for s in slugs)
            elif kind == 'canonical':
                _, slug, category, slug_tokens = concept
                matched = any(
                    s == slug
                    or (slug_tokens <= set(s.split('-'))
                        and self._slug_category.get(s) == category)
                    for s in slugs
                )
            else:
                matched = any(concept[1].search(t) for t in texts)
            if matched:
                count += 1
        return count


def _facet_matcher(facets: PromptFacets, attr: str, tokens) -> WantedIngredientMatcher:
    """Build lazily, cache on the facets instance so per-candidate scoring in a
    max()/sorted() loop does the DB work exactly once per selection run."""
    matcher = facets.__dict__.get(attr)
    if matcher is None:
        matcher = WantedIngredientMatcher.build(tokens)
        facets.__dict__[attr] = matcher
    return matcher


def wanted_matcher(facets: PromptFacets) -> WantedIngredientMatcher:
    return _facet_matcher(facets, '_wanted_matcher', facets.wanted_ingredients)


def _avoided_matcher(facets: PromptFacets) -> WantedIngredientMatcher:
    return _facet_matcher(facets, '_avoided_matcher', facets.avoided_ingredients)


def recipe_matches_facets(recipe: CuratedRecipe, facets: PromptFacets) -> bool:
    """Hard gate: EXCLUSIONS only (issue #47 — restrictions gate, preferences
    rank). Gates on explicitly requested cuisine, a stated time limit, and
    avoided ingredients. Wanted ingredients rank in `score_recipe` instead."""
    if facets.cuisines:
        cuisine = (recipe.cuisine or '').strip().lower()
        if not cuisine or cuisine not in facets.cuisines:
            return False

    # Stated time budget is a hard cap; recipes with unknown time pass.
    if facets.max_time_minutes:
        total = recipe.total_time
        if total and total > facets.max_time_minutes:
            return False

    if facets.avoided_ingredients:
        tokens = _recipe_ingredient_tokens(recipe)
        if any(_ingredient_present(a, tokens) for a in facets.avoided_ingredients):
            return False
        # Substring is kept for backward compat; the matcher adds category /
        # canonical / Czech-aware avoidance ("nechci ryby" blocks all fish).
        if _avoided_matcher(facets).hits(recipe):
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
    enforce_mapping: bool = True,
    enforce_roles: bool = True,
) -> List[CuratedRecipe]:
    """Recipes that pass the HARD GATE for one slot (incl. prompt facets).

    `enforce_mapping=False` relaxes ONLY the catalog-mapping gate — used for a
    user's own chat_web drafts (spec 2026-07-27, decision 1).
    `enforce_roles=False` relaxes ONLY the dish-role slot-fit gate — used as
    the select-time fallback when a slot has no role-appropriate candidates.
    All other gates (slot, dietary, facets) always apply."""
    meal_type = _SLOT_TO_MEAL_TYPE.get(slot, slot)
    candidates = pool if pool is not None else published_pool(status)
    exclude_ids = exclude_ids or set()

    out: List[CuratedRecipe] = []
    for r in candidates:
        if r.id in exclude_ids:
            continue
        if meal_type not in (r.meal_types or []):
            continue
        if enforce_roles and not _role_allowed(slot, r.dish_role or ''):
            continue
        if not required_tags.issubset(set(r.dietary_tags or [])):
            continue
        if enforce_mapping and not r.is_catalog_mapped():
            continue
        # Unshoppable in an ordinary Czech supermarket. Unconditional: after
        # unpublish_unshoppable this is belt-and-braces for published rows, but
        # it still covers the enforce_mapping=False chat-draft path.
        if r.shopping_difficulty == Availability.SPECIALTY:
            continue
        if facets is not None and not recipe_matches_facets(r, facets):
            continue
        out.append(r)
    return out


# One matched wanted concept must outrank the sum of all comfort terms.
_WANTED_HIT_WEIGHT = 20.0

# Novelty: a recipe this user was already served recently ranks below fresh
# near-peers, but the penalty stays under _WANTED_HIT_WEIGHT so prompt fit
# still wins ("kuřecí" beats a fresh cabbage salad even on a repeat).
_RECENT_SERVE_PENALTY = 8.0

# Shopping friction. At 1.0 per blocker a single blocker is exactly enough to
# push a findable recipe out of the _SAMPLING_WINDOW against an equally-scoring
# common one — it loses ties, which is the intent. Against _WANTED_HIT_WEIGHT
# (20.0) it is negligible, so it can never override what the user asked for.
_SHOPPING_BLOCKER_PENALTY = 1.0
_SHOPPING_PENALTY_CAP = 3.0

# Near-tied candidates (within this score distance of the top) are sampled,
# not argmax'd, so equally-good dishes rotate across plans instead of one
# fixed winner serving forever. Sized so deliberate orderings stay strict:
# wanted hits (20), cuisine variety (5), same-dish reuse (100), difficulty
# (2), strong ingredient reuse (up to 6) — and crucially the calorie
# size-sanity spread, now per-portion (a 307-kcal/portion side vs a
# 680-kcal/portion main at a 700 target differs by ~1.6, which must stay a
# deterministic win for the main).
_SAMPLING_WINDOW = 1.0

# How far back a user's plans count as "recent" for the novelty penalty.
_RECENT_SERVE_WINDOW_DAYS = 14


def recently_served_curated_ids(goal: Any, *, window_days: int = _RECENT_SERVE_WINDOW_DAYS) -> Set[int]:
    """CuratedRecipe ids served to this goal's user in their recent plans.

    Reads Recipe.curated_recipe_slug across the user's other goals inside the
    window. Never raises: goals without a persisted user (tests, simulation
    namespaces) yield an empty set — the penalty simply doesn't apply.
    """
    from datetime import timedelta

    from django.utils import timezone

    from diet_planner.models import Recipe

    user_id = getattr(goal, 'user_id', None)
    goal_pk = getattr(goal, 'pk', None)
    if not user_id or not goal_pk:
        return set()
    since = timezone.now() - timedelta(days=window_days)
    slugs = (
        Recipe.objects
        .filter(dietary_goal__user_id=user_id, created_at__gte=since)
        .exclude(dietary_goal_id=goal_pk)
        .exclude(curated_recipe_slug='')
        .values_list('curated_recipe_slug', flat=True)
    )
    return set(
        CuratedRecipe.objects.filter(slug__in=set(slugs)).values_list('id', flat=True)
    )

# Wanted tokens describe the plan's MAIN components ("maso nebo ryba" is about
# lunches/dinners, not breakfast or snacks) — the prompt-fit threshold below
# only applies to these slots.
_WANTED_FIT_SLOTS = ('lunch', 'dinner')


def score_recipe(
    recipe: CuratedRecipe,
    *,
    used_recipe_ids: Set[int],
    used_cuisines: Sequence[str],
    target_calories: Optional[float] = None,
    facets: Optional[PromptFacets] = None,
    used_canonicals: Optional[Set[str]] = None,
    recently_served_ids: Optional[Set[int]] = None,
) -> float:
    """Soft-ranking score; higher is better."""
    score = 0.0

    # Novelty across plans: this user already got this dish recently.
    if recently_served_ids and recipe.id in recently_served_ids:
        score -= _RECENT_SERVE_PENALTY

    # Variety: strongly avoid the exact same dish twice; nudge away from a
    # cuisine already used in the plan so a week isn't monotone.
    if recipe.id in used_recipe_ids:
        score -= 100.0
    if recipe.cuisine and recipe.cuisine in used_cuisines:
        score -= 5.0 * list(used_cuisines).count(recipe.cuisine)

    # Difficulty: prefer easy (novice-friendly is the whole point).
    if recipe.difficulty == CuratedRecipe.Difficulty.EASY:
        score += 2.0

    # Shopping friction: prefer a dish the user can buy in one stop. Driven by
    # the blocker list, not the tier, so an 'unrated' row (the model default,
    # i.e. merely not-yet-recomputed) costs nothing.
    if (getattr(settings, 'AVAILABILITY_RANKING_ENABLED', False)
            and recipe.shopping_difficulty != Availability.COMMON):
        score -= min(
            len(recipe.shopping_blockers or []) * _SHOPPING_BLOCKER_PENALTY,
            _SHOPPING_PENALTY_CAP)

    # Optional macro fit: closeness of PER-PORTION calories to the per-meal
    # target. base_nutrition is whole-recipe (per base_servings) — comparing
    # totals made 1-2 serving sides look like perfect mains (goal 133).
    if target_calories:
        per_portion = per_portion_calories(recipe)
        if per_portion:
            rel = abs(per_portion - target_calories) / target_calories
            score += max(0.0, 3.0 * (1.0 - rel))  # full 3 pts at exact, 0 at >=100% off

    # Prompt fit. Wanted-ingredient hits are what the user actually asked for
    # ("maso nebo ryba"), so they carry a weight that DOMINATES the comfort
    # terms above (difficulty+popularity+reuse+calorie sum to ~12 worst case).
    if facets is not None:
        score += _WANTED_HIT_WEIGHT * wanted_matcher(facets).hits(recipe)
        tags = set(recipe.dietary_tags or [])
        score += 1.0 * len(facets.emphases & tags)
        if 'quick' in facets.styles and recipe.total_time and recipe.total_time <= 20:
            score += 1.0

    # Ingredient reuse: prefer recipes that share canonical ingredients with
    # those already chosen for the plan, so the shopping list stays short. Mild
    # weight + cap so it nudges selection without overriding dietary/macro fit
    # or making the week monotone (the cuisine-variety penalty above counters
    # over-concentration).
    if used_canonicals:
        shared = len(_recipe_canonicals(recipe) & used_canonicals)
        score += min(shared * 0.6, 6.0)

    return score


def select_recipes_for_plan(
    goal: Any,
    *,
    status: str = CuratedRecipe.Status.PUBLISHED,
    facets: Optional[PromptFacets] = None,
    calorie_targets: Optional[Dict[int, Dict[str, float]]] = None,
    recently_served_ids: Optional[Set[int]] = None,
) -> Dict[str, Any]:
    """Greedy per-slot selection across the whole plan.

    `calorie_targets` is {day_number: {slot_key: kcal}} (the overlay derives it
    from the generated plan) and feeds the size-sanity term in `score_recipe`
    so a 400-kcal side can't win a 700-kcal main slot.

    Returns {'days': [{'day_number', 'slots': {slot_key: CuratedRecipe}}, ...],
             'coverage': {'filled': int, 'total': int},
             'gaps': [{day_number, slot, reason, required_tags,
                       unmatched_wanted}, ...]} where slot_key is
    'breakfast'/'lunch'/'dinner' or 'small_meal:N'/'snack:N'. Uncovered slots
    are simply absent — the caller falls back to the generated meal — and every
    one is recorded in `gaps` as a corpus-acquisition signal.
    """
    required_tags = required_tags_for_goal(goal)
    num_days = int(getattr(goal, 'num_days', 7) or 7)
    small_n = int(getattr(goal, 'small_meals_per_day', 0) or 0)
    snack_n = int(getattr(goal, 'snacks_per_day', 0) or 0)

    main_slots = [s for s in ('breakfast', 'lunch', 'dinner') if getattr(goal, s, True)]
    slot_plan: List[tuple] = [(s, s) for s in main_slots]
    slot_plan += [('small_meal', f'small_meal:{i}') for i in range(small_n)]
    slot_plan += [('snack', f'snack:{i}') for i in range(snack_n)]

    pool = published_pool(status)
    goal_seed = getattr(goal, 'pk', None) or getattr(goal, 'id', None) or 0
    used_recipe_ids: Set[int] = set()
    used_cuisines: List[str] = []
    used_canonicals: Set[str] = set()  # ingredient reuse across the whole plan
    days: List[Dict[str, Any]] = []
    gaps: List[Dict[str, Any]] = []
    filled = total = 0

    def record_gap(day_number: int, slot_key: str, reason: str) -> None:
        gap = {
            'day_number': day_number,
            'slot': slot_key,
            'reason': reason,
            'required_tags': sorted(required_tags),
            'unmatched_wanted': sorted(facets.wanted_ingredients) if facets else [],
        }
        gaps.append(gap)
        logger.info("Recipe grounding corpus gap: %s", gap)

    for day_number in range(1, num_days + 1):
        chosen: Dict[str, Any] = {}
        for slot_type, slot_key in slot_plan:
            total += 1
            candidates = eligible_recipes_for_slot(slot_type, required_tags, pool=pool, facets=facets)
            if not candidates:
                # Role-relaxed fallback: serving a role-mismatched dish beats
                # starving the slot, but it is recorded as a corpus gap.
                candidates = eligible_recipes_for_slot(
                    slot_type, required_tags, pool=pool, facets=facets, enforce_roles=False)
                if candidates:
                    record_gap(day_number, slot_key, 'role_relaxed')
                else:
                    record_gap(day_number, slot_key, 'no_eligible_recipes')
                    continue
            target = slot_target(calorie_targets, day_number, slot_key)
            scored = [(score_recipe(
                r, used_recipe_ids=used_recipe_ids, used_cuisines=used_cuisines,
                facets=facets, used_canonicals=used_canonicals,
                target_calories=target, recently_served_ids=recently_served_ids,
            ), r) for r in candidates]
            top = max(s for s, _ in scored)
            window = [r for s, r in scored if s >= top - _SAMPLING_WINDOW]
            # Seeded per (goal, day, slot): rotation across plans, stable
            # within one plan (re-running the same goal reproduces it).
            rng = random.Random(f'{goal_seed}:{day_number}:{slot_key}')
            best = rng.choice(window)
            # Prompt-fit threshold (main slots only): if even the best curated
            # candidate matches nothing the user asked for, the generated meal
            # — written with full prompt context — is the better answer.
            if (
                facets is not None and facets.wanted_ingredients
                and slot_type in _WANTED_FIT_SLOTS
                and wanted_matcher(facets).hits(best) == 0
            ):
                record_gap(day_number, slot_key, 'wanted_fit_below_threshold')
                continue
            chosen[slot_key] = best
            used_recipe_ids.add(best.id)
            if best.cuisine:
                used_cuisines.append(best.cuisine)
            used_canonicals |= _recipe_canonicals(best)
            filled += 1
        days.append({'day_number': day_number, 'slots': chosen})

    return {'days': days, 'coverage': {'filled': filled, 'total': total}, 'gaps': gaps}


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
    portions: Optional[int] = None,
) -> Dict[str, Any]:
    """Render a CuratedRecipe into a meal object, scaling quantities/nutrition by
    `factor` (default 1.0 = base servings). `portions` overrides factor: serve
    that many of the recipe's base_servings portions (factor = portions/base),
    and the meal's `servings` reports the portions actually served. Ingredients
    keep their canonical / catalog_id so the shopping list stays coherent by
    construction. Source attribution is attached for the frontend credit line."""
    if portions is not None:
        factor = portions / max(int(recipe.base_servings or 1), 1)
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
        'servings': portions if portions is not None else recipe.base_servings,
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


def per_portion_calories(recipe: CuratedRecipe) -> Optional[float]:
    """Calories of ONE portion. base_nutrition is the whole-recipe total for
    base_servings portions, so anything user-facing or slot-fitting has to
    divide first — serving a 4-portion bake's 2150 kcal as a single lunch is
    the bug this exists to prevent."""
    calories = (recipe.base_nutrition or {}).get('calories')
    if not isinstance(calories, (int, float)) or calories <= 0:
        return None
    return calories / max(int(recipe.base_servings or 1), 1)


def portions_for_target(recipe: CuratedRecipe, target: Optional[float]) -> int:
    """How many of the recipe's portions fill the slot's calorie target.
    Without a target (or usable nutrition) serve ONE portion — never the whole
    multi-serving pot (goal 133: 1709 kcal / 6 servings rendered as one
    dinner). Capped at base_servings: we never invent more food than the
    recipe makes."""
    base = max(int(recipe.base_servings or 1), 1)
    per_portion = per_portion_calories(recipe)
    if not target or not per_portion:
        return 1
    return max(1, min(base, int(round(target / per_portion))))


_KCAL_IN_TEXT_RE = re.compile(r'(\d+(?:[.,]\d+)?)\s*kcal', re.IGNORECASE)
_LEADING_NUMBER_RE = re.compile(r'(\d+(?:[.,]\d+)?)')


def _meal_calories(meal: Any) -> Optional[float]:
    """Calories of a generated meal, tolerating every nutritional_info shape
    Gemini actually emits: a dict with numeric calories, a dict with string
    calories ("450" / "450 kcal"), or a bare string blob ("cca 650 kcal, 30 g
    bílkovin" — prod goal 134 crashed on exactly that). Returns None when no
    number can be trusted."""
    if not isinstance(meal, dict):
        return None
    info = meal.get('nutritional_info')
    if isinstance(info, dict):
        calories = info.get('calories')
        if isinstance(calories, (int, float)):
            return float(calories) if calories > 0 else None
        if isinstance(calories, str):
            m = _LEADING_NUMBER_RE.search(calories)
            if m:
                value = float(m.group(1).replace(',', '.'))
                return value if value > 0 else None
        return None
    if isinstance(info, str):
        # A free-text blob mixes numbers ("30 g bílkovin"); only a number
        # explicitly tied to kcal is safe to read.
        m = _KCAL_IN_TEXT_RE.search(info)
        if m:
            value = float(m.group(1).replace(',', '.'))
            return value if value > 0 else None
    return None


# Fallback per-slot calorie targets (roughly a 2000-kcal adult day) used when
# the generated plan carries no usable number for a slot. Without one, the
# overlay served exactly one base-portion — for piece-counted recipes that is
# a fraction of a meal (prod goal 134: 1/12 muffin batch = 16-kcal breakfast).
_SLOT_DEFAULT_KCAL: Dict[str, float] = {
    'breakfast': 450.0,
    'lunch': 650.0,
    'dinner': 550.0,
    'small_meal': 250.0,
    'snack': 250.0,
}


def slot_target(
    calorie_targets: Optional[Dict[int, Dict[str, float]]],
    day_number: int,
    slot_key: str,
) -> Optional[float]:
    """Calorie target for a slot: the generated plan's own number when usable,
    else the slot-type default. slot_key is 'lunch' or 'small_meal:0'-style."""
    derived = (calorie_targets or {}).get(day_number, {}).get(slot_key)
    if derived:
        return derived
    return _SLOT_DEFAULT_KCAL.get(slot_key.split(':', 1)[0])


def _calorie_targets_from_days(
    transformed_days: List[Dict[str, Any]],
) -> Dict[int, Dict[str, float]]:
    """Per-slot calorie targets read off the generated plan itself — the LLM
    already sized each meal for this user, so its calories are the best
    available 'how big should this slot be' signal (no goal field needed)."""
    targets: Dict[int, Dict[str, float]] = {}
    for idx, day in enumerate(transformed_days):
        day_number = day.get('day_number', idx + 1)
        per_slot: Dict[str, float] = {}

        def add(slot_key: str, meal: Any) -> None:
            calories = _meal_calories(meal)
            if calories is not None:
                per_slot[slot_key] = calories

        for slot in ('breakfast', 'lunch', 'dinner'):
            add(slot, day.get(slot))
        for slot_type, list_key in (('small_meal', 'small_meals'), ('snack', 'snacks')):
            for i, meal in enumerate(day.get(list_key) or []):
                add(f'{slot_type}:{i}', meal)
        targets[day_number] = per_slot
    return targets


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
    Returns {'days', 'coverage', 'facets', 'gaps'}.
    """
    if facets is None:
        vocab = published_cuisine_vocab(status=status)
        facets = extract_prompt_facets(
            getattr(goal, 'prompt', '') or '',
            language=getattr(goal, 'language_code', 'cs') or 'cs',
            cuisine_vocab=vocab,
        )

    # Restrictions stated in the prompt are enforced here at generation, but the
    # extraction result used to die with this call — leaving refine/replace/swap
    # blind to them. Persist so the rest of the product honours the same rules.
    store_derived_dietary_tags(goal, getattr(facets, 'dietary', set()))

    calorie_targets = _calorie_targets_from_days(transformed_days)
    selection = select_recipes_for_plan(
        goal, status=status, facets=facets,
        calorie_targets=calorie_targets,
        recently_served_ids=recently_served_curated_ids(goal),
    )
    sel_by_day = {d['day_number']: d['slots'] for d in selection['days']}

    promoted_ids: Set[int] = set()
    goal_id = getattr(goal, 'id', None) or getattr(goal, 'pk', 0)
    rescued = 0

    # Suspect facets = the user said something concrete and we failed to parse
    # it. The generated plan is then the only prompt-aware artifact: keep its
    # meals, only fill slots that are actually empty (rescue-only).
    rescue_only = bool(getattr(facets, 'suspect', False))
    if rescue_only:
        logger.warning(
            "Facet extraction suspect for goal %s: overlay running rescue-only "
            "(generated meals kept)", goal_id)

    for idx, day in enumerate(transformed_days):
        day_number = day.get('day_number', idx + 1)
        slots = sel_by_day.get(day_number, {})

        # Main meals: breakfast/lunch/dinner are single objects. A chosen
        # recipe attaches even when the slot is empty — a truncated/stub LLM
        # response (dropped in transform) must not discard a full curated
        # selection with it (prod goal 133: 4/4 chosen, 0 applied, plan
        # failed the completeness guard).
        for slot in ('breakfast', 'lunch', 'dinner'):
            recipe = slots.get(slot)
            if recipe is None:
                continue
            existing = day.get(slot)
            if existing and rescue_only:
                continue
            target = slot_target(calorie_targets, day_number, slot)
            meal = scale_recipe_to_meal(recipe, portions=portions_for_target(recipe, target))
            meal['meal_identifier'] = (
                (existing or {}).get('meal_identifier')
                or f"{goal_id}:{day_number}:{slot}:0"
            )
            if not existing:
                rescued += 1
            day[slot] = meal
            promoted_ids.add(recipe.id)

        # small_meals / snacks are lists; overlay positionally, appending
        # rescued meals for chosen indices past the (possibly hollowed) list.
        for slot_type, list_key in (('small_meal', 'small_meals'), ('snack', 'snacks')):
            meals = day.get(list_key) or []
            chosen = {
                int(k.split(':', 1)[1]): r
                for k, r in slots.items() if k.startswith(slot_type + ':')
            }
            for i in range(max([len(meals)] + [x + 1 for x in chosen])):
                recipe = chosen.get(i)
                if recipe is None:
                    continue
                if i < len(meals) and rescue_only:
                    continue
                existing = meals[i] if i < len(meals) else None
                target = slot_target(calorie_targets, day_number, f'{slot_type}:{i}')
                meal = scale_recipe_to_meal(recipe, portions=portions_for_target(recipe, target))
                meal['meal_identifier'] = (
                    (existing.get('meal_identifier') if isinstance(existing, dict) else None)
                    or f"{goal_id}:{day_number}:{slot_type}:{i}"
                )
                if i < len(meals):
                    meals[i] = meal
                else:
                    meals.append(meal)
                    rescued += 1
                promoted_ids.add(recipe.id)
            day[list_key] = meals

    if rescued:
        logger.info("Recipe grounding rescued %d empty slot(s) with curated recipes", rescued)

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
        'coverage': {**selection['coverage'], 'rescued': rescued},
        'facets': facets.to_debug(),
        'gaps': selection['gaps'],
    }


def grounding_enabled() -> bool:
    return bool(getattr(settings, 'RECIPE_GROUNDING_ENABLED', False))
