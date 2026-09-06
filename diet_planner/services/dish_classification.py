"""
Classify a curated recipe by what it can CARRY in a Czech day, when it may
appear, what it is eaten with, and which dish family it belongs to.

One Gemini call per batch answers four fields per slug; a deterministic
validator drops anything outside the vocabularies; then
data/dish_role_overrides.yaml pins whatever the owner has decided. Used at
curation intake (every new recipe) and by `manage.py retag_dish_roles`
(backfill + review report). Spec: docs/superpowers/specs/2026-09-06-dish-roles-priloha-design.md.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional

import yaml
from django.utils.text import slugify

from diet_planner.models import CuratedRecipe
from diet_planner.services.canonical_lookup import fold_diacritics
from diet_planner.services.priloha import SIDE_KEYS

logger = logging.getLogger(__name__)

OVERRIDES_PATH = Path(__file__).resolve().parents[1] / 'data' / 'dish_role_overrides.yaml'

# 'light' is legacy: the LLM must choose breakfast or supper instead.
VALID_ROLES = {c.value for c in CuratedRecipe.DishRole} - {CuratedRecipe.DishRole.LIGHT.value}
VALID_MEAL_TYPES = {'breakfast', 'lunch', 'dinner', 'snack', 'small_meal'}
VALID_SIDES = set(SIDE_KEYS)
_FAMILY_RE = re.compile(r'^[a-z0-9-]{1,60}$')

SYSTEM_PROMPT = (
    "You classify recipes for a CZECH meal planner. For each recipe return four fields.\n"
    "\n"
    "dish_role — what the dish can CARRY:\n"
    "  main — a warm, substantial dish that carries a Czech oběd (and may carry večeře): "
    "svíčková, guláš, řízek, pečené kuře, rizoto, plněné papriky, omáčky s masem, "
    "hearty one-pot dishes like segedínský guláš, composed salads with a full protein portion.\n"
    "  supper — a quick dish Czechs eat as VEČEŘE, never as oběd: lečo, topinky, bramboráky, "
    "smažený sýr bez přílohy, chlebíčky, míchaná vejce k večeři, menemen/shakshuka, quesadilla.\n"
    "  breakfast — a SNÍDANĚ dish: kaše, ovesná kaše, vejce na snídani, toasty, palačinky, lívance, "
    "jogurt s granolou, smoothie bowl.\n"
    "  soup — a brothy or starter soup that accompanies a meal rather than carrying it: "
    "česnečka, kulajda, čočková polévka, hrachová polévka, vývar.\n"
    "  side — accompaniments and components: basic salads, dips, spreads, sauces, breads, plain "
    "grains or vegetables, AND preserving bases / batch components (e.g. a 'lečo' that is only "
    "peppers, onion, tomato and lard in 18 servings for jars).\n"
    "  dessert — sweet dishes and baked desserts.\n"
    "\n"
    "meal_types — WHEN the dish may appear, any of: breakfast, lunch, dinner, snack, small_meal. "
    "A supper dish lists dinner only. A main lists lunch and dinner. A breakfast dish lists breakfast "
    "(and small_meal if it also works as a light bite).\n"
    "\n"
    "side_options — for main and supper ONLY: the příloha a Czech household eats it with, as an "
    "ordered list from: chleb (bread), brambory (boiled potatoes), ryze (rice), knedlik (houskový "
    "knedlík), testoviny (pasta). Order by what is most usual for that dish. Empty list when the "
    "dish is complete on its own (rizoto, plněné papriky, pasta dishes, bowls, composed salads) or "
    "when the recipe already contains its starch. Examples: lečo → [chleb]; guláš → [knedlik, chleb]; "
    "svíčková → [knedlik]; řízek → [brambory]; kuře na paprice → [knedlik, testoviny]; "
    "rajská omáčka → [knedlik, testoviny]; pečené kuře → [brambory, ryze]. Other roles: [].\n"
    "\n"
    "dish_family — a short lowercase ASCII key naming the dish type so the planner never serves two "
    "of a family in one day: leco, gulas, svickova, rizek, rizoto, omacka-rajska, omacka-koprova, "
    "polevka-cockova, kure-pecene, kase-ovesna, palacinky. Variants share a key (Lečo, Lečo s klobásou, "
    "Domácí lečo → leco).\n"
    "\n"
    "Input is a JSON array of recipes. Answer ONLY with a JSON array of objects "
    '{"slug", "dish_role", "meal_types", "side_options", "dish_family"} covering every input slug. No prose.'
)


@dataclass
class Classification:
    dish_role: str = ''
    meal_types: List[str] = field(default_factory=list)
    side_options: List[str] = field(default_factory=list)
    dish_family: str = ''
    problems: List[str] = field(default_factory=list)


def _default_generate(system_prompt: str, user_text: str) -> str:
    from diet_planner.llm_service import GeminiService
    return GeminiService().classify_dishes(system_prompt, user_text)


# Patched in tests; the management command and curation may inject their own.
_generate: Callable[[str, str], str] = _default_generate


def _key(recipe: Any) -> str:
    return getattr(recipe, 'slug', None) or slugify(recipe.name_cs)


def describe(recipe: Any) -> Dict[str, Any]:
    return {
        'slug': _key(recipe),
        'name': recipe.name_cs,
        'description': recipe.description or '',
        'cuisine': getattr(recipe, 'cuisine', '') or '',
        'meal_types': recipe.meal_types or [],
        'ingredients': [i.get('name') for i in (recipe.ingredients or []) if i.get('name')],
        'base_servings': recipe.base_servings,
        'calories_total': (recipe.base_nutrition or {}).get('calories'),
    }


def normalize_family(raw: Any) -> str:
    text = fold_diacritics(str(raw or '')).strip().lower()
    text = re.sub(r'[^a-z0-9]+', '-', text).strip('-')[:60]
    return text if _FAMILY_RE.match(text or '') else ''


def _clean_list(values: Any, allowed: set, problems: List[str], label: str) -> List[str]:
    out: List[str] = []
    for v in (values if isinstance(values, list) else []):
        key = str(v).strip().lower()
        if key in allowed:
            if key not in out:
                out.append(key)
        else:
            problems.append(f'{label} {key!r} dropped')
    return out


def parse_answer(raw: str) -> Dict[str, Classification]:
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    if not isinstance(data, list):
        return {}
    out: Dict[str, Classification] = {}
    for item in data:
        if not isinstance(item, dict) or not item.get('slug'):
            continue
        c = Classification()
        role = str(item.get('dish_role', '')).strip().lower()
        if role in VALID_ROLES:
            c.dish_role = role
        elif role:
            c.problems.append(f'dish_role {role!r} dropped')
        c.meal_types = _clean_list(item.get('meal_types'), VALID_MEAL_TYPES, c.problems, 'meal_type')
        c.side_options = _clean_list(item.get('side_options'), VALID_SIDES, c.problems, 'side')
        c.dish_family = normalize_family(item.get('dish_family'))
        out[str(item['slug'])] = c
    return out


def classify_recipes(
    recipes: Iterable[Any],
    *,
    generate: Optional[Callable[[str, str], str]] = None,
    batch_size: int = 25,
) -> Dict[str, Classification]:
    """LLM pass over `recipes`, keyed by slug (or slugified name for unsaved
    rows). A failed batch is logged and skipped — never raises."""
    gen = generate or _generate
    recipes = list(recipes)
    out: Dict[str, Classification] = {}
    for start in range(0, len(recipes), batch_size):
        batch = recipes[start:start + batch_size]
        payload = json.dumps([describe(r) for r in batch], ensure_ascii=False)
        try:
            out.update(parse_answer(gen(SYSTEM_PROMPT, payload)))
        except Exception as exc:  # noqa: BLE001
            logger.warning('dish_classification: batch at #%d failed: %r', start, exc)
    return out


def load_overrides(path: Path = OVERRIDES_PATH) -> Dict[str, Dict[str, Dict[str, Any]]]:
    with open(path, encoding='utf-8') as fh:
        data = yaml.safe_load(fh) or {}
    return {'by_slug': data.get('by_slug') or {}, 'by_family': data.get('by_family') or {}}


_FIELDS = ('dish_role', 'meal_types', 'side_options', 'dish_family')


def _merge(c: Classification, entry: Dict[str, Any]) -> None:
    for key in _FIELDS:
        if key in entry:
            setattr(c, key, entry[key] if key != 'dish_family' else normalize_family(entry[key]))


def apply_overrides(
    slug: str, classification: Classification, *, overrides: Optional[Dict] = None,
) -> Classification:
    """by_slug beats by_family beats the LLM. The family used for the by_family
    lookup is the slug override's, if it sets one, else the LLM's."""
    ovr = overrides if overrides is not None else load_overrides()
    c = Classification(
        **{k: getattr(classification, k) for k in _FIELDS},
        problems=list(classification.problems),
    )
    slug_entry = ovr['by_slug'].get(slug) or {}
    family = normalize_family(slug_entry.get('dish_family', c.dish_family))
    family_entry = ovr['by_family'].get(family) or {}
    _merge(c, family_entry)
    _merge(c, slug_entry)
    return c


def classify_and_override(
    recipes: Iterable[Any], *, generate: Optional[Callable[[str, str], str]] = None,
) -> Dict[str, Classification]:
    recipes = list(recipes)
    ovr = load_overrides()
    raw = classify_recipes(recipes, generate=generate)
    return {
        _key(r): apply_overrides(_key(r), raw[_key(r)], overrides=ovr)
        for r in recipes if _key(r) in raw
    }
