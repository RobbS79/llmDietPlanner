"""
Audit the static price book (diet_planner/data/canonical_prices.yaml) for
suspect entries. Read-only, re-runnable gate — the price-side sibling of
audit_portion_plausibility.

It flags an entry three ways:

  (a) CATEGORY BAND — the per-kg / per-l / per-piece price falls outside a
      plausible shelf-price band for its inferred category. Bands are
      category-aware because a spice legitimately costs thousands of Kč/kg
      while a vegetable does not.

  (b) RATIO SANITY — a known ingredient family has an expected price ratio
      (e.g. chicken breast is ~1.3-1.8x chicken thigh, never 3x). Encoded
      families are documented in RATIO_FAMILIES below.

  (c) THIN SAMPLE — the median rests on <= THIN_SAMPLE_MAX catalog samples,
      so the number is statistically fragile regardless of plausibility.

Output is a ranked report, worst first, staples grouped first. Nothing is
mutated; corrections live in canonical_prices.proposed.yaml for human review.

    python manage.py audit_price_book
    python manage.py audit_price_book --book diet_planner/data/canonical_prices.proposed.yaml
    python manage.py audit_price_book --csv /tmp/price_audit.csv

The pure classification helpers (infer_category, per_display_price,
band_flag, ratio_flags) are importable and unit-tested in
diet_planner/tests/test_audit_price_book.py.
"""
import csv
from pathlib import Path

import yaml
from django.conf import settings
from django.core.management.base import BaseCommand

from diet_planner.services.piece_weights import load_piece_weights

THIN_SAMPLE_MAX = 2

# Staple slugs whose correctness drives ~90% of recipe cost. Reported first.
STAPLES = {
    'chicken-breast', 'chicken-thigh', 'beef', 'beef-tenderloin', 'pork',
    'ground-meat', 'ham', 'bacon', 'eggs', 'butter', 'semi-skimmed-milk',
    'whole-milk', 'cheese', 'greek-yogurt', 'white-yogurt', 'cottage-cheese',
    'potatoes', 'onion', 'carrots', 'tomatoes', 'apples', 'bananas',
    'bread-loaf', 'plain-flour', 'pasta', 'pasta-spaghetti', 'rice-basmati',
    'rice-jasmine', 'brown-rice', 'sugar', 'white-sugar', 'oats',
    'olive-oil', 'sunflower-oil', 'cabbage', 'cucumber', 'bell-pepper',
}

# Plausible shelf-price bands, Kč per kg (mass) / per l (volume). Category-aware.
CATEGORY_BANDS = {
    'vegetable':      (6, 300),
    'fruit':          (12, 700),      # imported / berries push the top end
    'dried_fruit':    (60, 700),
    'herb_fresh':     (60, 4000),     # sold in tiny packs -> high per-kg
    'poultry':        (50, 350),
    'red_meat':       (80, 900),      # mince to tenderloin
    'cured_meat':     (80, 700),
    'cheese':         (60, 1300),     # cottage to aged / goat
    'dairy':          (8, 260),       # milk, cream, yogurt
    'fat_butter':     (70, 1300),     # butter, ghee, lard, margarine
    'flour_grain':    (6, 220),       # flour, rice, oats, pasta, starch
    'legume':         (18, 450),
    'nuts_seeds':     (70, 2000),
    'oil':            (25, 800),
    'vinegar':        (12, 2600),     # balsamic top end
    'sugar_sweet':    (8, 450),
    'honey_syrup':    (70, 500),
    'spice':          (120, 22000),   # vanilla pods ~19000 Kč/kg
    'sauce_condiment': (15, 1200),
    'bakery':         (15, 260),
    'canned':         (12, 400),
    'nut_butter':     (100, 950),
    'alcohol':        (70, 1300),
    'other':          (4, 3000),
}
# Bands for count-priced items with no known piece weight, Kč per piece.
PIECE_BANDS = {
    'egg':          (3, 12),
    'leafy_piece':  (4, 70),
}

# Intra-family price-ratio expectations. Each: (numerator, denominator,
# lo, hi, note). Flag when book ratio is outside [lo, hi].
RATIO_FAMILIES = [
    ('chicken-breast', 'chicken-thigh', 1.2, 2.0,
     'breast is normally ~1.3-1.8x thigh'),
    ('beef-tenderloin', 'beef', 1.4, 3.2,
     'tenderloin is a premium cut vs generic beef'),
    ('white-sugar', 'sugar', 0.6, 1.5,
     'crystal vs generic sugar are near-identical'),
    ('whole-milk', 'semi-skimmed-milk', 0.85, 1.3,
     'whole vs semi-skimmed milk differ only by fat'),
    ('rice-basmati', 'brown-rice', 0.4, 2.5,
     'rice variants stay within a small band'),
]

# Keyword -> category. First matching keyword (substring of slug) wins; order
# matters (more specific first). A few slugs are pinned in _OVERRIDES.
_KEYWORDS = [
    ('tenderloin', 'red_meat'), ('beef', 'red_meat'), ('pork', 'red_meat'),
    ('ground-meat', 'red_meat'), ('lard', 'fat_butter'),
    ('chicken', 'poultry'),
    ('bacon', 'cured_meat'), ('ham', 'cured_meat'), ('salami', 'cured_meat'),
    ('sausage', 'cured_meat'), ('czech-sausage', 'cured_meat'),
    ('nut-butter', 'nut_butter'), ('peanut-butter', 'nut_butter'),
    ('almond-butter', 'nut_butter'), ('tahini', 'nut_butter'),
    ('butter', 'fat_butter'), ('ghee', 'fat_butter'), ('margarine', 'fat_butter'),
    ('cheese', 'cheese'), ('mozzarella', 'cheese'), ('feta', 'cheese'),
    ('milk', 'dairy'), ('cream', 'dairy'), ('yogurt', 'dairy'),
    ('buttermilk', 'dairy'),
    ('flour', 'flour_grain'), ('rice', 'flour_grain'), ('oats', 'flour_grain'),
    ('oat-flour', 'flour_grain'), ('pasta', 'flour_grain'), ('quinoa', 'flour_grain'),
    ('cornmeal', 'flour_grain'), ('cornstarch', 'flour_grain'),
    ('starch', 'flour_grain'), ('breadcrumbs', 'flour_grain'), ('noodles', 'flour_grain'),
    ('oil', 'oil'),
    ('vinegar', 'vinegar'),
    ('honey', 'honey_syrup'),
    ('sugar', 'sugar_sweet'),
    ('beans', 'legume'), ('lentils', 'legume'), ('chickpea', 'legume'),
    ('peas', 'legume'), ('edamame', 'legume'),
    ('nuts', 'nuts_seeds'), ('seeds', 'nuts_seeds'), ('almonds', 'nuts_seeds'),
    ('cashews', 'nuts_seeds'), ('walnuts', 'nuts_seeds'), ('pecans', 'nuts_seeds'),
    ('hazelnuts', 'nuts_seeds'), ('peanuts', 'nuts_seeds'), ('pine-nuts', 'nuts_seeds'),
    ('bread', 'bakery'), ('tortilla', 'bakery'), ('popcorn', 'bakery'),
    ('canned', 'canned'), ('sauce', 'sauce_condiment'), ('paste', 'sauce_condiment'),
    ('ketchup', 'sauce_condiment'), ('mustard', 'sauce_condiment'),
    ('salsa', 'sauce_condiment'), ('guacamole', 'sauce_condiment'),
    ('hummus', 'sauce_condiment'), ('pickles', 'sauce_condiment'),
    ('wine', 'alcohol'), ('rum', 'alcohol'),
    ('raisins', 'dried_fruit'), ('dates', 'dried_fruit'), ('cranberries', 'dried_fruit'),
]

# Slugs whose category the keyword heuristic gets wrong.
_OVERRIDES = {
    'basil': 'herb_fresh', 'parsley': 'herb_fresh', 'chives': 'herb_fresh',
    'dill': 'herb_fresh', 'mint': 'herb_fresh', 'coriander': 'herb_fresh',
    'rosemary': 'herb_fresh', 'thyme': 'herb_fresh', 'sage': 'herb_fresh',
    'arugula': 'vegetable', 'spinach': 'vegetable', 'kale': 'vegetable',
    'mixed-vegetables': 'vegetable',
    'bell-pepper': 'vegetable', 'chili-pepper': 'vegetable',  # fresh, not a spice
    'salt': 'other', 'sea-salt': 'other',  # commodity salt, not a costly spice
    'buttermilk': 'dairy',  # podmáslí — keyword 'butter' would misfile it
    'coconut-milk': 'canned', 'coconut-oil': 'oil', 'coconut-sugar': 'sugar_sweet',
    'coconut-flakes': 'other',
    'cocoa-powder': 'other', 'dark-chocolate': 'other', 'chocolate-chips': 'other',
    'protein-powder': 'other', 'nutritional-yeast': 'other', 'dry-yeast': 'other',
    'baking-powder': 'other', 'baking-soda': 'other',
    'applesauce': 'canned', 'pumpkin-puree': 'canned', 'tomato-sauce': 'canned',
    'chopped-tomatoes-canned': 'canned',
    'water': 'other', 'coffee': 'other', 'stock': 'sauce_condiment',
    'beef-stock': 'sauce_condiment', 'chicken-stock': 'sauce_condiment',
    'vegetable-stock': 'sauce_condiment',
    'tofu': 'legume', 'tempeh': 'legume',
    'greek-yogurt': 'dairy', 'sour-cream': 'dairy', 'cream-cheese': 'cheese',
    'goat-cheese': 'cheese', 'czech-soft-cheese': 'cheese',
    'cottage-cheese': 'dairy',
}

_SPICE_HINTS = (
    'pepper', 'paprika', 'cumin', 'curry', 'masala', 'turmeric', 'cinnamon',
    'nutmeg', 'clove', 'cardamom', 'coriander', 'ginger', 'allspice', 'bay',
    'oregano', 'cayenne', 'chili', 'caraway', 'poppy', 'vanilla', 'zaatar',
    'juniper', 'marjoram', 'herbs-de-provence', 'spice', 'seasoning', 'vegeta',
    'garlic-powder', 'onion-powder', 'grilling', 'saffron',
)


def infer_category(slug, name_cs=''):
    """Best-effort category for a canonical slug (see CATEGORY_BANDS keys)."""
    if slug in _OVERRIDES:
        return _OVERRIDES[slug]
    for hint in _SPICE_HINTS:
        if hint in slug:
            return 'spice'
    for kw, cat in _KEYWORDS:
        if kw in slug:
            return cat
    return None  # unknown -> caller treats as produce/other by unit


def per_display_price(entry, piece_grams=None):
    """Return (value, display_unit) in shelf terms: Kč/kg, Kč/l, or Kč/ks.

    Mass (g) -> Kč/kg (x1000); volume (ml) -> Kč/l (x1000). Count (ks) is
    converted to Kč/kg when a piece weight is known (so it hits the same
    category band as its weight-sold shelf form), else kept as Kč/ks.
    """
    ppu = float(entry.get('price_per_unit') or 0)
    unit = (entry.get('unit') or '').strip()
    if unit == 'g':
        return ppu * 1000.0, 'Kč/kg'
    if unit == 'ml':
        return ppu * 1000.0, 'Kč/l'
    if unit == 'ks':
        if piece_grams and piece_grams > 0:
            return ppu / (piece_grams / 1000.0), 'Kč/kg'
        return ppu, 'Kč/ks'
    return ppu, 'Kč/?'


def band_flag(category, value, display_unit, slug=''):
    """Return a reason string when `value` is outside the category band, else None."""
    if display_unit == 'Kč/ks':
        if slug == 'eggs':
            lo, hi = PIECE_BANDS['egg']
        else:
            lo, hi = PIECE_BANDS['leafy_piece']
        label = 'Kč/ks'
    else:
        band = CATEGORY_BANDS.get(category)
        if band is None:
            return None
        lo, hi = band
        label = display_unit
    if value < lo:
        return f"below {category or 'piece'} band ({value:.1f} < {lo} {label})"
    if value > hi:
        return f"above {category or 'piece'} band ({value:.1f} > {hi} {label})"
    return None


def ratio_flags(prices):
    """Yield (slug, reason) for family ratios that fall outside expectation."""
    for num, den, lo, hi, note in RATIO_FAMILIES:
        ne, de = prices.get(num), prices.get(den)
        if not ne or not de:
            continue
        # Compare in per-kg-equivalent terms (both usually same unit).
        nv, _ = per_display_price(ne)
        dv, _ = per_display_price(de)
        if dv <= 0:
            continue
        ratio = nv / dv
        if ratio < lo or ratio > hi:
            yield num, (f"ratio {num}/{den}={ratio:.2f} outside [{lo}, {hi}] "
                        f"({note})")


class Command(BaseCommand):
    help = "Audit the static price book for suspect entries (read-only)."

    def add_arguments(self, parser):
        default_book = str(
            Path(settings.BASE_DIR) / 'diet_planner' / 'data' / 'canonical_prices.yaml')
        parser.add_argument('--book', default=default_book,
                            help="Path to the price-book YAML to audit.")
        parser.add_argument('--csv', dest='csv_path', default=None,
                            help="Write per-entry flag rows to this CSV path.")

    def handle(self, *args, **options):
        book_path = Path(options['book'])
        data = yaml.safe_load(book_path.read_text(encoding='utf-8')) or {}
        prices = data.get('prices', {})
        weights = load_piece_weights()

        # Precompute ratio flags (keyed by slug).
        ratio_by_slug = {}
        for slug, reason in ratio_flags(prices):
            ratio_by_slug.setdefault(slug, []).append(reason)

        rows = []
        for slug, entry in prices.items():
            category = infer_category(slug, entry.get('name_cs', ''))
            value, disp = per_display_price(entry, weights.get(slug))
            reasons = []
            bf = band_flag(category, value, disp, slug)
            if bf:
                reasons.append(bf)
            reasons.extend(ratio_by_slug.get(slug, []))
            samples = entry.get('samples')
            if isinstance(samples, (int, float)) and samples <= THIN_SAMPLE_MAX:
                reasons.append(f"thin sample (n={int(samples)})")

            # Severity for ranking: how far outside the band (or thin-only).
            severity = 0.0
            band = CATEGORY_BANDS.get(category)
            if disp != 'Kč/ks' and band:
                lo, hi = band
                if value > hi:
                    severity = value / hi
                elif value < lo and value > 0:
                    severity = lo / value
            if ratio_by_slug.get(slug):
                severity = max(severity, 2.0)
            rows.append({
                'slug': slug,
                'name_cs': entry.get('name_cs', ''),
                'category': category or '(unknown)',
                'display': f"{value:.2f} {disp}",
                'samples': samples,
                'verified': entry.get('verified', ''),
                'source': entry.get('source', ''),
                'flags': '; '.join(reasons),
                'severity': round(severity, 2),
                '_flagged': bool(reasons),
                '_staple': slug in STAPLES,
            })

        flagged = [r for r in rows if r['_flagged']]
        self.stdout.write(f"Audited {len(rows)} entries from {book_path.name}.")
        self.stdout.write(f"Flagged {len(flagged)} "
                          f"({100 * len(flagged) / max(len(rows), 1):.0f}%).")

        def sort_key(r):
            return (not r['_staple'], -r['severity'], r['slug'])

        self.stdout.write("\n=== STAPLES (flagged, worst first) ===")
        for r in sorted([r for r in flagged if r['_staple']], key=sort_key):
            self.stdout.write(
                f"  [{r['severity']:>5.2f}] {r['slug']:<20} {r['display']:>16}"
                f"  {r['flags']}")

        self.stdout.write("\n=== NON-STAPLES (flagged, worst first) ===")
        for r in sorted([r for r in flagged if not r['_staple']], key=sort_key):
            self.stdout.write(
                f"  [{r['severity']:>5.2f}] {r['slug']:<20} {r['display']:>16}"
                f"  {r['flags']}")

        if options['csv_path']:
            fields = ['slug', 'name_cs', 'category', 'display', 'samples',
                      'verified', 'source', 'severity', 'flags']
            with open(options['csv_path'], 'w', newline='', encoding='utf-8') as fh:
                w = csv.DictWriter(fh, fieldnames=fields, extrasaction='ignore')
                w.writeheader()
                w.writerows(sorted(rows, key=sort_key))
            self.stdout.write(f"\nWrote {len(rows)} rows to {options['csv_path']}.")
