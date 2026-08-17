"""Reduce real user prompts to reusable phrasing templates.

`DietaryGoal.prompt` is an EncryptedTextField because it is user data. Only
shapes leave this module: a prompt that does not reduce cleanly to a known
template is DROPPED, never exported. Anything else risks a name, an address or
an email landing in git.

Phrasing is the half of query realism we cannot invent. The `Mám X` shape is
the standing example: it broke facet extraction on prod precisely because no
test author wrote prompts that way.
"""
from __future__ import annotations

import re
from typing import List, Optional, Tuple

_EMAIL = re.compile(r'\S+@\S+')
_URL = re.compile(r'https?://\S+')

#: (pattern, template). Ordered; first match wins.
_SHAPES: List[Tuple[re.Pattern, str]] = [
    (re.compile(r'^jídelníček na \d+ dní$', re.IGNORECASE), 'jídelníček na {n} dní'),
    (re.compile(r'^jidelnicek na \d+ dni$', re.IGNORECASE), 'jídelníček na {n} dní'),
    (re.compile(r'^mám .{2,30}, co uvařit\?$', re.IGNORECASE),
     'Mám {ingredient}, co uvařit?'),
    (re.compile(r'^mám .{2,30}$', re.IGNORECASE), 'Mám {ingredient}'),
    (re.compile(r'^něco (rychlého|levného|zdravého)( na .{3,20})?$', re.IGNORECASE),
     'něco {quality}'),
    (re.compile(r'^chci (zhubnout|nabrat|jíst zdravěji)$', re.IGNORECASE),
     'chci {objective}'),
    (re.compile(r'^\w[\w\s]{2,40}$', re.IGNORECASE), '{free_short}'),
]

#: Longer than this and a free-text prompt is assumed to carry personal detail.
_MAX_FREE_TEXT = 40


def reduce_prompt(prompt: str) -> Optional[str]:
    """The template a prompt reduces to, or None when it must be dropped."""
    if not prompt:
        return None
    text = ' '.join(prompt.split())
    if _EMAIL.search(text) or _URL.search(text):
        return None

    for pattern, template in _SHAPES:
        if pattern.match(text):
            if template == '{free_short}' and len(text) > _MAX_FREE_TEXT:
                return None
            return template
    return None
