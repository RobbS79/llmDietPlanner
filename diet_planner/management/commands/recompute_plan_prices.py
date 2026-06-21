"""
Re-price existing DietaryPlan rows from the catalog without regenerating them.

Per-item `price_total` and the plan `total_price` are frozen into the plan at
creation time. When the pricing logic is corrected (e.g. the unit-conversion
fix in PriceResol._calc_packages_needed that stopped a gram requirement against
a kg-packaged product from inflating the pack count ~1000x), already-stored
plans keep the wrong numbers. This command re-runs the deterministic
`PriceResolver` over each plan's existing shopping-list items and rewrites the
prices in place — no LLM, no new meals, idempotent.

    python manage.py recompute_plan_prices --dry-run
    python manage.py recompute_plan_prices                  # heal all plans
    python manage.py recompute_plan_prices --plan-id 86
    python manage.py recompute_plan_prices --min-total 5000 # only inflated ones

See [[prod-pricing-fabrication-surface]] and the PriceResolver unit-conversion
regression in tests/test_catalog_constrained.py.
"""
from decimal import Decimal

from django.core.management.base import BaseCommand

from diet_planner.models import DietaryPlan
from diet_planner.services.price_resolver import PriceResolver


class Command(BaseCommand):
    help = "Re-price existing DietaryPlans from the catalog (no regeneration)."

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true',
                            help="Report new totals without saving.")
        parser.add_argument('--plan-id', type=int, default=None,
                            help="Re-price only this plan id.")
        parser.add_argument('--min-total', type=float, default=0.0,
                            help="Only touch plans whose current total_price is "
                                 ">= this (default 0 = all).")

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        plan_id = options['plan_id']
        min_total = Decimal(str(options['min_total']))

        plans = DietaryPlan.objects.select_related('dietary_goal').order_by('id')
        if plan_id is not None:
            plans = plans.filter(id=plan_id)
        if min_total > 0:
            plans = plans.filter(total_price__gte=min_total)

        changed = skipped = 0
        for plan in plans:
            payload = plan.shopping_list
            # Single-store plans store a bare list; cross-store plans store
            # {'items': [...], ...}. We only re-price the items.
            if isinstance(payload, dict):
                items = payload.get('items') or []
                container = 'dict'
            else:
                items = payload or []
                container = 'list'

            if not items:
                skipped += 1
                continue

            goal = plan.dietary_goal
            try:
                resolved = PriceResolver(goal).resolve_shopping_list(items)
            except Exception as exc:  # never let one bad plan abort the run
                self.stderr.write(self.style.WARNING(
                    f"[{plan.id}] re-price failed, left untouched: {exc}"
                ))
                skipped += 1
                continue

            new_total = sum(
                (Decimal(str(i['price_total'])) for i in resolved if i.get('price_total')),
                Decimal('0'),
            )
            old_total = plan.total_price or Decimal('0')

            self.stdout.write(
                f"[{plan.id}] {old_total} -> {new_total} {plan.currency} "
                f"({len(items)} items)"
            )

            if not dry_run:
                if container == 'dict':
                    payload['items'] = resolved
                    plan.shopping_list = payload
                else:
                    plan.shopping_list = resolved
                plan.total_price = new_total
                plan.save(update_fields=['shopping_list', 'total_price', 'updated_at'])
            changed += 1

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(
            f"{'[dry-run] ' if dry_run else ''}re-priced={changed} skipped={skipped}"
        ))
