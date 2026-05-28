"""
Resolve StoreProduct.canonical_ingredient for rows where it's NULL.

Strategy:
1. Rule pass — normalized_name → IngredientAlias → CanonicalIngredient.
2. LLM fallback — batch up to N candidates per Gemini call; auto-write
   matches with confidence >= 0.85, dump the rest to a CSV review queue.

Idempotent. Re-run after edits to CanonicalIngredient/IngredientAlias.

Usage:
    python manage.py match_canonical_ingredients --dry-run
    python manage.py match_canonical_ingredients --batch=20 --csv=/tmp/unmatched.csv
"""
import csv
import logging
from typing import Dict, List, Optional

from django.core.management.base import BaseCommand
from django.db.models import Q

from diet_planner.llm_service import GeminiService
from diet_planner.models import CanonicalIngredient, IngredientAlias, StoreProduct
from diet_planner.scrapers.utils import normalize_ingredient_name

logger = logging.getLogger(__name__)


CONFIDENCE_AUTO_WRITE = 0.85


class Command(BaseCommand):
    help = 'Resolve StoreProduct.canonical_ingredient via rule + LLM matching.'

    def add_arguments(self, parser):
        parser.add_argument('--batch', type=int, default=20, help='LLM batch size')
        parser.add_argument('--limit', type=int, default=None, help='Max products to consider')
        parser.add_argument('--dry-run', action='store_true')
        parser.add_argument('--csv', type=str, default=None, help='Output CSV of low-confidence rows')
        parser.add_argument('--no-llm', action='store_true', help='Skip the LLM fallback pass')

    def handle(self, *args, **options):
        qs = StoreProduct.objects.filter(canonical_ingredient__isnull=True, is_active=True)
        if options['limit']:
            qs = qs[: options['limit']]

        products = list(qs)
        self.stdout.write(f'Considering {len(products)} unmatched StoreProduct rows')

        alias_index = self._build_alias_index()
        canonical_index = {ci.slug: ci for ci in CanonicalIngredient.objects.all()}

        # ─── Pass 1: rule-based matching ─────────────────────────────
        rule_matched: List[StoreProduct] = []
        unmatched: List[StoreProduct] = []
        for sp in products:
            canonical = self._rule_match(sp, alias_index, canonical_index)
            if canonical:
                if not options['dry_run']:
                    sp.canonical_ingredient = canonical
                    sp.save(update_fields=['canonical_ingredient'])
                rule_matched.append(sp)
            else:
                unmatched.append(sp)

        self.stdout.write(self.style.SUCCESS(
            f'Rule pass: matched {len(rule_matched)}/{len(products)}'
        ))

        # ─── Pass 2: LLM batch fallback ──────────────────────────────
        llm_matched = 0
        low_confidence_rows: List[Dict] = []
        if unmatched and not options['no_llm']:
            llm = GeminiService()
            candidates_payload = [
                {'slug': ci.slug, 'name': ci.name, 'category': ci.category}
                for ci in canonical_index.values()
            ]

            batch = options['batch']
            for i in range(0, len(unmatched), batch):
                chunk = unmatched[i:i + batch]
                names = [sp.normalized_name for sp in chunk]
                results = llm.match_canonical_ingredients_batch(names, candidates_payload)

                for sp, result in zip(chunk, results):
                    slug = (result or {}).get('canonical_slug')
                    confidence = float((result or {}).get('confidence', 0) or 0)
                    canonical = canonical_index.get(slug) if slug else None
                    if canonical and confidence >= CONFIDENCE_AUTO_WRITE:
                        if not options['dry_run']:
                            sp.canonical_ingredient = canonical
                            sp.save(update_fields=['canonical_ingredient'])
                        llm_matched += 1
                    else:
                        low_confidence_rows.append({
                            'store_product_id': sp.id,
                            'store': sp.store.code,
                            'normalized_name': sp.normalized_name,
                            'suggested_slug': slug or '',
                            'confidence': confidence,
                        })

        self.stdout.write(self.style.SUCCESS(f'LLM pass: matched {llm_matched}'))

        # ─── CSV review queue ────────────────────────────────────────
        if options['csv']:
            with open(options['csv'], 'w', encoding='utf-8', newline='') as fh:
                writer = csv.DictWriter(
                    fh,
                    fieldnames=['store_product_id', 'store', 'normalized_name',
                                'suggested_slug', 'confidence'],
                )
                writer.writeheader()
                writer.writerows(low_confidence_rows)
            self.stdout.write(f"Wrote {len(low_confidence_rows)} low-confidence rows to {options['csv']}")

        total = len(rule_matched) + llm_matched
        pct = (total / len(products) * 100) if products else 0.0
        self.stdout.write(self.style.SUCCESS(
            f'Done. Matched {total}/{len(products)} ({pct:.1f}%). '
            f'Low-confidence: {len(low_confidence_rows)}'
        ))

    # ─── Helpers ─────────────────────────────────────────────────────────

    def _build_alias_index(self) -> Dict[str, CanonicalIngredient]:
        return {
            alias.alias.lower().strip(): alias.canonical_ingredient
            for alias in IngredientAlias.objects.select_related('canonical_ingredient')
        }

    def _rule_match(
        self,
        sp: StoreProduct,
        alias_index: Dict[str, CanonicalIngredient],
        canonical_index: Dict[str, CanonicalIngredient],
    ) -> Optional[CanonicalIngredient]:
        name = normalize_ingredient_name(sp.normalized_name or sp.name or '')
        if not name:
            return None

        # Exact alias hit.
        alias_hit = alias_index.get(name)
        if alias_hit:
            return alias_hit

        # Longest-match-wins icontains on name_cs / name_sk.
        candidates = CanonicalIngredient.objects.filter(
            Q(name_cs__icontains=name) | Q(name_sk__icontains=name) | Q(name__icontains=name)
        )
        best = None
        best_len = 0
        for ci in candidates:
            for haystack in (ci.name_cs, ci.name_sk, ci.name):
                if not haystack:
                    continue
                if name in haystack.lower():
                    if len(haystack) > best_len:
                        best = ci
                        best_len = len(haystack)
        return best
