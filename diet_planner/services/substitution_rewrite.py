"""Rewriting the instruction steps that name a substituted ingredient.

Deliberately narrow. We are editing someone else's credited recipe, so the
LLM sees only the steps that mention the swapped ingredient, and must return
exactly that many steps back. Anything else raises and the caller discards the
whole rewrite — a half-adapted recipe is worse than an unshoppable one.
"""
from __future__ import annotations

import json
import logging
from typing import Callable, List, Optional

from django.conf import settings

from diet_planner.services.ingredient_substitution import (
    IngredientChange, SubstitutionPlan,
)

logger = logging.getLogger(__name__)


#: What this run has spent. Module-level because the cost is a property of
#: the run, not of any one recipe, and the command reports it once at the end.
#: `unmetered_calls` exists so an unknown cost can never read as a zero cost.
_USAGE = {'calls': 0, 'unmetered_calls': 0, 'prompt_tokens': 0,
          'output_tokens': 0, 'total_tokens': 0}


def reset_usage() -> None:
    """Zero the counters. Call once at the start of a run."""
    for key in _USAGE:
        _USAGE[key] = 0


def usage_snapshot() -> dict:
    return dict(_USAGE)


def record_usage(resp) -> None:
    """Accumulate one response's token usage.

    A response without usage_metadata is counted as unmetered rather than as
    free: the tokens were spent either way, and a silent zero would understate
    the bill.
    """
    meta = getattr(resp, 'usage_metadata', None)
    if meta is None:
        _USAGE['unmetered_calls'] += 1
        return
    _USAGE['prompt_tokens'] += int(getattr(meta, 'prompt_token_count', 0) or 0)
    _USAGE['output_tokens'] += int(getattr(meta, 'candidates_token_count', 0) or 0)
    _USAGE['total_tokens'] += int(getattr(meta, 'total_token_count', 0) or 0)


class RewriteError(Exception):
    """The rewrite could not be trusted; caller must discard it."""


_PROMPT = (
    'Toto jsou kroky českého receptu, ve kterých se mění jedna surovina.\n'
    'Záměny:\n{swaps}\n\n'
    'Přepiš KAŽDÝ krok tak, aby používal novou surovinu. Zachovej styl, tón '
    'i pořadí. Neměň nic jiného — žádné nové kroky, žádné rady navíc. Pokud '
    'záměna vyžaduje jinou přípravu (např. mletí ovesných vloček místo ovesné '
    'mouky), doplň to stručně do téhož kroku.\n\n'
    'Kroky ({count}):\n{steps}\n\n'
    'Vrať POUZE JSON: {{"steps": [{{"text": "..."}}, ...]}} — přesně {count} '
    'kroků ve stejném pořadí.'
)


def _default_generate(prompt: str) -> str:
    import google.generativeai as genai

    genai.configure(api_key=getattr(settings, 'GEMINI_API_KEY', None))
    model = genai.GenerativeModel(getattr(settings, 'GEMINI_MODEL', 'gemini-2.5-flash'))
    resp = model.generate_content(prompt)
    record_usage(resp)
    return getattr(resp, 'text', '') or ''


def _step_text(step) -> str:
    if isinstance(step, dict):
        return step.get('text') or ''
    return str(step or '')


def _stems(name: str) -> List[str]:
    """Czech is inflected, so compare stems rather than exact forms
    ('vanilkový extrakt' appears as 'vanilkového extraktu')."""
    return [w[:-2] if len(w) > 5 else w for w in name.lower().split() if w]


def _mentions(text: str, name: str) -> bool:
    """Loose: ANY stem hits. Decides which steps go to the LLM, where
    over-including a step costs tokens and nothing else."""
    haystack = text.lower()
    return any(stem in haystack for stem in _stems(name))


def _names(text: str, name: str) -> bool:
    """Strict: EVERY stem hits. The fail-closed guard needs this, because the
    loose form is actively wrong there: 'vanilkové aroma' and 'vanilkový
    extrakt' share the 'vanilko' stem, so ANY-matching reported the new name as
    present in a step that still said 'vanilkový extrakt' and the guard never
    fired. Requiring every stem also separates swaps that keep the head noun
    ('avokádový olej' -> 'řepkový olej')."""
    haystack = text.lower()
    stems = _stems(name)
    return bool(stems) and all(stem in haystack for stem in stems)


def _removed_stems(change: IngredientChange) -> List[str]:
    """The stems a swap actually takes away: in the old name, gone from the new.

    'vanilkový extrakt' -> 'vanilkové aroma' removes only 'extra'. The vanilla
    survives, so 'Vanilkový koláč' is still a true title and must not be sent
    for regeneration.

    Stems under three characters are dropped: 'pico de gallo' -> 'salsa'
    removes the word 'de', which is a substring of half the Czech language
    ('dezert', 'deset'), and matching on it would send unrelated titles to the
    model. Nothing is lost — such a word never identifies the ingredient on
    its own, and the words that do ('pico', 'gallo') still match.
    """
    kept = set(_stems(change.new_name))
    return [stem for stem in _stems(change.old_name)
            if stem not in kept and len(stem) >= 3]


def _drops(text: str, change: IngredientChange) -> bool:
    """Whether `text` still leans on something the swap removed.

    ANY removed stem, not all of them: 'Javorové banánové muffiny' never says
    'sirup', but the maple is gone and the title is now false. Neither existing
    matcher fits here — the loose one fires on the surviving word, the strict
    one misses the half-named phrase.
    """
    haystack = text.lower()
    return any(stem in haystack for stem in _removed_stems(change))


def rewrite_instructions(
    instructions, plan: SubstitutionPlan,
    *, generate: Optional[Callable[[str], str]] = None,
) -> List[dict]:
    """Instruction list with swapped ingredients renamed in the affected steps.

    Raises RewriteError if the model returns the wrong shape, errors, or leaves
    an old ingredient name in place.
    """
    from diet_planner.services.prompt_facets import _strip_code_fence

    steps = list(instructions or [])
    if not plan.changes:
        return steps

    affected = [
        i for i, step in enumerate(steps)
        if any(_mentions(_step_text(step), c.old_name) for c in plan.changes)
    ]
    if not affected:
        # The swap never surfaces in the prose — ingredient rewrite is enough.
        return steps

    swaps = '\n'.join(f'- {c.old_name} → {c.new_name}' for c in plan.changes)
    numbered = '\n'.join(f'{n + 1}. {_step_text(steps[i])}' for n, i in enumerate(affected))
    prompt = _PROMPT.format(swaps=swaps, count=len(affected), steps=numbered)

    gen = generate or _default_generate
    # Counted before the call, not after: a rewrite that fails or gets
    # discarded still burned the tokens.
    _USAGE['calls'] += 1
    try:
        raw = gen(prompt)
        data = json.loads(_strip_code_fence(raw))
        new_steps = data['steps']
    except RewriteError:
        raise
    except Exception as exc:
        raise RewriteError(f'instruction rewrite failed: {exc}') from exc

    if not isinstance(new_steps, list) or len(new_steps) != len(affected):
        raise RewriteError(
            f'expected {len(affected)} steps, got '
            f'{len(new_steps) if isinstance(new_steps, list) else type(new_steps).__name__}')

    out = [dict(s) if isinstance(s, dict) else {'text': str(s)} for s in steps]
    for n, position in enumerate(affected):
        new_text = (new_steps[n] or {}).get('text', '').strip() if isinstance(
            new_steps[n], dict) else str(new_steps[n]).strip()
        if not new_text:
            raise RewriteError(f'empty step text at position {position}')
        for change in plan.changes:
            if _names(new_text, change.old_name) and not _names(
                    new_text, change.new_name):
                raise RewriteError(
                    f'step {position} still names {change.old_name!r}')
        # Keep everything the model was not asked to produce.
        out[position]['text'] = new_text

    return out


_PROSE_PROMPT = (
    'Toto je název a popis českého receptu, ve kterém se mění suroviny.\n'
    'Záměny:\n{swaps}\n\n'
    'Přepiš název a popis tak, aby odpovídaly NOVÉ surovině. Zachovej styl, '
    'tón i přibližnou délku. Neměň nic jiného — nepřidávej nové informace, '
    'rady ani sliby. Pokud se surovina v názvu nebo popisu nevyskytuje, vrať '
    'ho beze změny.\n\n'
    'Název: {name}\n'
    'Popis: {description}\n\n'
    'Vrať POUZE JSON: {{"name": "...", "description": "..."}}'
)


def rewrite_prose(
    name, description, plan: SubstitutionPlan,
    *, generate: Optional[Callable[[str], str]] = None,
) -> tuple:
    """(name, description) with swapped-out ingredients renamed.

    The ingredient list and the steps were always rewritten; the prose around
    them was not. That left recipes whose title still promised an ingredient
    the recipe no longer contained — a claim the reader sees first.

    Skips the LLM entirely unless a field leans on a word the swap removed —
    'Vanilkový koláč' survives extrakt -> aroma untouched. Fail-closed:
    raises RewriteError if the model returns the wrong shape or leaves an old
    ingredient name standing, and the caller discards the whole rewrite.
    """
    from diet_planner.services.prompt_facets import _strip_code_fence

    name = name or ''
    description = description or ''
    if not plan.changes:
        return name, description

    if not any(_drops(name, c) or _drops(description, c) for c in plan.changes):
        # Nothing the prose claims stopped being true — leave it alone.
        return name, description

    swaps = '\n'.join(f'- {c.old_name} → {c.new_name}' for c in plan.changes)
    prompt = _PROSE_PROMPT.format(
        swaps=swaps, name=name, description=description)

    gen = generate or _default_generate
    # Counted before the call: a discarded rewrite still burned the tokens.
    _USAGE['calls'] += 1
    try:
        raw = gen(prompt)
        data = json.loads(_strip_code_fence(raw))
        new_name = data['name']
        new_description = data['description']
    except RewriteError:
        raise
    except Exception as exc:
        raise RewriteError(f'prose rewrite failed: {exc}') from exc

    if not isinstance(new_name, str) or not isinstance(new_description, str):
        raise RewriteError('prose rewrite returned a non-string field')
    new_name = new_name.strip()
    new_description = new_description.strip()
    if not new_name:
        raise RewriteError('prose rewrite returned an empty name')

    for change in plan.changes:
        for label, text in (('name', new_name),
                            ('description', new_description)):
            if _names(text, change.old_name) and not _names(text, change.new_name):
                raise RewriteError(f'{label} still names {change.old_name!r}')

    return new_name, new_description
