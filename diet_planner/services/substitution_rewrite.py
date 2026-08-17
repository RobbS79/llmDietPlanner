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

from diet_planner.services.ingredient_substitution import SubstitutionPlan

logger = logging.getLogger(__name__)


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
