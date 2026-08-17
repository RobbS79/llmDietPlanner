"""What Czechs actually cook, harvested from public recipe-site rankings.

Pure functions: parsing and enrichment only. Fetching lives in the
`build_demand_index` command so this module stays testable against fixtures.

Why rankings at all: the corpus has only ever been measured against itself
("458 published, 164 fail the shopping bar"). Demand data is what turns that
into "of the dishes people look for, we can serve N".
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Dict, List, Optional

from bs4 import BeautifulSoup

from diet_planner.models import CanonicalIngredient, IngredientAlias
from diet_planner.services.canonical_lookup import fold_diacritics, resolve_canonical

logger = logging.getLogger(__name__)

#: Recipe detail links, single path segment after /recept/ containing a
#: digit somewhere in it (the id). Both target sites are covered:
#:   toprecepty.cz -> /recept/13237-uzasny-tvarohovy-moucnik-ke-kave/  (leading id)
#:   recepty.cz    -> /recept/asijske-kureci-nudlicky-s-cuketou-168830 (trailing id)
#: Nav/listing links on both sites (/recept/oblibene, /recept/oblibene/2,
#: /recept/nejnovejsi, ...) have no digit in the first segment, or carry an
#: extra path segment, so the "single segment, contains a digit" constraint
#: excludes them without an explicit denylist.
_RECIPE_HREF = re.compile(r'^/recept/[\w-]*\d[\w-]*/?$')

#: recepty.cz CSS-truncates card titles ("…") but repeats the full title,
#: prefixed with "více o " ("more about "), in a second anchor lower in the
#: same card. Recognize that prefix so the full title wins over the
#: truncated one; unused on toprecepty.cz (grep confirms zero occurrences).
_MORE_ABOUT_PREFIX = re.compile(r'^více o\s+', re.IGNORECASE)
_ELLIPSIS = '…'


@dataclass(frozen=True)
class DemandTerm:
    term: str
    rank: int
    source: str
    category: str
    rating: Optional[float] = None


#: BEM block names for widgets that carry real recipe links but are not the
#: ranking a page was fetched for, so they must not contaminate rank order or
#: supply a fallback name when the "real" title is truncated:
#:   toprecepty.cz "b-suggest__item"    -> "Mohlo by se vám líbit" (you might
#:                                          like) widget, repeated twice ahead
#:                                          of the actual ranked grid.
#:   recepty.cz    "recipe-ranking__*"  -> the "Poslední sledované recepty"
#:                                          (recently viewed recipes) sidebar,
#:                                          whose only text-bearing anchor is
#:                                          CSS-truncated with no untruncated
#:                                          "více o" companion anywhere in the
#:                                          card.
#: Both fixtures were captured anonymously via plain curl (no cookies, no
#: session), so these widgets are confirmed to render for an unauthenticated
#: fetch too — `build_demand_index` will hit the same markup, not a
#: logged-in-only variant. That means this is live, load-bearing exclusion
#: logic, not dead code guarding against a hypothetical.
#:
#: Matching is anchored to the BEM block boundary (exact block class, or
#: block followed by "__" or "--") rather than bare substring: the
#: recepty.cz fixture also has an unrelated `class="main-suggest"` header
#: search-autocomplete container, which a bare "suggest" substring check
#: would also match. It is currently harmless only because that div holds no
#: anchors — bare substring matching would become a silent-zero-yield risk
#: of its own the day a real listing grid class contains one of these words
#: as a substring (e.g. a hypothetical "recipe-ranking-list" for the actual
#: ranking).
_EXCLUDED_WIDGET_BLOCKS = ('b-suggest', 'recipe-ranking')


def _matches_excluded_block(cls: str) -> bool:
    cls = cls.lower()
    return any(
        cls == block or cls.startswith(block + '__') or cls.startswith(block + '--')
        for block in _EXCLUDED_WIDGET_BLOCKS
    )


def _in_excluded_widget(anchor) -> bool:
    """True if the anchor itself, or an ancestor, is a non-ranking widget."""
    for element in (anchor, *anchor.parents):
        classes = element.get('class') if hasattr(element, 'get') else None
        if not classes:
            continue
        if any(_matches_excluded_block(cls) for cls in classes):
            return True
    return False


def parse_ranking(html: str, *, source: str, category: str) -> List[DemandTerm]:
    """Ranked dish names from a listing page, best first.

    Rank is positional: these pages are already sorted, and the rank badges are
    images on only the first few items. Duplicate links (thumbnail + title
    anchor pointing at the same recipe) collapse to their first occurrence so
    ranks stay dense; when duplicates disagree on the name (one truncated,
    one not — see `_MORE_ABOUT_PREFIX`), the longest untruncated candidate
    wins.

    Known accepted risk in that "longest untruncated candidate wins" rule:
    it assumes a shorter candidate sharing an href is the truncated one. That
    breaks if a site instead folds badge text (e.g. a "30 minut" prep-time
    label) into the SAME anchor as the title with no nested `<a>` to trigger
    the wrapper skip above — the badge-plus-title text would be longer than
    the clean title and would win. Not observed on either target site as of
    this writing (toprecepty.cz keeps badges outside the title anchor;
    recepty.cz's badge-carrying anchor is the wrapper, which is skipped). If
    a future source hits this shape, the fix is source-specific badge
    stripping, not changing this heuristic — the `více o` full title on
    recepty.cz depends on "longest wins" as written.
    """
    if not html:
        return []

    soup = BeautifulSoup(html, 'lxml')
    order: List[str] = []  # hrefs in first-seen order, i.e. rank order
    candidates: Dict[str, List[str]] = {}  # href -> candidate names seen for it

    for anchor in soup.find_all('a', href=True):
        href = anchor['href']
        if not _RECIPE_HREF.match(href):
            continue
        if anchor.find('a') is not None:
            # A wrapper/card anchor with a nested anchor inside (recepty.cz
            # nests a clean title link inside a noisier card link that also
            # carries a prep-time badge). Skip the wrapper; the nested anchor
            # supplies a candidate name on its own turn through this loop.
            continue
        if _in_excluded_widget(anchor):
            continue
        name = ' '.join(anchor.get_text(' ', strip=True).split())
        name = _MORE_ABOUT_PREFIX.sub('', name)
        if len(name) <= 3:
            continue  # image-only anchors carry no title
        if href not in candidates:
            order.append(href)
            candidates[href] = []
        candidates[href].append(name)

    terms: List[DemandTerm] = []
    for rank, href in enumerate(order, start=1):
        names = candidates[href]
        untruncated = [n for n in names if not n.endswith(_ELLIPSIS)]
        if untruncated:
            name = max(untruncated, key=len)
        else:
            # Every candidate is CSS-truncated (no "více o"-style full-title
            # companion anchor exists for this recipe). Strip the trailing
            # ellipsis rather than shipping it as part of the "dish name".
            name = names[0].rstrip(_ELLIPSIS).rstrip()
        terms.append(DemandTerm(
            term=name, rank=rank, source=source, category=category))

    if not terms:
        # html was already confirmed non-empty above (the early `if not
        # html: return []`), so reaching here with zero terms means a
        # selector drifted, not that the page was blank.
        logger.warning(
            'demand_index.parse_ranking: 0 terms from non-empty html '
            '(source=%r, category=%r) — a selector likely drifted',
            source, category,
        )

    return terms


#: Source category -> the meal slot that demand belongs to. `None` means
#: either of two different things, deliberately conflated for now:
#:   - the category genuinely has no slot in a meal plan (desserts, drinks,
#:     preserves): real demand, out of scope on merit, reported but never
#:     scored.
#:   - 'global': the all-time/star ranking page mixes every dish type by
#:     construction (perník and bublanina sit next to guláš and svíčková on
#:     the same listing). No single slot label could be honest for it, so it
#:     cannot be scored either — scoring it as 'dinner' would mark every
#:     dessert on that page in-scope and manufacture exactly the false
#:     coverage gap this module exists to avoid. Scored demand comes from the
#:     per-category pages instead (maso, polevky, testoviny, salaty, ...);
#:     `build_demand_index` already fetches those separately.
#: Both collapse to `in_scope=False` here. If that conflation ever needs to
#: be told apart downstream (e.g. a report that shows "has no meal slot" vs
#: "page not classifiable" as separate buckets), split this into two fields
#: rather than overloading `None` further.
CATEGORY_SLOTS = {
    'global': None,
    'maso': 'dinner',
    'testoviny': 'dinner',
    'polevky': 'lunch',
    'salaty': 'lunch',
    'snidane': 'breakfast',
    'omacky': 'dinner',
    'moucniky': None,
    'dezerty': None,
    'napoje': None,
    'zavarovani': None,
}

_WORD = re.compile(r'[^\wáčďéěíňóřšťúůýž]+', re.IGNORECASE)


def _words(text: str) -> List[str]:
    return [w for w in _WORD.split(text.lower()) if len(w) > 2]


#: Minimum shared leading-prefix length for two folded words to count as the
#: same word under Czech inflection. Same floor and same reasoning as
#: `_words_match` in `user_simulation.py`: 5 is a conservative stand-in for
#: real lemmatization — long enough that unrelated words sharing a short
#: prefix ("mas" in "maso" vs "máslo") don't collapse into a false match.
_MIN_STEM_LEN = 5

#: Minimum fraction of the CANDIDATE KEY's length that the shared prefix must
#: cover, fuzzy path only. The length floor above is not enough on its own:
#: "cibulová" shares 5 characters with "cibule" (5 of 6 = 0.83, a real match)
#: but also shares 5 with a much longer, more specific key like "cibulový
#: prášek" (5 of 15 ≈ 0.33 before the single-word restriction below even
#: applies) — a short query word claiming most of a long, specific product
#: name is exactly the over-matching direction that corrupts loose coverage
#: (a false demand-side canonical manufactures a false loose hit). 0.7 keeps
#: "cibulová" ~ "cibule" while rejecting claims on far longer keys.
_MIN_COVERAGE_RATIO = 0.7


@lru_cache(maxsize=1)
def _farm_fuzzy_index() -> Dict[str, List[str]]:
    """Diacritics-folded SINGLE-WORD canonical names/aliases -> slugs, built
    ONLY to power the farm-local fuzzy fallback below.

    FARM-ONLY BOUNDARY: this is a measurement-only convenience with a
    conservative shared-prefix heuristic (see `_MIN_STEM_LEN` and
    `_MIN_COVERAGE_RATIO`). It must NEVER be promoted into
    `canonical_lookup.resolve_canonical` — that function backs curation
    intake and pricing, where a fuzzy match could silently corrupt real
    ingredient data. Keep this local to demand_index.py.

    Multiword names/aliases ("BBQ omáčka", "Cibulový prášek") are skipped
    entirely rather than split into constituent words. Splitting used to
    index each word of a multiword product separately, which is exactly how
    a bare "omáčka" query reached "bbq-sauce" and "cibulová" reached the far
    more specific "onion-powder" ("Cibulový prášek") instead of "onion"
    ("cibule") — a one-word dish-name query has no way to disambiguate which
    word of a multiword product it was supposed to mean. Multiword names
    still resolve correctly through the exact/alias/normalized
    `resolve_canonical` path, which is authoritative and where they belong.

    Follows the shape of `_normalized_index()` in canonical_lookup.py (build
    once, cache, iterate name/name_cs/name_sk + aliases).
    """
    index: Dict[str, List[str]] = {}

    def add(text: Optional[str], slug: str) -> None:
        words = _words(text or '')
        if len(words) != 1:
            return  # multiword source text — not a fuzzy-matchable key
        key = fold_diacritics(words[0]).lower()
        if not key:
            return
        slugs = index.setdefault(key, [])
        if slug not in slugs:
            slugs.append(slug)

    for ci in CanonicalIngredient.objects.all().values('slug', 'name', 'name_cs', 'name_sk'):
        for field in ('name_cs', 'name', 'name_sk'):
            add(ci[field], ci['slug'])
    for alias in IngredientAlias.objects.select_related('canonical_ingredient'):
        add(alias.alias, alias.canonical_ingredient.slug)

    return index


def _shared_prefix_len(a: str, b: str) -> int:
    shared = 0
    for ca, cb in zip(a, b):
        if ca != cb:
            break
        shared += 1
    return shared


def _fuzzy_canonical_slug(word: str) -> Optional[str]:
    """Farm-local fallback for `resolve_canonical` misses on inflected Czech
    dish-name words (e.g. 'bramborem' -> 'brambory' -> slug 'potatoes').

    Only ever called after `resolve_canonical` has already returned None for
    this word — see `enrich_term`. A candidate key must clear BOTH
    `_MIN_STEM_LEN` (absolute shared-prefix length) and
    `_MIN_COVERAGE_RATIO` (shared prefix as a fraction of the key's own
    length) before it is even considered — see those constants for why each
    exists; both guard against over-matching, which is the dangerous
    direction here (a false demand-side canonical manufactures a false loose
    coverage hit, inflating the headline number).

    Among the survivors, longest shared prefix wins first. A remaining tie
    at the same shared length prefers the key the match consumes most fully
    (the smaller key — closer to being exactly the query's stem rather than
    a truncated prefix of a longer word); any tie still remaining after that
    falls back to lexicographic slug, for reproducibility.
    """
    query = fold_diacritics(word).lower()
    if not query:
        return None

    best_shared = -1
    best_key_len: Optional[int] = None
    best_slugs: List[str] = []
    for key, slugs in _farm_fuzzy_index().items():
        shared = _shared_prefix_len(query, key)
        if shared < _MIN_STEM_LEN:
            continue
        key_len = len(key)
        if shared / key_len < _MIN_COVERAGE_RATIO:
            continue
        if shared > best_shared or (shared == best_shared and key_len < best_key_len):
            best_shared = shared
            best_key_len = key_len
            best_slugs = list(slugs)
        elif shared == best_shared and key_len == best_key_len:
            best_slugs.extend(slugs)

    if not best_slugs:
        return None
    return sorted(set(best_slugs))[0]


def enrich_term(term: DemandTerm) -> dict:
    """Add slot scope and resolved canonicals to a parsed demand term."""
    slot = CATEGORY_SLOTS.get(term.category, 'dinner')
    canonicals = []
    for word in _words(term.term):
        canonical = resolve_canonical(word)
        slug = canonical.slug if canonical is not None else _fuzzy_canonical_slug(word)
        if slug is not None and slug not in canonicals:
            canonicals.append(slug)

    return {
        'term': term.term,
        'rank': term.rank,
        'source': term.source,
        'category': term.category,
        'slot_hint': slot,
        'in_scope': slot is not None,
        'canonicals': canonicals,
        'folded': fold_diacritics(term.term).lower(),
    }
