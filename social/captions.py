"""Czech captions written by Gemini from a facts dict, then checked by a
deterministic validator. The validator is the honesty gate: any number, shop
or recipe the caption mentions must be in the facts, and sales-speak that the
data cannot back is banned outright. The human ✅ in Slack is the taste gate.
"""
from __future__ import annotations

import json
import re
import unicodedata
from typing import Callable, Iterable

from diet_planner.services.llm_health import default_generate

MAX_CAPTION_CHARS = 600
MAX_GROUP_CHARS = 350
NUMBER_RE = re.compile(r'\d+(?:[.,]\d+)?')
URL_RE = re.compile(r'https?://\S+')
BANNED = [
    (re.compile(r'ušetří', re.I), 'promises savings we do not compute'),
    (re.compile(r'exkluzivn', re.I), 'claims exclusivity'),
    (re.compile(r'nejlevnější', re.I), 'claims cheapest'),
    (re.compile(r'zaručen', re.I), 'guarantees a result'),
    (re.compile(r'\d+\s*%\s*slev', re.I), 'percentage discount not in facts'),
]


class CaptionRejected(Exception):
    """Gemini could not produce a caption that passes validation."""


def _fold(text: str) -> str:
    """Lowercase, strip diacritics — for fuzzy name matching."""
    nfkd = unicodedata.normalize('NFKD', text)
    return ''.join(c for c in nfkd if not unicodedata.combining(c)).lower()


def _numbers_in(value) -> set:
    found = set()
    if isinstance(value, dict):
        for v in value.values():
            found |= _numbers_in(v)
    elif isinstance(value, (list, tuple)):
        for v in value:
            found |= _numbers_in(v)
    elif isinstance(value, bool):
        pass
    elif isinstance(value, (int, float)):
        found.add(str(value).replace('.', ','))
        found.add(str(value))
    elif isinstance(value, str):
        for m in NUMBER_RE.findall(URL_RE.sub('', value)):
            found.add(m)
            found.add(m.replace('.', ','))
    return found


def _names_in_facts(facts: dict) -> set:
    names = set()
    if facts.get('name'):
        names.add(facts['name'])
    for r in facts.get('recipes', []):
        names.add(r['name'])
    for m in facts.get('meals', []):
        names.add(m['name'])
    return {_fold(n) for n in names}


def validate_caption(caption: str, facts: dict, *, known_shops: Iterable[str],
                     known_recipes: Iterable[str], max_chars: int = MAX_CAPTION_CHARS) -> list:
    """Return a list of human-readable violations; empty means the caption is honest."""
    violations = []
    body = URL_RE.sub('', caption)
    if len(caption) > max_chars:
        violations.append(f'caption is {len(caption)} chars, limit {max_chars}')

    allowed_numbers = _numbers_in(facts)
    for number in NUMBER_RE.findall(body):
        if number not in allowed_numbers and number.replace(',', '.') not in allowed_numbers:
            violations.append(f'number {number!r} is not in the facts')

    fact_shops = {_fold(s) for s in _numbers_free_strings(facts, key='shop')}
    folded_body = _fold(body)
    for shop in known_shops:
        stem = _fold(shop)[:4]            # "Lidl" matches "Lidlu", "Kauf" matches "Kauflandu"
        if stem and stem in folded_body and _fold(shop) not in fact_shops:
            violations.append(f'shop {shop!r} is not in the facts')

    fact_names = _names_in_facts(facts)
    for name in known_recipes:
        folded = _fold(name)
        stem = folded[:max(4, len(folded) - 3)]   # tolerate Czech case endings
        if stem in folded_body and folded not in fact_names:
            violations.append(f'recipe {name!r} is not in the facts')

    for pattern, why in BANNED:
        if pattern.search(body):
            violations.append(f'banned phrase ({why}): {pattern.pattern}')
    return violations


def _numbers_free_strings(value, key: str) -> set:
    out = set()
    if isinstance(value, dict):
        for k, v in value.items():
            if k == key and isinstance(v, str):
                out.add(v)
            elif k == 'deal_shops' and isinstance(v, list):
                out |= set(v)
            else:
                out |= _numbers_free_strings(v, key)
    elif isinstance(value, list):
        for v in value:
            out |= _numbers_free_strings(v, key)
    return out


HOUSE_RULES = """Jsi copywriter české aplikace Vařto (jídelníčky na míru s recepty a přehledem slev z letáků).
Piš česky, neformálně, jako člověk, ne jako reklama. Žádné vykřičníky v každé větě, max 2 emoji.
POUŽIJ JEN FAKTA Z JSONU NÍŽE. Nevymýšlej ceny, procenta, úspory ani obchody, které v datech nejsou.
Neslibuj úspory ("ušetříte"), nepiš "exkluzivní", "nejlevnější", "zaručeně".
Odkaz z pole "link" vlož na konec doslovně, včetně {channel}.
Odpověz POUZE JSON objektem, bez komentáře."""

KIND_BRIEF = {
    'deals': 'Pondělní přehled: které suroviny jsou tenhle týden v akci a kde, a 1–2 recepty, které je využijí. '
             'Vrať {"caption": "<max 600 znaků pro Facebook>", "group_variant": "<max 350 znaků, v první osobě, '
             '\'stavím appku…\', bez hashtagů, pro vložení do facebookové skupiny>"}.',
    'recipe': 'Středeční recept: jméno, kcal na porci, čas, kde je zdroj, a kolik surovin je v akci. '
              'Vrať {"caption": "<max 600 znaků, na konci 3–5 hashtagů>"}.',
    'showcase': 'Páteční ukázka: co uživatel napsal (pole "prompt") a jaký den mu Vařto sestavilo (pole "meals"). '
                'Vrať {"caption": "<max 600 znaků>"}.',
}


def _parse_json(text: str) -> dict:
    text = text.strip()
    text = re.sub(r'^```(?:json)?\s*|\s*```$', '', text, flags=re.S)
    start, end = text.find('{'), text.rfind('}')
    if start == -1 or end == -1:
        raise CaptionRejected(f'model did not return JSON: {text[:120]!r}')
    try:
        data = json.loads(text[start:end + 1])
    except json.JSONDecodeError as exc:
        raise CaptionRejected(f'model returned invalid JSON: {exc}')
    if not isinstance(data, dict) or not isinstance(data.get('caption'), str):
        raise CaptionRejected('model JSON has no "caption" string')
    return data


def write_caption(facts: dict, *, generate: Callable[[str], str] = default_generate,
                  known_shops: Iterable[str], known_recipes: Iterable[str]) -> dict:
    """Return {'caption': str, 'group_variant': str}; raise CaptionRejected after one retry."""
    kind = facts.get('kind', 'recipe')
    known_shops, known_recipes = set(known_shops), set(known_recipes)
    prompt = f'{HOUSE_RULES}\n\n{KIND_BRIEF[kind]}\n\nFAKTA:\n{json.dumps(facts, ensure_ascii=False, indent=1)}'
    last_violations = []
    for attempt in range(2):
        text = generate(prompt if attempt == 0 else
                        f'{prompt}\n\nPŘEDCHOZÍ POKUS BYL ZAMÍTNUT, OPRAV TOHLE:\n- ' + '\n- '.join(last_violations))
        data = _parse_json(text)
        caption = data['caption'].strip()
        group = (data.get('group_variant') or '').strip() if kind == 'deals' else ''
        last_violations = validate_caption(caption, facts, known_shops=known_shops,
                                           known_recipes=known_recipes)
        if group:
            last_violations += [f'group_variant: {v}' for v in validate_caption(
                group, facts, known_shops=known_shops, known_recipes=known_recipes,
                max_chars=MAX_GROUP_CHARS)]
        if not last_violations:
            return {'caption': caption, 'group_variant': group}
    raise CaptionRejected('; '.join(last_violations))


# ---- DB-backed known sets (call from the command, pass into the pure functions)

def known_shops() -> set:
    from diet_planner.models import GroceryStore
    names = set()
    for name, chain in GroceryStore.objects.values_list('name', 'chain'):
        names.add(name.split(' (')[0])
        names.add(chain.title())
    return {n for n in names if n}


def known_recipe_names() -> set:
    from diet_planner.models import Recipe
    return set(Recipe.objects.filter(is_public=True).values_list('name', flat=True))
