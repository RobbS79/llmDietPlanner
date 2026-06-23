"""Active leaflet deals for a recipe's ingredients.

A deal is ACTIVE only when a real LEAFLET_DISCOUNT PriceRecord is in its
validity window right now (valid_from <= now < valid_until, with a real
non-null end), tied to a canonical ingredient. Nothing future-dated (planned),
expired, open-ended, fabricated, or mocked is ever ACTIVE. See
docs/superpowers/specs/2026-06-23-recipe-deals-headline-design.md.
"""
from diet_planner.models import PriceRecord, PriceSourceType
from diet_planner.services.canonical_lookup import resolve_canonical


def _ingredient_slug(ingredient):
    slug = (ingredient.get('canonical') or '').strip()
    if slug:
        return slug
    name = (ingredient.get('name') or '').strip()
    canonical = resolve_canonical(name) if name else None
    return canonical.slug if canonical else None


def _active_deal_index():
    """canonical slug -> chosen active deal dict.

    Active window enforced by .current() (valid_from <= now and not expired);
    we additionally require a real end date and a canonical link. Deterministic
    pick per canonical: soonest-expiring, then store code.
    """
    records = (
        PriceRecord.objects.current()
        .filter(
            source_type=PriceSourceType.LEAFLET_DISCOUNT,
            valid_until__isnull=False,
            store_product__is_active=True,
            store_product__canonical_ingredient__isnull=False,
        )
        .select_related('store_product__store',
                        'store_product__canonical_ingredient')
        .order_by('valid_until', 'store_product__store__code')
    )
    index = {}
    for record in records:
        product = record.store_product
        slug = product.canonical_ingredient.slug
        if slug in index:                      # keep first = soonest-expiring
            continue
        index[slug] = {
            'canonical': slug,
            # Clean brand name ("Lidl") for the headline, not the verbose seeded
            # store.name ("Lidl (Czech Republic)"). chain is an uppercase code.
            'shop': product.store.chain.title(),
            'display_name': product.name,
            'source_url': record.source_url or product.source_url or '',
            'valid_until': record.valid_until.isoformat(),
            # price/discount intentionally omitted this phase — no fabricated
            # money; the headline is deal-discovery only (see deals spec).
        }
    return index


def recipe_deals(ingredients):
    """Active deals for a recipe's ingredient list.

    Returns {matched, total, deals}: `total` counts non-optional ingredients,
    `deals` has one entry per matched canonical (deduped), each carrying the
    recipe `ingredient` label.
    """
    index = _active_deal_index()
    deals = []
    seen = set()
    total = 0
    for ingredient in ingredients or []:
        if ingredient.get('optional'):
            continue
        total += 1
        slug = _ingredient_slug(ingredient)
        if not slug or slug in seen:
            continue
        deal = index.get(slug)
        if not deal:
            continue
        seen.add(slug)
        deals.append({**deal, 'ingredient': ingredient.get('name') or slug})
    return {'matched': len(deals), 'total': total, 'deals': deals}
