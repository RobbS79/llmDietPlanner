"""Czech captions written by Gemini from a facts dict, then checked by a
deterministic validator. The validator is the honesty gate; the human ✅ in
Slack is the taste gate.

What the validator enforces:

- **Numbers.** Every number in the caption must appear in the facts. Facts
  dates (``2026-09-13``) also license the Czech rendering ``13. 9. 2026``.
  Identifier fields (``recipe_id``, ``iso_week``, urls…) are *not* claims, so
  the digits inside them license nothing.
- **Shops.** A shop is "mentioned" when any caption word starts with the
  shop's stem and is at most 3 characters longer, so ``Lidlu``, ``Kauflandu``
  and ``Tescu`` are hits while ``Kaufmann`` and ``penne`` are not. Bases
  ignore the domain suffix, so known ``Rohlik.cz`` matches fact shop
  ``Rohlik``. Two bases are ordinary Czech words as well (``rohlik``,
  ``kosik``); those count only when capitalized, so ``do košíku`` is a basket.
  A mentioned shop that is not in the facts is a violation.
- **Recipes.** A known recipe counts as mentioned when *every* one of its
  significant word stems appears in the caption (allowing up to 3 characters
  of Czech case ending), so ``svíčkovou`` hits ``Svíčková`` but ``svíčku``,
  ``brambory`` and ``rizika`` do not. Stems that fold down below 4 characters
  keep their diacritics, so ``Rýže`` does not fire on ``ryze``.
- **Sales-speak.** Savings, exclusivity, "cheapest", guarantees — plus prices
  and percentages, which the facts never carry — are banned outright.
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
WORD_RE = re.compile(r'\w+', re.UNICODE)
ISO_DATE_RE = re.compile(r'(\d{4})-(\d{2})-(\d{2})')
VOWELS = 'aeiouy'
MAX_ENDING_CHARS = 3        # Czech case endings: Lidl->Lidlu, Svíčková->svíčkovou
MIN_STEM_CHARS = 4          # shorter stems fire on every lookalike word
# Vowels a Czech shop name swaps when it declines: Tesco -> v Tescu, Billa ->
# v Bille. 'y' is deliberately absent: Penny does not decline, and dropping it
# would make the common noun "penne" look like the shop.
SHOP_DECLINING_VOWELS = 'aeo'
# Shop bases that are also ordinary Czech words (a bread roll, a basket). For
# these — and only these — a lowercase word is the common noun, not the shop.
COMMON_NOUN_BASES = frozenset({'rohlik', 'kosik'})
# Digits inside these fields identify a row; they are never a claim about the
# world, so they must not whitelist a number the caption invents.
IDENTIFIER_KEYS = {'recipe_id', 'goal_id', 'iso_week', 'kind', 'link', 'url',
                   'source_url', 'image_url', 'canonical', 'slot'}
BANNED = [
    (re.compile(r'ušetří', re.I), 'promises savings we do not compute'),
    (re.compile(r'exkluzivn', re.I), 'claims exclusivity'),
    (re.compile(r'nejlevnější', re.I), 'claims cheapest'),
    (re.compile(r'zaručen', re.I), 'guarantees a result'),
    # The facts carry neither prices nor percentages, so any of either is made up.
    (re.compile(r'\d+(?:[.,]\d+)?\s*(?:Kč|CZK|korun|,-)', re.I), 'states a price'),
    (re.compile(r'\d+\s*(?:%|procent)', re.I), 'states a percentage'),
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
        for key, v in value.items():
            if key in IDENTIFIER_KEYS:
                continue
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
        # An ISO date licenses its Czech rendering too: "13. 9. 2026".
        for year, month, day in ISO_DATE_RE.findall(value):
            found |= {year, month, month.lstrip('0'), day, day.lstrip('0')}
    return found


def _shop_base(name: str) -> str:
    """'Rohlik.cz' -> 'rohlik', 'Kaufland' -> 'kaufland'. The first alphabetic
    token of the folded name, so a domain suffix never splits one shop in two."""
    match = re.match(r'[^\W\d_]+', _fold(name), re.UNICODE)
    return match.group(0) if match else ''


def _shop_stem(base: str) -> str:
    """The part of a shop base that survives declension: 'tesco' -> 'tesc'
    (v Tescu), 'kaufland' -> 'kaufland'. Never shorter than MIN_STEM_CHARS."""
    stem = base[:-1] if base[-1:] in SHOP_DECLINING_VOWELS else base
    return stem if len(stem) >= MIN_STEM_CHARS else base


def _words(body: str) -> list:
    """(folded word, was it capitalized) for every word in the caption."""
    return [(_fold(w), w[:1].isupper()) for w in WORD_RE.findall(body)]


def _inflects_from(word: str, stem: str) -> bool:
    """True when `word` looks like `stem` carrying a Czech case ending —
    same opening, at most MAX_ENDING_CHARS longer ('lidl' -> 'lidlu',
    'kaufland' -> 'kauflandu', but not 'kaufland' -> 'kaufmann')."""
    return bool(stem) and word.startswith(stem) and len(word) - len(stem) <= MAX_ENDING_CHARS


def _recipe_stems(name: str) -> list:
    """(stem, keep_diacritics) for every word of a recipe name longer than two
    characters, with a trailing vowel dropped so the stem survives declension.

    A stem below MIN_STEM_CHARS is too blunt once diacritics are folded away —
    'kaše' would become 'kas' and fire on "kasa", 'rýže' would become 'ryz' and
    fire on "ryze". Those short stems are therefore matched with their
    diacritics intact, which is exactly the signal folding threw away.
    """
    stems = []
    for token in WORD_RE.findall(name.lower()):
        if len(token) <= 2:
            continue
        folded = _fold(token)
        stem = folded[:-1] if folded[-1] in VOWELS else folded
        if len(stem) >= MIN_STEM_CHARS:
            stems.append((stem, False))
        else:
            stems.append((token[:-1] if _fold(token[-1:]) in VOWELS else token, True))
    return stems


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

    fact_shops = {_shop_base(s) for s in _numbers_free_strings(facts, key='shop')}
    folded_body = _fold(body)
    lowered_body = body.lower()
    words = _words(body)
    reported = set()
    for shop in known_shops:
        base = _shop_base(shop)
        if not base or base in fact_shops or base in reported:
            continue
        stem = _shop_stem(base)
        proper_noun_only = base in COMMON_NOUN_BASES
        if any(_inflects_from(word, stem) and (capitalized or not proper_noun_only)
               for word, capitalized in words):
            reported.add(base)
            violations.append(f'shop {shop!r} is not in the facts')

    fact_names = _names_in_facts(facts)
    for name in known_recipes:
        if _fold(name) in fact_names:
            continue
        stems = _recipe_stems(name)
        if stems and all(
                re.search(rf'\b{re.escape(stem)}\w{{0,{MAX_ENDING_CHARS}}}\b',
                          lowered_body if keep_diacritics else folded_body)
                for stem, keep_diacritics in stems):
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
        elif kind == 'deals':
            last_violations.append('group_variant missing for deals')
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
