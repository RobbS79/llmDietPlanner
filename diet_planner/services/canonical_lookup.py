"""
Resolve free-text ingredient names (as emitted by the LLM or scraped) to a
CanonicalIngredient row. Used by the pricing pipeline to read the
is_pantry_staple flag and other catalog-level metadata for a shopping-list line,
and by the recipe-grounding curation pipeline to decide whether a curated
ingredient maps to a buyable catalog ingredient.

Matching strategy (first hit wins):
  1. Exact (case-insensitive) on CanonicalIngredient.name / name_cs / name_sk.
  2. Exact (case-insensitive) on IngredientAlias.alias.
  3. Normalized match: scraped/LLM names carry prep + quality descriptors that
     defeat exact matching ("olivový olej, kvalitní", "čerstvě mletý černý pepř",
     "kuřecí prsa nebo stehna", "smetana ke šlehání 33%"). We strip those down to
     a base key and compare against the same key computed for every canonical
     name + alias. The normalized index is built once per process and cached.

Returns None if no match — callers must handle that as "not a staple / not
catalog-mapped, treat as a normal grocery item".
"""
from __future__ import annotations

import re
from functools import lru_cache
from typing import Dict, Optional

from django.db.models import Q

from diet_planner.models import CanonicalIngredient, IngredientAlias


# Prep / quality / state words that describe an ingredient without changing what
# you buy. Stripped (as whole tokens) when normalizing for the fallback match.
# Covers the Czech gender/number variants we actually see from the rewrite step.
_MODIFIER_WORDS = {
    # freshness / state
    "čerstvý", "čerstvá", "čerstvé", "čerstvě", "čerstvého", "čerstvou",
    "sušený", "sušená", "sušené", "sušeného",
    "mražený", "mražená", "mražené",
    "vařený", "vařená", "vařené", "vychlazený", "vychlazená", "vychlazené",
    "pečený", "pečená", "pečené", "pražený", "pražená", "pražené",
    "uzený", "uzená", "uzené",
    "uvařený", "uvařená", "uvařené", "uvařeného",  # cooked (sibling of vařený)
    "opražený", "opražená", "opražené", "opraženého",  # toasted (sibling of pražený)
    "opečený", "opečená", "opečené",  # pan-toasted (bread/baguette) — still the bread
    "grilovaný", "grilovaná", "grilované",  # grilled — a cooking method, not a product
    "studený", "studená", "studené",  # cold (fridge state) — same product
    "nastrouhaný", "nastrouhaná", "nastrouhané",  # grated (sibling of strouhaný)
    "rozmačkaný", "rozmačkaná", "rozmačkané",  # mashed: mashed banana/avocado is still the fruit
    "rozdrobený", "rozdrobená", "rozdrobené",  # crumbled: crumbled feta is still feta
    "natvrdo",  # hard-boiled (eggs) — a prep state, not a different product
    "rozpuštěný", "rozpuštěná", "rozpuštěné", "rozpuštěného",  # melted X is still X
    "vlažný", "vlažná", "vlažné", "teplý", "teplá", "teplé",  # lukewarm / warm
    "nakládaný", "nakládaná", "nakládané", "sterilovaný", "sterilovaná", "sterilovaný",
    # cut / form
    "mletý", "mletá", "mleté", "mletého", "mleně",
    "celý", "celá", "celé", "celého",
    "drcený", "drcená", "drcené",
    "krájený", "krájená", "krájené", "nakrájený", "nakrájená", "nakrájené",
    "sekaný", "sekaná", "sekané", "nasekaný", "nasekaná", "nasekané",
    "strouhaný", "strouhaná", "strouhané",
    "plátky", "kostky", "nudličky", "vločky",  # only when trailing; harmless as tokens
    # fat / quality / size
    "plnotučný", "plnotučná", "plnotučné", "polotučný", "polotučná", "polotučné",
    "kvalitní", "extra", "panenský", "panenská", "panenské", "pevný", "pevná", "pevné",
    "jemný", "jemná", "jemné", "velký", "velká", "velké", "malý", "malá", "malé",
    "střední",  # medium: a size, not a different product ("střední žlutá cibule")
    "přírodní", "blanšírovaný", "blanšírovaná", "blanšírované",  # natural / blanched
    "kvašený", "kvašená", "kvašené", "křupavý", "křupavá", "křupavé",
    "krémový", "krémová", "krémové",  # creamy peanut butter -> peanut butter
    "neslazený", "neslazená", "neslazené",  # unsweetened: same SKU at the till
    "zralý", "zralá", "zralé", "zralého", "zralou",  # ripe: state, not identity
    "vyzrálý", "vyzrálá", "vyzrálé", "vyzrálého",  # fully ripe (sibling of zralý)
    "jemně",  # finely (degree adverb on a cut) — "jemně nasekaná" → just the noun
    # retail descriptors seen on leaflet produce/meat that don't change identity
    "konzumní",  # "brambory konzumní" — table potatoes are just potatoes
    "raný", "raná", "rané",  # early (new-season) — same vegetable
    "kuchyňský", "kuchyňská", "kuchyňské",  # culinary (yellow cooking onion) — same onion
    "baby",  # "baby špenát" — still spinach
    "selský", "selská", "selské",  # farmhouse-style — same dairy product
    # generic head-nouns that don't change identity
    "maso", "koření",
    # bare connectors that survive a list ("rýže vařená a vychlazená")
    "a", "i", "s", "se", "z",
    # english fall-throughs
    "fresh", "dried", "ground", "whole", "chopped", "sliced", "minced", "grated",
    "large", "small", "extra", "virgin", "fine", "frozen", "cooked",
}

# Store/producer brand + grade labels. These never change *what* you buy, but
# they wreck the normalized-multiset match for scraped leaflet names — plain
# "Avokádo" resolves, "Avokádo bio Nature's Promise" did not. Stripped as whole
# tokens, exactly like _MODIFIER_WORDS. Kept separate for clarity/maintenance.
# Only brands that are unambiguously NOT an ingredient word belong here.
_BRAND_WORDS = {
    # grade / label markers
    "bio", "premium", "finest", "exclusive", "deluxe", "standard",
    # CZ store private labels & dairy/bakery producers seen on leaflets
    "pilos", "milbona", "clever", "boni", "olma", "olmais", "hollandia",
    "danone", "activia", "choceňský", "choceňská", "milko", "madeta",
    "laktos", "penam", "odkolek", "breadway", "tesco", "kunín", "kunin",
    "nature's", "natures", "promise", "karlova", "koruna",
}


# Prepositional / descriptor tails: everything from these markers onward is a
# preparation note, not part of the ingredient identity.
#   "olej na smažení" -> "olej",  "smetana ke šlehání" -> "smetana"
_TAIL_MARKERS = re.compile(
    r"\s+(?:na\s|ke\s|ku\s|k\s|z\s+konzervy|z\s+plechovky"
    r"|v\s+konzervě|v\s+plechovce|v\s+nálevu|do\s)",
)


def _strip_descriptors(raw: str) -> str:
    """Reduce a free-text ingredient name to an order-independent base key.

    Czech grocery names appear in both word orders ("černý pepř" vs
    "pepř černý mletý", "hladká mouka" vs "mouka hladká"), so after stripping
    descriptors we sort the remaining tokens — the key is a multiset of content
    words, not a phrase. This makes the match robust to word order.
    """
    s = raw.lower().strip()
    s = re.sub(r"\(.*?\)", " ", s)            # drop parentheticals
    s = s.split(",")[0]                        # drop post-comma descriptor
    parts = re.split(r"\bnebo\b|\bor\b|/", s)  # "x nebo y" -> first option
    s = parts[0]
    if len(parts) > 1:
        first_tokens = parts[0].split()
        # "kokosový nebo olivový olej": the head noun ("olej") is shared and
        # trails the *last* option. When the first option is a lone adjective
        # (Czech acute ending ý/á/é — nouns like "máslo"/"olej"/"sůl" lack it),
        # it has no head noun of its own, so borrow the trailing one.
        if len(first_tokens) == 1 and re.search(r"[ýáé]$", first_tokens[0]):
            last_tokens = parts[-1].split()
            if last_tokens:
                s = f"{first_tokens[0]} {last_tokens[-1]}"
    s = _TAIL_MARKERS.split(s)[0]              # drop prepositional tails
    s = re.sub(r"\s*\d+([.,]\d+)?\s*%?", " ", s)  # drop quantities / percentages
    s = re.sub(r"[¼½¾⅐⅑⅒⅓⅔⅕⅖⅗⅘⅙⅚⅛⅜⅝⅞]", " ", s)  # drop unicode vulgar fractions
    tokens = [
        t for t in re.split(r"[\s]+", s.strip())
        if t and t not in _MODIFIER_WORDS and t not in _BRAND_WORDS
    ]
    return " ".join(sorted(tokens)).strip()


@lru_cache(maxsize=1)
def _normalized_index() -> Dict[str, int]:
    """Map normalized-key -> CanonicalIngredient id, over all names + aliases.

    Built once per process; call `clear_cache()` after seeding new rows in the
    same process. More-specific names are inserted first so a shorter alias
    cannot clobber a better key (dict keeps the first writer via setdefault).
    """
    index: Dict[str, int] = {}

    def add(text: str, ci_id: int) -> None:
        key = _strip_descriptors(text or "")
        if key:
            index.setdefault(key, ci_id)

    for ci in CanonicalIngredient.objects.all().values("id", "name", "name_cs", "name_sk"):
        for field in ("name_cs", "name", "name_sk"):
            add(ci[field], ci["id"])
    for al in IngredientAlias.objects.all().values("canonical_ingredient_id", "alias"):
        add(al["alias"], al["canonical_ingredient_id"])
    return index


def clear_cache() -> None:
    """Drop the cached normalized index (call after seeding canonical rows)."""
    _normalized_index.cache_clear()


def resolve_canonical(name: str) -> Optional[CanonicalIngredient]:
    if not name:
        return None
    needle = name.strip()
    if not needle:
        return None

    # 1 + 2: exact match on canonical names, then aliases (fast path).
    ci = CanonicalIngredient.objects.filter(
        Q(name__iexact=needle)
        | Q(name_cs__iexact=needle)
        | Q(name_sk__iexact=needle)
    ).first()
    if ci is not None:
        return ci

    alias = (
        IngredientAlias.objects
        .select_related('canonical_ingredient')
        .filter(alias__iexact=needle)
        .first()
    )
    if alias is not None:
        return alias.canonical_ingredient

    # 3: normalized fallback — strip prep/quality descriptors and match on the
    # base key against the cached normalized index.
    key = _strip_descriptors(needle)
    if not key:
        return None
    ci_id = _normalized_index().get(key)
    if ci_id is not None:
        return CanonicalIngredient.objects.filter(pk=ci_id).first()
    return None
