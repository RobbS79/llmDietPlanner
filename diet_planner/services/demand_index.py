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


#: Ancestor class markers for widgets that carry real recipe links but are
#: not the ranking a page was fetched for, so they must not contaminate rank
#: order or supply a fallback name when the "real" title is truncated:
#:   toprecepty.cz "b-suggest__item"  -> "Mohlo by se vám líbit" (you might
#:                                        like) widget, repeated twice ahead
#:                                        of the actual ranked grid.
#:   recepty.cz    "recipe-ranking__" -> a "most visited this week" trending
#:                                        sidebar with its own separate,
#:                                        CSS-truncated-only titles (no
#:                                        untruncated "více o" companion).
#: Each marker is confirmed (via grep against the captured fixtures) to be
#: unused anywhere in either site's real listing markup, so this stays a
#: narrow, evidence-backed exclusion rather than a broad content filter.
_EXCLUDED_WIDGET_MARKERS = ('suggest', 'recipe-ranking')


def _in_excluded_widget(anchor) -> bool:
    """True if an ancestor's class marks this as a non-ranking widget."""
    for parent in anchor.parents:
        classes = parent.get('class') if hasattr(parent, 'get') else None
        if not classes:
            continue
        for cls in classes:
            cls_lower = cls.lower()
            if any(marker in cls_lower for marker in _EXCLUDED_WIDGET_MARKERS):
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
        name = max(untruncated, key=len) if untruncated else names[0]
        terms.append(DemandTerm(
            term=name, rank=rank, source=source, category=category))

    return terms
