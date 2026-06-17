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


@dataclass
class PromptFacets:
    cuisines: Set[str] = field(default_factory=set)
    wanted_ingredients: Set[str] = field(default_factory=set)
    avoided_ingredients: Set[str] = field(default_factory=set)
    styles: Set[str] = field(default_factory=set)
    emphases: Set[str] = field(default_factory=set)

    def is_empty(self) -> bool:
        return not (
            self.cuisines or self.wanted_ingredients or self.avoided_ingredients
            or self.styles or self.emphases
        )

    def to_debug(self) -> dict:
        return {
            'cuisines': sorted(self.cuisines),
            'wanted_ingredients': sorted(self.wanted_ingredients),
            'avoided_ingredients': sorted(self.avoided_ingredients),
            'styles': sorted(self.styles),
            'emphases': sorted(self.emphases),
        }


def _clean_list(value) -> Set[str]:
    """Lowercase + strip a list of strings; non-lists become empty."""
    if not isinstance(value, list):
        return set()
    return {str(v).strip().lower() for v in value if str(v).strip()}


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
    )


_SYSTEM_PROMPT_TEMPLATE = (
    "You extract structured facets from a user's free-text meal-plan request. "
    "Return ONLY a JSON object with these keys (all arrays of short lowercase "
    "strings, omit or use [] when unsure):\n"
    '  "cuisines": choose only from this exact list: {vocab};\n'
    '  "wanted_ingredients": key ingredients the user explicitly wants;\n'
    '  "avoided_ingredients": ingredients the user wants to avoid (beyond allergies);\n'
    '  "styles": e.g. quick, comfort, light;\n'
    '  "emphases": choose from high_protein, low_carb, low_calorie, budget.\n'
    "Do not invent cuisines outside the provided list. No prose, JSON only."
)


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
    resp = model.generate_content(user_text)
    return getattr(resp, 'text', '') or ''


def extract_prompt_facets(
    prompt: Optional[str],
    *,
    language: str,
    cuisine_vocab: List[str],
    generate: Optional[Callable[[str, str], str]] = None,
) -> PromptFacets:
    """Extract PromptFacets from free text. Never raises: any failure -> empty."""
    if not prompt or not prompt.strip():
        return PromptFacets()
    gen = generate or _default_generate
    system_prompt = _SYSTEM_PROMPT_TEMPLATE.format(vocab=', '.join(cuisine_vocab) or '(none)')
    try:
        raw = gen(system_prompt, f"Language: {language}\nRequest: {prompt.strip()}")
        data = json.loads(_strip_code_fence(raw))
        return _coerce_facets(data, cuisine_vocab=cuisine_vocab)
    except Exception as exc:  # noqa: BLE001 - defensive by design
        logger.warning("Prompt facet extraction failed, using empty facets: %s", exc)
        return PromptFacets()
