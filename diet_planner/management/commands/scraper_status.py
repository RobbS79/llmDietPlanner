"""
Management command: shows scraper health status for all stores.

Usage:
    python manage.py scraper_status
    python manage.py scraper_status --json
"""
from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db.models import Count, Sum, Max
from django.utils import timezone

from diet_planner.models import GroceryStore, PriceRecord, ScrapeRun


class Command(BaseCommand):
    help = 'Display scraper health status for all stores'

    def add_arguments(self, parser):
        parser.add_argument('--json', action='store_true', help='Output as JSON')

    def handle(self, *args, **options):
        now = timezone.now()
        week_ago = now - timedelta(days=7)
        stores = GroceryStore.objects.filter(is_active=True).order_by('chain', 'country')

        rows = []
        for store in stores:
            # Latest successful scrape
            latest_run = ScrapeRun.objects.filter(
                store=store, status='COMPLETED'
            ).order_by('-started_at').first()

            # Active priced records
            active_count = PriceRecord.objects.current().filter(
                store_product__store=store,
                store_product__is_active=True,
                price__gt=0,
            ).count()

            # PriceRecord uses valid_until directly; derive fresh/stale/expired
            # by comparing scraped_at to the store's TTL window.
            ttl_hours = store.default_price_ttl_hours or 168
            fresh_cutoff = now - timedelta(hours=ttl_hours / 2)
            fresh = PriceRecord.objects.current().filter(
                store_product__store=store, scraped_at__gte=fresh_cutoff,
            ).count()
            stale = max(0, active_count - fresh)
            expired = PriceRecord.objects.filter(
                store_product__store=store,
                valid_until__lte=now,
            ).count()

            # Weekly cost
            weekly_cost = ScrapeRun.objects.filter(
                store=store, started_at__gte=week_ago,
            ).aggregate(total=Sum('llm_cost_usd'))['total'] or Decimal('0')

            # Weekly runs
            weekly_runs = ScrapeRun.objects.filter(
                store=store, started_at__gte=week_ago,
            ).count()

            # Last scrape age
            if latest_run:
                age = now - latest_run.started_at
                age_str = f"{age.total_seconds() / 3600:.0f}h ago"
                last_products = latest_run.products_found
            else:
                age_str = "never"
                last_products = 0
                age = None

            # Health status
            ttl = store.default_price_ttl_hours
            if age is None:
                health = "NEVER"
            elif age.total_seconds() / 3600 > ttl:
                health = "STALE"
            elif age.total_seconds() / 3600 > ttl * 0.75:
                health = "WARN"
            else:
                health = "OK"

            rows.append({
                'code': store.code,
                'chain': store.chain,
                'country': store.country,
                'health': health,
                'last_scrape': age_str,
                'last_products': last_products,
                'active_offers': active_count,
                'fresh': fresh,
                'stale': stale,
                'expired': expired,
                'weekly_runs': weekly_runs,
                'weekly_cost': f"${weekly_cost:.4f}",
            })

        if options['json']:
            import json
            self.stdout.write(json.dumps(rows, indent=2))
            return

        # Table output
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("=== SCRAPER STATUS ==="))
        self.stdout.write("")

        header = f"{'Store':<15} {'Health':<7} {'Last Scrape':<12} {'Products':<10} {'Active':<8} {'F/S/E':<12} {'Runs/wk':<8} {'Cost/wk':<10}"
        self.stdout.write(header)
        self.stdout.write("-" * len(header))

        for r in rows:
            health_style = {
                'OK': self.style.SUCCESS,
                'WARN': self.style.WARNING,
                'STALE': self.style.ERROR,
                'NEVER': self.style.ERROR,
            }.get(r['health'], self.style.WARNING)

            health_text = health_style(r['health'].ljust(7))
            fse = f"{r['fresh']}/{r['stale']}/{r['expired']}"
            self.stdout.write(
                f"{r['code']:<15} "
                f"{health_text} "
                f"{r['last_scrape']:<12} "
                f"{str(r['last_products']):<10} "
                f"{str(r['active_offers']):<8} "
                f"{fse:<12} "
                f"{str(r['weekly_runs']):<8} "
                f"{r['weekly_cost']:<10}"
            )

        self.stdout.write("")

        # Summary
        total_active = sum(r['active_offers'] for r in rows)
        total_cost = sum(float(r['weekly_cost'].replace('$', '')) for r in rows)
        stale_stores = [r['code'] for r in rows if r['health'] in ('STALE', 'NEVER')]

        self.stdout.write(f"Total active offers: {total_active}")
        self.stdout.write(f"Weekly LLM cost: ${total_cost:.4f}")
        if stale_stores:
            self.stdout.write(self.style.ERROR(f"Stale/never scraped: {', '.join(stale_stores)}"))
        else:
            self.stdout.write(self.style.SUCCESS("All stores healthy"))
        self.stdout.write("")
