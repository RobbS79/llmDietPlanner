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
