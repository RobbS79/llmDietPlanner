"""Anonymous first-visit search over the published collection (spec 2026-11-03).

One LLM read of the request (prompt_facets, up to two calls, each against
the daily budget); selection reuses the plan
pipeline's hard gate and ranking, with no gap filling: what the collection
cannot answer is reported as exact=False, never written by Gemini here.
"""
import concurrent.futures
import dataclasses
import unicodedata
from typing import Any, Callable, Dict, List, Optional

from django.conf import settings

from diet_planner.models import CuratedRecipe
from diet_planner.models.catalog import Availability
from diet_planner.services import prompt_facets
from diet_planner.services.discover_guard import take_llm_slot
from diet_planner.services.prompt_facets import PromptFacets, extract_prompt_facets
from diet_planner.services.recipe_retrieval import (
    _avoided_matcher, _role_allowed, published_cuisine_vocab, published_pool, recipe_matches_facets,
    score_recipe, wanted_matcher,
)

_LABELS_DIETARY = {'vegetarian': 'bez masa', 'vegan': 'veganské', 'gluten_free': 'bez lepku',
                   'dairy_free': 'bez mléka', 'low_carb': 'méně sacharidů'}
_LABELS_EMPHASES = {'high_protein': 'hodně bílkovin', 'low_carb': 'méně sacharidů',
                    'low_calorie': 'lehčí jídla', 'budget': 'levnější suroviny'}
_LABELS_STYLES = {'quick': 'rychlé', 'light': 'lehčí jídla', 'comfort': 'poctivé jídlo',
                  'meal_prep': 'do krabiček'}

# Accent-folded filler words that carry no dish or ingredient meaning.
_TEXT_STOPWORDS = {'uvarit', 'chci', 'neco', 'doma', 'mam'}

# Accent-folded stems that make a query medical: the UI then says it is not
# medical advice (spec 2026-11-03).
_MEDICAL_STEMS = ('cukrovk', 'cukrovc', 'diabet', 'inzulin')  # cukrovc: "při cukrovce"


class LLMBudgetSpent(Exception):
    """Today's discover LLM budget is used up: read the request as text."""


def _budgeted(generate: Callable[[str, str], str]) -> Callable[[str, str], str]:
    """Each REAL LLM call takes one budget slot first (extract_prompt_facets
    retries once, so one request may cost two). No slot: raise, and the
    extraction failure falls back to text search."""
    def call(system_prompt: str, user_text: str) -> str:
        if not take_llm_slot():
            raise LLMBudgetSpent()
        return generate(system_prompt, user_text)
    return call


def _fold(text: str) -> str:
    return ''.join(c for c in unicodedata.normalize('NFD', (text or '').lower())
                   if not unicodedata.combining(c))


def understood_labels(facets: Optional[PromptFacets]) -> List[str]:
    if facets is None:
        return []
    labels: List[str] = []

    def add(label):
        if label and label not in labels:
            labels.append(label)

    for w in sorted(facets.wanted_ingredients):
        add(w)
    for a in sorted(facets.avoided_ingredients):
        add(f'bez: {a}')
    for d in sorted(facets.dietary):
        add(_LABELS_DIETARY.get(d, d))
    if facets.max_time_minutes:
        add(f'do {facets.max_time_minutes} minut')
    for e in sorted(facets.emphases):
        add(_LABELS_EMPHASES.get(e))
    for s in sorted(facets.styles):
        add(_LABELS_STYLES.get(s))
    for c in sorted(facets.cuisines):
        add(c)
    return labels


def _mains(pool: List[CuratedRecipe]) -> List[CuratedRecipe]:
    out = []
    for r in pool:
        if not {'lunch', 'dinner'} & set(r.meal_types or []):
            continue
        if not _role_allowed('dinner', r.dish_role or ''):
            continue
        if not r.is_catalog_mapped() or r.shopping_difficulty == Availability.SPECIALTY:
            continue
        out.append(r)
    return out


def _read_request(q: str, pool, generate) -> Optional[PromptFacets]:
    """Facets, or None when the LLM failed, timed out or found nothing usable."""
    timeout = getattr(settings, 'DISCOVER_LLM_TIMEOUT_SECONDS', 5)
    vocab = published_cuisine_vocab(pool=pool)
    # Looked up at call time so tests can patch prompt_facets._default_generate.
    kwargs = {'language': 'cs', 'cuisine_vocab': vocab,
              'generate': _budgeted(generate or prompt_facets._default_generate)}
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    try:
        facets = executor.submit(extract_prompt_facets, q, **kwargs).result(timeout=timeout)
    except Exception:  # noqa: BLE001 - timeout or LLM error: text fallback
        return None
    finally:
        executor.shutdown(wait=False, cancel_futures=True)
    if facets.suspect or facets.is_empty():
        return None
    return facets


def _rank(candidates, facets) -> List[CuratedRecipe]:
    scored = [(score_recipe(r, used_recipe_ids=set(), used_cuisines=[], facets=facets), -r.id, r)
              for r in candidates]
    scored.sort(key=lambda t: (t[0], t[1]), reverse=True)
    return [r for _, _, r in scored]


def _text_match(q: str, mains: List[CuratedRecipe]) -> List[CuratedRecipe]:
    tokens = [t for t in _fold(q).replace(',', ' ').split()
              if len(t) >= 3 and t not in _TEXT_STOPWORDS]
    if not tokens:  # filler only ("chci něco uvařit"): nothing to match on
        return []
    out = []
    for r in mains:
        hay = _fold(r.name_cs + ' ' + ' '.join(str(i.get('name', '')) for i in r.ingredients or []))
        if all(t[:5] in hay for t in tokens):
            out.append(r)
    return out


def _restrictions_only(facets: PromptFacets) -> PromptFacets:
    """The gates the nearest list may never relax: dietary rules and avoided
    ingredients. Cuisine and time limit are preferences it may drop.

    Built ONCE per discover() call: recipe_matches_facets caches the avoided
    matcher on the facets instance, and a fresh copy per recipe would rebuild
    it (a few queries each). The original's matcher is shared too."""
    relaxed = dataclasses.replace(facets, cuisines=set(), max_time_minutes=None)
    if facets.avoided_ingredients:
        facets.__dict__['_avoided_matcher'] = _avoided_matcher(relaxed)
    return relaxed


def _passes_restrictions(r: CuratedRecipe, facets: PromptFacets, relaxed: PromptFacets) -> bool:
    return (set(facets.dietary) <= set(r.dietary_tags or [])
            and recipe_matches_facets(r, relaxed))


def _is_medical(q: str) -> bool:
    folded = _fold(q)
    return any(stem in folded for stem in _MEDICAL_STEMS)


def discover(q: str, page: int, *, llm_allowed: bool,
             generate: Optional[Callable[[str, str], str]] = None,
             page_size: int = 4) -> Dict[str, Any]:
    q = (q or '').strip()[:300]
    pool = published_pool()
    mains = _mains(pool)
    facets = _read_request(q, pool, generate) if (q and llm_allowed) else None
    fallback = bool(q) and facets is None

    if facets is not None:
        relaxed = _restrictions_only(facets)
        allowed = [r for r in mains if _passes_restrictions(r, facets, relaxed)]
        gated = [r for r in allowed if recipe_matches_facets(r, facets)]
        if facets.wanted_ingredients:
            matcher = wanted_matcher(facets)
            exact_list = [r for r in gated if matcher.hits(r) > 0]
        else:
            exact_list = gated
        ranked = _rank(exact_list, facets)
        exact = bool(ranked)
        if not ranked:
            ranked = _rank(gated or allowed, None)
    else:
        matched = _text_match(q, mains) if q else []
        exact = bool(matched) or not q
        ranked = _rank(matched or mains, None)

    start = max(page, 0) * page_size
    return {
        'understood': understood_labels(facets),
        'exact': exact,
        'fallback': fallback,
        'medical_note': _is_medical(q),
        # The whole ranking, for callers that cache it and slice pages
        # themselves (the discover view).
        'ranked_ids': [r.id for r in ranked],
        'recipes': ranked[start:start + page_size],
        'has_more': len(ranked) > start + page_size,
    }
