"""
Recipe / shopping-list coherence checks.

A recurring class of production bug: the meal plan describes an ingredient
as "already prepared" / "leftover" / "from yesterday" — but the same
ingredient still appears on the shopping list with a price, so the user
is told to BUY meat that the recipe says they should ALREADY HAVE.

The user-visible symptom reported on plan 108, recipe 108:1:dinner:0:
recipe text says "the beef (klizka) is already prepared" while the
shopping list says "buy 300 g klizka". Paying customers see this as
garbage output and rightly stop trusting the product.

This module gives us three things:

1. `detect_pre_prepared_ingredient_names(meal)` — scans a meal's
   description / instructions for multilingual "already prepared / leftover"
   markers and returns the set of ingredient names that appear inside
   such a sentence. Used both to filter ingredient lists before display
   and to validate generated plans.

2. `filter_pre_prepared(meal)` — returns a shallow copy of the meal whose
   `ingredients[]` no longer contains items marked / described as
   pre-prepared. Each filtered ingredient is moved into
   `pre_prepared_ingredients[]` so the UI can still render "uses leftover
   beef from yesterday" without telling the user to buy it.

3. `find_coherence_issues(days, shopping_list)` — returns a list of
   structured issues describing each (ingredient × meal) conflict. The
   validator promotes any non-empty result to a hard error so we refuse
   to publish a self-contradictory plan.

The detection layer is intentionally permissive (false-positive friendly):
it is better to occasionally drop a fresh ingredient than to keep telling
a paying customer to buy something the recipe says is already cooked.
The patterns are sourced from the languages we currently support: cs, sk,
pl, hu, ro, bg, de, en.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pre-prepared phrase patterns (per language).
#
# We match on substrings, lower-cased, with diacritics intact. Phrases are
# deliberately short and pragmatic — "already cooked", "from yesterday",
# "leftover", "pre-prepared". Add more as bug reports surface; tests in
# tests/test_recipe_coherence.py document the exact strings each rule
# catches.
# ---------------------------------------------------------------------------

_PRE_PREPARED_PHRASES: Tuple[str, ...] = (
    # English
    "already prepared", "already cooked", "already made", "already baked",
    "pre-prepared", "pre prepared", "pre-cooked", "pre cooked",
    "leftover", "left over", "left-over",
    "from yesterday", "from the previous", "from previous day",
    "from previous meal", "from the day before",
    # Czech
    "už připravené", "už připravená", "už připravený", "už uvařené",
    "už uvařená", "už uvařený", "již připravené", "již připravená",
    "již připravený", "již uvařené", "již uvařená", "již uvařený",
    "ze včerejška", "z předchozího dne", "z předchozí",
    "zbytek z", "zbylé", "zbylá", "zbylý",
    "předem připravené", "předem připravená", "předem připravený",
    # Slovak
    "už pripravené", "už pripravená", "už pripravený", "už uvarené",
    "už uvarená", "už uvarený", "už upečené",
    "zo včerajška", "z predchádzajúceho dňa",
    "zvyšok z", "zvyšky z",
    # Polish
    "już przygotowane", "już przygotowany", "już przygotowana",
    "już ugotowane", "już ugotowany", "już ugotowana",
    "z wczoraj", "z poprzedniego dnia", "z poprzedniego",
    "resztki z", "pozostałe z",
    # Hungarian
    "már elkészített", "már elkészült", "már megfőzött",
    "tegnapi", "tegnapról", "tegnap maradt",
    "előző napi", "előzőleg elkészített",
    "maradék",
    # Romanian
    "deja preparat", "deja preparată", "deja gătit", "deja gătită",
    "din ziua precedentă", "de ieri", "rămas de",
    # Bulgarian
    "вече приготвен", "вече приготвена", "вече приготвено", "вече сготвен",
    "от вчера", "от предишния ден", "останал от",
    # German
    "schon zubereitet", "bereits zubereitet", "schon gekocht",
    "bereits gekocht", "vorbereitet", "vom vortag", "vom vorigen tag",
    "reste vom", "übrig vom", "übrig geblieben",
)


# Compiled regex of "is/was/already" + any phrase, used so we can also
# accept light grammatical variation around the marker word.
_PRE_PREPARED_REGEX = re.compile(
    "|".join(re.escape(p) for p in _PRE_PREPARED_PHRASES),
    re.IGNORECASE | re.UNICODE,
)


# Sentence splitter that survives bullet lists, Czech punctuation, etc.
_SENTENCE_SPLIT = re.compile(r"[.!?;\n•·\-–—]+")


# A handful of generic "carrier" words we don't want to match on alone.
# E.g. if the description says "Already prepared in advance: soak the beans"
# we shouldn't latch onto "beans" just because the sentence contains the
# phrase but actually describes prep work the user is about to do. The
# tests cover the false-positive cases explicitly.
_PREP_VERB_HINTS = (
    "soak", "marinate", "marinade", "marinujte", "namáčejte", "namočte",
    "vorbereiten", "namocz", "namočiť", "macerati",
)


def _ingredient_name(ingredient: Any) -> str:
    if isinstance(ingredient, dict):
        return str(
            ingredient.get("name")
            or ingredient.get("ingredient")
            or ""
        ).strip()
    return str(ingredient or "").strip()


def _normalize(text: str) -> str:
    return (text or "").lower().strip()


def _meal_text_blob(meal: Dict[str, Any]) -> str:
    """Concatenate description + instructions into a single lowercased blob."""
    parts: List[str] = []
    description = meal.get("description")
    if description:
        parts.append(str(description))
    for step in meal.get("instructions", []) or []:
        if isinstance(step, dict):
            parts.append(str(step.get("text") or step.get("step") or ""))
        else:
            parts.append(str(step))
    return _normalize(" \n ".join(parts))


def _split_sentences(blob: str) -> List[str]:
    return [s.strip() for s in _SENTENCE_SPLIT.split(blob) if s.strip()]


def _is_explicitly_pre_prepared_flag(ingredient: Any) -> bool:
    """A first-class boolean flag from the LLM, if it cooperates."""
    if not isinstance(ingredient, dict):
        return False
    for key in ("pre_prepared", "preprepared", "from_leftovers", "is_leftover"):
        val = ingredient.get(key)
        if isinstance(val, bool) and val:
            return True
        if isinstance(val, str) and val.strip().lower() in ("true", "yes", "1"):
            return True
    return False


def detect_pre_prepared_ingredient_names(meal: Dict[str, Any]) -> Set[str]:
    """
    Return the set of ingredient names (lower-cased) that the meal's
    description or instructions describe as already-prepared / leftover.

    Algorithm: split the description+instructions blob into sentences,
    keep only sentences containing a pre-prepared marker phrase AND not
    containing a verb that suggests the user is about to do the prep
    themselves, then check which ingredient names appear inside any
    surviving sentence.
    """
    blob = _meal_text_blob(meal)
    if not blob or not _PRE_PREPARED_REGEX.search(blob):
        return set()

    sentences = _split_sentences(blob)
    matching_sentences = [
        s for s in sentences
        if _PRE_PREPARED_REGEX.search(s)
        and not any(hint in s for hint in _PREP_VERB_HINTS)
    ]
    if not matching_sentences:
        return set()

    ingredient_names = [
        _ingredient_name(ing) for ing in meal.get("ingredients", []) or []
    ]
    ingredient_names = [n for n in ingredient_names if n]

    flagged: Set[str] = set()
    for name in ingredient_names:
        needle = _normalize(name)
        if not needle or len(needle) < 2:
            continue
        for sentence in matching_sentences:
            if needle in sentence:
                flagged.add(needle)
                break
    return flagged


def filter_pre_prepared(meal: Dict[str, Any]) -> Dict[str, Any]:
    """
    Return a copy of `meal` with pre-prepared ingredients moved off the
    main `ingredients[]` list into a `pre_prepared_ingredients[]` list.

    Safe to call on a meal that has no description / instructions — in that
    case it returns the meal effectively unchanged (a shallow copy).
    """
    if not isinstance(meal, dict):
        return meal

    ingredients = list(meal.get("ingredients", []) or [])
    if not ingredients:
        result = dict(meal)
        result.setdefault("ingredients", [])
        return result

    text_flagged = detect_pre_prepared_ingredient_names(meal)

    kept: List[Any] = []
    pre_prepared: List[Any] = []
    for ing in ingredients:
        name = _normalize(_ingredient_name(ing))
        if _is_explicitly_pre_prepared_flag(ing) or (name and name in text_flagged):
            pre_prepared.append(ing)
        else:
            kept.append(ing)

    result = dict(meal)
    result["ingredients"] = kept
    if pre_prepared:
        existing = list(result.get("pre_prepared_ingredients") or [])
        result["pre_prepared_ingredients"] = existing + pre_prepared
    return result


def iter_meals(days: Iterable[Dict[str, Any]]):
    """Yield (day_number, meal_type, meal_index, meal) for every meal in a plan."""
    for day in days or []:
        if not isinstance(day, dict):
            continue
        day_number = day.get("day_number")
        for meal_type in ("breakfast", "lunch", "dinner", "small_meals", "snacks"):
            meals = day.get(meal_type)
            if meals is None:
                continue
            if isinstance(meals, dict):
                meals_list = [meals]
            elif isinstance(meals, list):
                meals_list = meals
            else:
                continue
            for idx, meal in enumerate(meals_list):
                if isinstance(meal, dict):
                    yield day_number, meal_type, idx, meal


def find_coherence_issues(
    days: Iterable[Dict[str, Any]],
    shopping_list: Optional[Iterable[Dict[str, Any]]],
) -> List[Dict[str, Any]]:
    """
    Return a list of structured coherence issues. Each issue is:

        {
          "kind": "pre_prepared_on_shopping_list",
          "day_number": int | None,
          "meal_type": str,
          "meal_index": int,
          "meal_name": str,
          "ingredient": str,
        }

    Empty list means the plan is internally consistent.
    """
    issues: List[Dict[str, Any]] = []

    shopping_names: Set[str] = set()
    for item in shopping_list or []:
        if not isinstance(item, dict):
            continue
        name = (
            item.get("ingredient")
            or item.get("name")
            or item.get("matched_product_name")
            or ""
        )
        name = _normalize(str(name))
        if name:
            shopping_names.add(name)

    if not shopping_names:
        return issues

    for day_number, meal_type, idx, meal in iter_meals(days):
        flagged_names = detect_pre_prepared_ingredient_names(meal)
        for ing in meal.get("ingredients", []) or []:
            if not _is_explicitly_pre_prepared_flag(ing):
                name_norm = _normalize(_ingredient_name(ing))
                if name_norm not in flagged_names:
                    continue
            else:
                name_norm = _normalize(_ingredient_name(ing))
            if not name_norm:
                continue
            # Match if any shopping-list name contains, or is contained by,
            # the flagged ingredient — covers "klizka" vs. "hovězí klizka".
            for shop_name in shopping_names:
                if name_norm == shop_name or name_norm in shop_name or shop_name in name_norm:
                    issues.append({
                        "kind": "pre_prepared_on_shopping_list",
                        "day_number": day_number,
                        "meal_type": meal_type,
                        "meal_index": idx,
                        "meal_name": meal.get("name", ""),
                        "ingredient": _ingredient_name(ing),
                    })
                    break

    if issues:
        logger.warning(
            "recipe_coherence: %d shopping-list / recipe conflicts detected", len(issues)
        )
    return issues
