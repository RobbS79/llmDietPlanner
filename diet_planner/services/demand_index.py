"""What Czechs actually cook, harvested from public recipe-site rankings.

Pure functions: parsing and enrichment only. Fetching lives in the
`build_demand_index` command so this module stays testable against fixtures.

Why rankings at all: the corpus has only ever been measured against itself
("458 published, 164 fail the shopping bar"). Demand data is what turns that
into "of the dishes people look for, we can serve N".
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional

from bs4 import BeautifulSoup

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


def _in_suggestion_widget(anchor) -> bool:
    """True if an ancestor is a "you might like" / related-recipes widget.

    toprecepty.cz repeats a "Mohlo by se vám líbit" widget (ancestor class
    `b-suggest__item`) twice, earlier in the document than the actual ranked
    grid. Its links are real recipes but not part of the ranking being
    measured, so counting them would misassign the top ranks. "suggest" is
    unused elsewhere on either target site's ranking markup (recepty.cz's
    real listing uses "recommended-recipes", a different word), so this stays
    a safe, narrow exclusion rather than a broad content filter.
    """
    for parent in anchor.parents:
        classes = parent.get('class') if hasattr(parent, 'get') else None
        if classes and any('suggest' in cls.lower() for cls in classes):
            return True
    return False


def parse_ranking(html: str, *, source: str, category: str) -> List[DemandTerm]:
    """Ranked dish names from a listing page, best first.

    Rank is positional: these pages are already sorted, and the rank badges are
    images on only the first few items. Duplicate links (thumbnail + title
    anchor pointing at the same recipe) collapse to their first occurrence so
    ranks stay dense; when duplicates disagree on the name (one truncated,
    one not — see `_MORE_ABOUT_PREFIX`), the fullest name wins.
    """
    if not html:
        return []

    soup = BeautifulSoup(html, 'lxml')
    order: List[str] = []  # hrefs in first-seen order, i.e. rank order
    candidates: dict = {}  # href -> candidate names seen for it

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
        if _in_suggestion_widget(anchor):
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
        name = max(untruncated, key=len) if untruncated else names[0]
        terms.append(DemandTerm(
            term=name, rank=rank, source=source, category=category))

    return terms
