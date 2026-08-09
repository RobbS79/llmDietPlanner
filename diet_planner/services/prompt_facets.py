"""
Free-text prompt -> structured PromptFacets, used to make recipe grounding
prompt-aware (see docs/superpowers/specs/2026-06-17-prompt-aware-recipe-grounding-design.md).

This module is intentionally dependency-free w.r.t. recipe_retrieval: it takes
`cuisine_vocab` as an argument so the caller (recipe_retrieval.overlay) owns the
corpus lookup and no import cycle is created.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Set

logger = logging.getLogger(__name__)


# Dietary requirements the corpus can actually enforce (dietary_tags vocab).
ENFORCEABLE_DIETARY_TAGS = {'vegetarian', 'vegan', 'gluten_free', 'dairy_free', 'low_carb'}

# Keys of the extraction contract — used to pick the right JSON object out of a
# response that also contains prose or examples.
_FACET_KEYS = {
    'cuisines', 'wanted_ingredients', 'avoided_ingredients', 'styles',
    'emphases', 'dietary', 'max_time_minutes',
}


@dataclass
class PromptFacets:
    cuisines: Set[str] = field(default_factory=set)
    wanted_ingredients: Set[str] = field(default_factory=set)
    avoided_ingredients: Set[str] = field(default_factory=set)
    styles: Set[str] = field(default_factory=set)
    emphases: Set[str] = field(default_factory=set)
    # Restrictions stated in the text itself ("nejím lepek"); unlike the soft
    # facets above these are enforced as a HARD gate and never relaxed.
    dietary: Set[str] = field(default_factory=set)
    # Stated total-time budget ("max 30 minut"), enforced as a HARD gate on
    # recipe total_time; recipes with unknown time are let through.
    max_time_minutes: Optional[int] = None
    # Extraction anomaly: the prompt was substantive but extraction (after a
    # retry) produced nothing. The overlay must then treat the generated plan
    # as the only prompt-aware artifact and stop overriding generated meals.
    # Not part of is_empty(): it describes extraction, not the user.
    suspect: bool = False

    def is_empty(self) -> bool:
        return not (
            self.cuisines or self.wanted_ingredients or self.avoided_ingredients
            or self.styles or self.emphases or self.dietary
            or self.max_time_minutes
        )

    def to_debug(self) -> dict:
        return {
            'cuisines': sorted(self.cuisines),
            'wanted_ingredients': sorted(self.wanted_ingredients),
            'avoided_ingredients': sorted(self.avoided_ingredients),
            'styles': sorted(self.styles),
            'emphases': sorted(self.emphases),
            'dietary': sorted(self.dietary),
            'max_time_minutes': self.max_time_minutes,
        }


def _clean_list(value) -> Set[str]:
    """Lowercase + strip a list of strings; non-lists become empty."""
    if not isinstance(value, list):
        return set()
    return {str(v).strip().lower() for v in value if str(v).strip()}


def _coerce_time_minutes(value) -> Optional[int]:
    """Positive int minutes, else None (bools excluded: True is not a time)."""
    if isinstance(value, bool):
        return None
    try:
        minutes = int(value)
    except (TypeError, ValueError):
        return None
    return minutes if minutes > 0 else None


def _coerce_facets(data: dict, *, cuisine_vocab: List[str]) -> PromptFacets:
    """Pure: turn a raw dict into PromptFacets, filtering cuisines to vocab."""
    vocab = {c.strip().lower() for c in (cuisine_vocab or [])}
    if not isinstance(data, dict):
        return PromptFacets()
    return PromptFacets(
        cuisines=_clean_list(data.get('cuisines')) & vocab,
        wanted_ingredients=_clean_list(data.get('wanted_ingredients')),
        avoided_ingredients=_clean_list(data.get('avoided_ingredients')),
        styles=_clean_list(data.get('styles')),
        emphases=_clean_list(data.get('emphases')),
        dietary=_clean_list(data.get('dietary')) & ENFORCEABLE_DIETARY_TAGS,
        max_time_minutes=_coerce_time_minutes(data.get('max_time_minutes')),
    )


_SYSTEM_PROMPT_TEMPLATE = (
    "You extract structured facets from a user's free-text meal-plan request. "
    "Return ONLY a JSON object with these keys (arrays of short lowercase "
    "strings unless stated otherwise, omit or use [] when unsure):\n"
    '  "cuisines": ONLY if the user explicitly asks for a cuisine, choose from '
    "this exact list: {vocab}; never infer a cuisine from dish or ingredient names;\n"
    '  "wanted_ingredients": key ingredients or food groups the user explicitly '
    "wants OR lists as available to cook from — inventory phrasing counts "
    '("mám doma vejce", "v lednici mám", "zbylo mi", "koupil jsem") — as '
    "simple singular nouns in the language of the request "
    '(e.g. "maso", "ryba", "rýže", "zelenina" — not sentences);\n'
    '  "avoided_ingredients": ingredients the user wants to avoid (beyond '
    "allergies), same form as wanted_ingredients;\n"
    '  "styles": e.g. quick, comfort, light;\n'
    '  "emphases": choose from high_protein, low_carb, low_calorie, budget;\n'
    '  "max_time_minutes": integer — ONLY if the user states an explicit cooking '
    'time limit (e.g. "max 30 minut" -> 30), else null.\n'
    "Do not invent cuisines outside the provided list. No prose, JSON only."
)


def _extract_json_object(text: str) -> Optional[dict]:
    """First parseable JSON object anywhere in the response.

    `json.loads` is strict, and Gemini routinely appends prose (or a second
    object) after the contract — which raises "Extra data" and threw the WHOLE
    extraction away. Observed on prod 2026-08-09 after the gemini-3.5-flash
    bump: every facet call failed, so cuisines, wanted ingredients, time limits
    AND dietary restrictions were silently empty product-wide. Same fix the
    refine agent already carries (`refine_agent._extract_contract`).
    """
    decoder = json.JSONDecoder()
    fallback = None
    idx = text.find('{')
    while idx != -1:
        try:
            data, _ = decoder.raw_decode(text, idx)
        except ValueError:
            data = None
        if isinstance(data, dict):
            # Prefer an object that actually looks like the contract; a stray
            # `{}` or an example dict in the prose must not win.
            if data.keys() & _FACET_KEYS:
                return data
            if fallback is None:
                fallback = data
        idx = text.find('{', idx + 1)
    return fallback


def _strip_code_fence(text: str) -> str:
    t = text.strip()
    if t.startswith('```'):
        t = t.split('\n', 1)[-1] if '\n' in t else t
        if t.endswith('```'):
            t = t[: -3]
        if t.lstrip().startswith('json'):
            t = t.lstrip()[4:]
    return t.strip()


def _default_generate(system_prompt: str, user_text: str) -> str:
    import google.generativeai as genai
    from django.conf import settings

    genai.configure(api_key=getattr(settings, 'GEMINI_API_KEY', None))
    model = genai.GenerativeModel(
        model_name=getattr(settings, 'GEMINI_MODEL', 'gemini-2.5-flash'),
        system_instruction=system_prompt,
    )
    # Deterministic + native JSON: facet extraction was a coin flip at default
    # temperature (goal 133 — same prompt, empty on ~half of samples).
    resp = model.generate_content(
        user_text,
        generation_config=genai.types.GenerationConfig(
            temperature=0.0,
            response_mime_type='application/json',
        ),
    )
    return getattr(resp, 'text', '') or ''


# A prompt at least this long is treated as substantive: the user said
# something concrete, so an empty extraction is an anomaly, not an answer.
_NONTRIVIAL_PROMPT_LEN = 15


def extract_prompt_facets(
    prompt: Optional[str],
    *,
    language: str,
    cuisine_vocab: List[str],
    generate: Optional[Callable[[str, str], str]] = None,
) -> PromptFacets:
    """Extract PromptFacets from free text. Never raises.

    A substantive prompt that extracts to nothing is retried once; if it stays
    empty (or the LLM call fails), the returned facets carry `suspect=True` so
    the overlay degrades to rescue-only instead of silently discarding the
    user's words (goal 133)."""
    if not prompt or not prompt.strip():
        return PromptFacets()
    gen = generate or _default_generate
    system_prompt = _SYSTEM_PROMPT_TEMPLATE.format(vocab=', '.join(cuisine_vocab) or '(none)')
    substantive = len(prompt.strip()) >= _NONTRIVIAL_PROMPT_LEN
    attempts = 2 if substantive else 1
    for _ in range(attempts):
        try:
            raw = gen(system_prompt, f"Language: {language}\nRequest: {prompt.strip()}")
            data = _extract_json_object(_strip_code_fence(raw))
            if data is None:
                raise ValueError('no JSON object in facet response')
            facets = _coerce_facets(data, cuisine_vocab=cuisine_vocab)
        except Exception as exc:  # noqa: BLE001 - defensive by design
            logger.warning("Prompt facet extraction failed: %s", exc)
            continue
        if not facets.is_empty():
            return facets
    facets = PromptFacets()
    if substantive:
        facets.suspect = True
        logger.warning(
            "Prompt facets empty for substantive prompt (len=%d) after retry — "
            "overlay will keep generated meals (rescue-only)", len(prompt.strip()))
    return facets
