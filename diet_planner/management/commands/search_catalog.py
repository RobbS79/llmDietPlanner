"""
Targeted catalog scrape: price the canonical ingredients our recipes actually
use by querying Rohlik's search API (one request per ingredient).

Unlike `scrape_catalog` (sitemap crawl of all ~22k SKUs, ~7h), this is driven
by the canonicals referenced in published recipes — hundreds of calls, minutes,
and every result is pre-mapped to its canonical (no `match_canonical` pass).

Usage:
    python manage.py search_catalog --store=ROHLIK --dry-run
    python manage.py search_catalog --store=ROHLIK --limit=20
    python manage.py search_catalog --store=ROHLIK --all-canonicals
"""
from django.core.management.base import BaseCommand, CommandError

from diet_planner.models import CanonicalIngredient, CuratedRecipe
from diet_planner.scrapers.rohlik_cz_search import RohlikCzSearchScraper

SEARCH_SCRAPER_MAP = {
    'ROHLIK': RohlikCzSearchScraper,
}


class Command(BaseCommand):
    help = 'Price recipe canonical ingredients via a store search API.'

    def add_arguments(self, parser):
        parser.add_argument('--store', required=True, help='GroceryStore code, e.g. ROHLIK')
        parser.add_argument('--limit', type=int, default=None, help='Cap number of canonicals (testing)')
        parser.add_argument('--all-canonicals', action='store_true',
                            help='Price every CanonicalIngredient, not just recipe-referenced ones')
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, *args, **options):
        store = options['store']
        scraper_cls = SEARCH_SCRAPER_MAP.get(store)
        if scraper_cls is None:
            raise CommandError(
                f'No search scraper registered for {store}. '
                f'Available: {sorted(SEARCH_SCRAPER_MAP)}'
            )

        canonicals = self._target_canonicals(options['all_canonicals'])
        if options['limit']:
            canonicals = canonicals[:options['limit']]
        self.stdout.write(f'Targeting {len(canonicals)} canonical ingredients')

        scraper = scraper_cls(dry_run=options['dry_run'])
        result = scraper.run(canonicals)

        self.stdout.write(self.style.SUCCESS(
            f"{store} search scrape: canonicals={result['canonicals']} "
            f"priced={result['priced']} missed={result['missed']} "
            f"on_sale={result['on_sale']} dry_run={result['dry_run']}"
        ))

    def _target_canonicals(self, all_canonicals: bool):
        if all_canonicals:
            return list(
                CanonicalIngredient.objects.exclude(name_cs='', name='').order_by('slug')
            )

        slugs = set()
        names = set()
        recipes = CuratedRecipe.objects.filter(
            status=CuratedRecipe.Status.PUBLISHED
        ).values_list('ingredients', flat=True)
        for ingredients in recipes:
            for ing in ingredients or []:
                ref = (ing.get('canonical') or '').strip()
                if ref:
                    slugs.add(ref)
                    names.add(ref.lower())

        qs = CanonicalIngredient.objects.filter(slug__in=slugs)
        found = list(qs)
        # Defensive: some recipes may store the canonical *name* rather than slug.
        found_slugs = {c.slug for c in found}
        leftover = slugs - found_slugs
        if leftover:
            by_name = CanonicalIngredient.objects.filter(name__in=leftover)
            found.extend(c for c in by_name if c.slug not in found_slugs)

        self.stdout.write(
            f'Published recipes reference {len(slugs)} canonical keys; '
            f'resolved {len(found)} CanonicalIngredient rows'
        )
        return sorted(found, key=lambda c: c.slug)
