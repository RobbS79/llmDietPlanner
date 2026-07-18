"""
Refine-chat: conversation -> (PromptFacets, next Czech follow-up question).

One combined flash call per preview turn. Same never-raise contract as
prompt_facets: any LLM/parse failure yields (empty facets, None) so the caller
degrades to an unsteered pick.
Spec: docs/superpowers/specs/2026-07-18-recipe-refine-chat-design.md.
"""
from __future__ import annotations

import json
import logging
from typing import Callable, List, Optional, Tuple

from .prompt_facets import (
    PromptFacets,
    _coerce_facets,
    _default_generate,
    _strip_code_fence,
)

logger = logging.getLogger(__name__)

MAX_USER_MESSAGES = 8
MAX_TOTAL_MESSAGES = 16
MAX_MESSAGE_CHARS = 500

_SYSTEM_PROMPT_TEMPLATE = (
    "You are helping a user pick a replacement dish for ONE meal slot in their "
    "Czech meal plan. From the conversation so far, extract CUMULATIVE facets "
    "(later user messages win on conflicts) and write ONE short follow-up "
    "question in Czech that would most narrow the choice further.\n"
    "Return ONLY a JSON object with these keys (facet arrays are short "
    "lowercase strings, [] when unsure):\n"
    '  "cuisines": choose only from this exact list: {vocab};\n'
    '  "wanted_ingredients": key ingredients the user wants;\n'
    '  "avoided_ingredients": ingredients the user wants to avoid;\n'
    '  "styles": e.g. quick, comfort, light;\n'
    '  "emphases": choose from high_protein, low_carb, low_calorie, budget;\n'
    '  "dietary": diets the user REQUIRES (e.g. says they do not eat gluten), '
    "choose from vegetarian, vegan, gluten_free, dairy_free, low_carb;\n"
    '  "question": one short question in Czech (max 15 words), or null when the '
    "conversation already gives enough signal.\n"
    "Never repeat or rephrase a question already asked in the conversation "
    "(assistant lines) — ask about a different aspect, or use null.\n"
    "The question must never mention prices, availability, or name a specific "
    "recipe. No prose, JSON only."
)


def clamp_messages(messages) -> List[dict]:
    """Validate + cap raw request messages: well-formed entries only, each text
    trimmed to MAX_MESSAGE_CHARS, newest MAX_TOTAL_MESSAGES kept, and oldest
    entries dropped until at most MAX_USER_MESSAGES user messages remain."""
    if not isinstance(messages, list):
        return []
    clean: List[dict] = []
    for m in messages:
        if not isinstance(m, dict):
            continue
        role = m.get('role')
        text = str(m.get('text') or '').strip()
        if role not in ('user', 'assistant') or not text:
            continue
        clean.append({'role': role, 'text': text[:MAX_MESSAGE_CHARS]})
    clean = clean[-MAX_TOTAL_MESSAGES:]
    while sum(1 for m in clean if m['role'] == 'user') > MAX_USER_MESSAGES:
        clean.pop(0)
    return clean


def _question_already_asked(question: str, convo: List[dict]) -> bool:
    """True when an assistant transcript line already contains this question
    (case-folded, whitespace-normalized substring match)."""
    norm = ' '.join(question.casefold().split())
    for m in convo:
        if m['role'] != 'assistant':
            continue
        if norm in ' '.join(m['text'].casefold().split()):
            return True
    return False


def refine_conversation(
    messages: List[dict],
    *,
    language: str,
    cuisine_vocab: List[str],
    generate: Optional[Callable[[str, str], str]] = None,
) -> Tuple[PromptFacets, Optional[str]]:
    """Extract cumulative facets + the next Czech question from a chat. Never
    raises; a conversation with no user message makes no LLM call at all."""
    convo = clamp_messages(messages)
    if not any(m['role'] == 'user' for m in convo):
        return PromptFacets(), None
    gen = generate or _default_generate
    system_prompt = _SYSTEM_PROMPT_TEMPLATE.format(vocab=', '.join(cuisine_vocab) or '(none)')
    transcript = '\n'.join(f"{m['role']}: {m['text']}" for m in convo)
    try:
        raw = gen(system_prompt, f"Language: {language}\nConversation:\n{transcript}")
        data = json.loads(_strip_code_fence(raw))
        facets = _coerce_facets(data, cuisine_vocab=cuisine_vocab)
        q = data.get('question') if isinstance(data, dict) else None
        question = str(q).strip() if isinstance(q, str) and str(q).strip() else None
        if question and _question_already_asked(question, convo):
            # Belt to the prompt's no-repeat instruction: the model re-asking
            # a transcript question is dropped rather than shown twice.
            question = None
        return facets, question
    except Exception as exc:  # noqa: BLE001 - defensive by design
        logger.warning("Refine-chat extraction failed, using empty facets: %s", exc)
        return PromptFacets(), None
