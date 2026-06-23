"""
Generate the static price book from current catalog data.

We no longer call individual shops at serve time (see
[[pricing-pivot-static-book]]). Instead we keep a maintainable per-ingredient
reference price (CZK per base unit) + a typical pack size, and estimate the
whole-pack checkout cost from it. This command seeds / refreshes that book from
the catalog using the MEDIAN price across products mapped to each canonical
ingredient — the median deliberately ignores premium SKUs ("Farma rodiny
Němcovy", "Marks & Spencer") that inflated totals.

Output is a YAML file the product owner then maintains by hand (inflation,
corrections) — re-running this overwrites it, so run it only to re-seed.

    python manage.py build_price_book                 # write the repo file
    python manage.py build_price_book --stdout        # print YAML only
    python manage.py build_price_book --min-samples 1

The per-recipe pricing engine reads the committed YAML (via _load_book), never the DB.
"""
import statistics
from pathlib import Path

import yaml
from django.conf import settings
from django.core.management.base import BaseCommand

from diet_planner.models import CanonicalIngredient, PriceRecord, PriceSourceType
from diet_planner.services.piece_weights import load_piece_weights
from diet_planner.services.units import to_base

# Where the committed book lives; _load_book reads this same path.
BOOK_PATH = Path(settings.BASE_DIR) / 'diet_planner' / 'data' / 'canonical_prices.yaml'

# Canonical base code per measurement dimension.
_DIM_BASE = {'mass': 'g', 'volume': 'ml', 'count': 'ks'}


class Command(BaseCommand):
    help = "Seed the static price book (canonical_prices.yaml) from catalog medians."

    def add_arguments(self, parser):
        # dest must NOT be 'stdout' — BaseCommand.execute() wraps any truthy
        # options['stdout'] as an OutputWrapper, which breaks self.stdout.write.
        parser.add_argument('--stdout', action='store_true', dest='emit_stdout',
                            help="Print YAML to stdout instead of writing the file.")
        parser.add_argument('--min-samples', type=int, default=1,
                            help="Minimum mapped products required to include a "
                                 "canonical (default 1).")

    def handle(self, *args, **options):
        min_samples = options['min_samples']
        piece_weights = load_piece_weights()  # canonical slug -> grams/piece

        # Current regular-price records, joined to their product + canonical.
        records = (
            PriceRecord.objects.current()
            .filter(
                source_type=PriceSourceType.STORE_REGULAR,
                price__gt=0,
                store_product__is_active=True,
                store_product__canonical_ingredient__isnull=False,
            )
            .select_related('store_product', 'store_product__canonical_ingredient')
        )

        # canonical_id -> list of (price_per_base, pack_base, dim)
        samples: dict = {}
        canon: dict = {}
        for r in records:
            sp = r.store_product
            c = sp.canonical_ingredient
            if not sp.package_size or sp.package_size <= 0 or not sp.package_unit:
                continue
            pack_base, dim = to_base(float(sp.package_size), sp.package_unit)
            if dim is None or pack_base <= 0:
                continue
            # Only mix products that measure the same way the canonical does.
            _, canon_dim = to_base(1.0, c.default_unit)
            if canon_dim is not None and canon_dim != dim:
                # Piece<->weight bridge: a counted canonical ("2 ks cibule")
                # that the store sells by weight ("síť 1 kg"). With a typical
                # piece weight we convert the real catalog price into a
                # per-piece price instead of discarding it. No weight → we must
                # not invent a price, so fall through to skip.
                grams = piece_weights.get(c.slug)
                if canon_dim == 'count' and dim == 'mass' and grams:
                    price_per_piece = (float(r.price) / pack_base) * grams
                    pack_pieces = pack_base / grams
                    samples.setdefault(c.id, []).append(
                        (price_per_piece, pack_pieces, canon_dim)
                    )
                    canon[c.id] = c
                continue
            samples.setdefault(c.id, []).append(
                (float(r.price) / pack_base, pack_base, dim)
            )
            canon[c.id] = c

        book = {}
        for cid, rows in samples.items():
            if len(rows) < min_samples:
                continue
            c = canon[cid]
            dim = rows[0][2]
            price_per_unit = round(statistics.median(p for p, _, _ in rows), 4)
            pack = round(statistics.median(pk for _, pk, _ in rows), 1)
            book[c.slug] = {
                'name_cs': c.name_cs or c.name,
                'unit': _DIM_BASE.get(dim, 'g'),
                'price_per_unit': price_per_unit,   # CZK per base unit
                'pack': pack,                        # typical pack size in base unit
                'samples': len(rows),
            }

        payload = {
            'currency': 'CZK',
            'note': 'Auto-seeded from catalog medians; maintain by hand for inflation.',
            'prices': dict(sorted(book.items())),
        }
        text = yaml.safe_dump(payload, allow_unicode=True, sort_keys=False, width=100)

        if options['emit_stdout']:
            self.stdout.write(text)
        else:
            BOOK_PATH.parent.mkdir(parents=True, exist_ok=True)
            BOOK_PATH.write_text(text, encoding='utf-8')
            self.stdout.write(self.style.SUCCESS(
                f"Wrote {len(book)} ingredients to {BOOK_PATH}"
            ))
        # Always echo a coverage line to stderr-style summary.
        self.stdout.write(self.style.SUCCESS(
            f"price_book: {len(book)} canonicals (from {len(samples)} with samples)"
        ))
