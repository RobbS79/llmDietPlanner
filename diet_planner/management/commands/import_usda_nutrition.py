"""Build the per-canonical nutrition table from USDA SR Legacy (public domain).

    python manage.py import_usda_nutrition --sr-legacy /path/FoodData_Central_sr_legacy_food_json_2018-04.json \
        --report /path/nutrition_review.csv --write-yaml

Matches each canonical (English `name`, or the entry's `usda_query` hint) to
an SR Legacy food, extracts kcal/protein/carbs/fat per 100 g, density from a
tbsp/tsp/cup portion and piece/unit weights from medium/each/clove/slice
portions, and writes a `nutrition:` block into data/canonical_ingredients.yaml
for rows with confidence >= MIN_CONFIDENCE. Rows already tagged `manual:` /
`frida:` are never overwritten; hand-set piece_weight_g / unit_weights win over
USDA portions; unmatched rows get `{source: needs_review}`. Idempotent.
The YAML's leading comment block is preserved on write.
"""
import csv
import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml
from django.core.management.base import BaseCommand, CommandError
from django.utils.text import slugify

NUTRIENT_IDS = {1008: 'kcal', 1003: 'protein', 1005: 'carbs', 1004: 'fat'}
MIN_CONFIDENCE = 0.6
USDA_ML = {'tbsp': 15.0, 'tsp': 5.0, 'cup': 240.0}
PIECE_MODIFIERS = ('medium', 'each', 'whole', 'large', 'piece')
UNIT_MODIFIERS = {'clove': 'stroužek', 'slice': 'plátek', 'bunch': 'svazek', 'sprig': 'snítka', 'leaf': 'lístek'}
BAD_WORDS = ('breaded', 'batter', 'cooked', 'roasted', 'fried', 'boiled', 'braised', 'baked', 'canned', 'frozen', 'dried',
             'dehydrated', 'juice', 'babyfood', 'fast foods', 'restaurant')
DEFAULT_FILE = Path(__file__).resolve().parents[2] / 'data' / 'canonical_ingredients.yaml'
MANUAL_PREFIXES = ('manual:', 'frida:')
REPORT_COLUMNS = ['slug', 'name_cs', 'status', 'usda_description', 'fdc_id', 'confidence',
                  'kcal', 'protein', 'carbs', 'fat', 'density', 'piece_weight_g']


# Description tokens that exclude a food outright (restaurant/branded/processed).
EXCLUDE_TOKENS = {'restaurant', 'fast', 'school', 'candies', 'candy', 'snacks', 'snack', 'babyfood',
                  'formula', 'supplement', 'applebee', 'mcdonald', 'kfc', 'burger', 'pizza', 'taco',
                  'campbell', 'kraft', 'nestle', 'hershey', 'prepared', 'mix'}
# Words that mark a different product when the query lacks them (walnuts -> walnut oil).
OTHER_PRODUCT_WORDS = ('oil', 'vinegar', 'bread', 'cake', 'sauce', 'dressing', 'juice', 'chocolate',
                       'soup', 'pudding', 'cookie', 'cereal', 'roll', 'bar', 'butter', 'flavored',
                       'flavor', 'giblet', 'liver', 'heart', 'gizzard', 'neck', 'feet',
                       'tongue', 'kidney', 'deli', 'prepackaged', 'rotisserie', 'seasoned', 'solution')
# First description segments that only name a class ("Spices, paprika"): the head is then
# segment 0 + segment 1.
CLASS_WORDS = {'spice', 'fish', 'cheese', 'nut', 'oil', 'beef', 'pork', 'chicken', 'milk', 'pasta', 'rice',
               'flour', 'vinegar', 'herb', 'seed', 'bean', 'wheat', 'lamb', 'bread', 'soup', 'sauce',
               'beverage', 'alcoholic beverage', 'crustacean', 'mollusk', 'game meat', 'veal', 'turkey',
               'sugar', 'sweetener', 'cream', 'yogurt', 'tomato product', 'leavening agent',
               'pepper', 'onion', 'lettuce', 'cabbage', 'squash', 'mushroom', 'oat', 'cereal', 'sausage'}
# Category -> state words that are fine (not penalized) and earn a small preference bonus.
STATE_OK = {
    'spices': ('dried', 'ground'),
    'grains': ('dry', 'uncooked', 'raw', 'enriched', 'unenriched'),
    'legumes': ('dry', 'uncooked', 'raw', 'mature seeds'),
    'baking': ('dry', 'uncooked', 'raw', 'enriched', 'unenriched'),
    'oils': ('salad or cooking',),
    'dairy': ('whole', 'plain', 'fluid'),
    'nuts': ('dried', 'raw'),
}
# Phrase/word synonyms folded on both sides before tokenizing.
SYNONYMS = [
    (r'\bbreadcrumbs?\b', 'bread crumbs'), (r'\byoghurt\b', 'yogurt'), (r'\bchill?ie?s?\b', 'chili'),
    (r'\bchile\b', 'chili'), (r'\bcilantro\b', 'coriander'), (r'\bcourgettes?\b', 'zucchini'),
    (r'\baubergines?\b', 'eggplant'), (r'\b(green|spring) onions?\b', 'scallion'),
    (r'\bcapsicums?\b', 'sweet pepper'), (r'\bbell peppers?\b', 'sweet pepper'),
    (r'\bbeetroots?\b', 'beets'), (r'\bhome-prepared\b', 'homemade'), (r'\bfilberts?\b', 'hazelnuts'), (r'\bmangetout\b', 'snow peas'), (r'\bmince[d]?\b', 'ground'), (r'\bfillets?\b', ''),
    (r'\bplain flour\b', 'wheat flour all-purpose'), (r'\bwhite yogurt\b', 'plain yogurt'),
    (r'\bpasta (spaghetti|penne|fusilli|farfalle|tagliatelle|linguine|rigatoni|macaroni)\b', 'pasta'),
    (r'\b(coconut flakes|desiccated coconut|shredded coconut)\b', 'coconut dried desiccated'),
]
# Class words that only name a category; other class words (cheese, milk, beef…) are foods
# themselves and count against a query that lacks them ("Cheese, cream" is not "cream").
PURE_CLASSES = {'spice', 'nut', 'seed', 'fish', 'beverage', 'alcoholic beverage', 'game meat',
                'crustacean', 'mollusk', 'herb', 'bean', 'leavening agent', 'tomato product',
                'sweetener', 'sugar', 'soup', 'sauce'}
# Qualifier segments skipped when picking a class head ("Chicken, broilers or fryers, breast").
FILLER_TOKENS = {'broiler', 'fryer', 'fresh', 'roasting', 'young', 'domesticated', 'all', 'grade',
                 'distilled', 'variety', 'meat', 'and', 'product'}
COLORS = {'white', 'red', 'green', 'yellow', 'black', 'brown', 'orange', 'purple'}
# Modifiers that count half in the overlap and cannot alone satisfy the head rule.
WEAK_TOKENS = {'white', 'red', 'green', 'fresh', 'smoked', 'sea', 'plain', 'whole', 'flake', 'meat',
               'dried', 'powder', 'leaf', 'fine', 'coarse', 'organic', 'light', 'dark'}
# Class head -> entry categories it may serve; any other category is penalized
# (butter must not become "Nuts, almond butter", smoked meat not "Nuts, coconut meat").
CLASS_CATEGORIES = {
    'nut': {'nuts', 'baking', 'other', 'oils'}, 'seed': {'nuts', 'baking', 'spices', 'other'},
    'fish': {'fish', 'canned', 'frozen'}, 'crustacean': {'fish', 'frozen'}, 'mollusk': {'fish', 'frozen'},
    'beef': {'meat', 'canned', 'frozen', 'other'}, 'pork': {'meat', 'canned', 'frozen', 'other'},
    'chicken': {'meat', 'frozen', 'other'}, 'lamb': {'meat'}, 'veal': {'meat'}, 'turkey': {'meat'},
    'game meat': {'meat'}, 'sausage': {'meat'},
    'cheese': {'dairy', 'other'}, 'milk': {'dairy', 'beverages', 'other'}, 'cream': {'dairy', 'other'},
    'yogurt': {'dairy', 'other'}, 'spice': {'spices', 'condiments', 'other'},
}


_IRREGULAR = {'leaves': 'leaf', 'halves': 'half', 'loaves': 'loaf'}


def _singular(t: str) -> str:
    """Crude plural fold so 'onion' meets 'Onions' and 'tomato' meets 'Tomatoes'."""
    if t in _IRREGULAR:
        return _IRREGULAR[t]
    if t.endswith('ies') and len(t) > 4:
        return t[:-3] + 'y'
    if t.endswith(('oes', 'ches', 'shes', 'sses')):
        return t[:-2]
    if t.endswith('s') and not t.endswith(('ss', 'us')) and len(t) > 3:
        return t[:-1]
    return t


def _norm(s: str) -> str:
    s = (s or '').lower()
    for pat, rep in SYNONYMS:
        s = re.sub(pat, rep, s)
    return s


def _tokens(s: str) -> set:
    return {_singular(t) for t in re.split(r'[^a-z]+', _norm(s)) if len(t) > 2}


def _head(desc: str) -> Tuple[set, Optional[str]]:
    """(head tokens, class word): segment 0, plus segment 1 when segment 0 is a class word."""
    segs = [s.strip() for s in desc.lower().split(',')]
    seg0 = ' '.join(_singular(w) for w in re.split(r'[^a-z]+', segs[0]) if w)
    head = _tokens(segs[0])
    rest = [s for s in segs[1:] if not _tokens(s) <= FILLER_TOKENS]
    if seg0 in CLASS_WORDS and rest:
        return head | _tokens(rest[0]), seg0
    return head, None


def _excluded(desc_raw: str, have: set, want: set) -> bool:
    if "'" in desc_raw and 'usda' not in desc_raw.lower():   # "CARRABBA'S", not "USDA's program"
        return True
    first = desc_raw.split(',')[0].strip()
    if len(first) > 3 and first.isupper():                  # "SMART SOUP, …" brand head
        return True
    if any(len(seg.strip()) > 3 and seg.strip().isupper() for seg in desc_raw.split(',')[1:]):
        return True                                          # "…, CHOBANI" brand qualifier
    return any(t in have and t not in want for t in EXCLUDE_TOKENS)


@lru_cache(maxsize=20000)
def _profile(desc_raw: str) -> Tuple[str, frozenset, frozenset, Optional[str]]:
    """(normalized description, all tokens, head tokens, class word), cached per description."""
    desc = _norm(desc_raw)
    head, klass = _head(desc)
    return desc, frozenset(_tokens(desc)), frozenset(head), klass


def _score(want: set, food: dict, category: str) -> float:
    desc_raw = food.get('description') or ''
    desc, have, head, klass = _profile(desc_raw)
    strong = want - WEAK_TOKENS or want
    if not (strong & head) or _excluded(desc_raw, have, want):
        return 0.0
    weight = {t: (0.5 if t in WEAK_TOKENS and t not in strong else 1.0) for t in want}
    score = sum(weight[t] for t in want & have) / sum(weight.values())
    if strong <= head:
        score += 0.25
    class_tokens = set(klass.split()) if klass in PURE_CLASSES else set()
    score -= 0.1 * len(head - want - class_tokens)          # "Milk, buttermilk" is not "whole milk"
    want_colors, head_colors = want & COLORS, head & COLORS
    if want_colors and head_colors and not want_colors & head_colors:
        score -= 0.5                                          # white wine vinegar != red wine vinegar
    if klass and category and klass in CLASS_CATEGORIES and category not in CLASS_CATEGORIES[klass]:
        score -= 0.5
    if category in ('meat', 'fish') and 'ground' in have and 'ground' not in want:
        score -= 0.3
    if category in ('meat', 'fish') and 'skin' in have and 'skin' not in want:
        score -= 0.2                                          # chicken breast = meat only
    ok_states = STATE_OK.get(category, ())
    if category in ('meat', 'fish', 'eggs', 'vegetables', 'fruits', 'other', '') and 'raw' in have:
        score += 0.15
    if any(re.search(rf'\b{s}\b', desc) for s in ok_states):
        score += 0.1
    for bad in BAD_WORDS:
        if bad in want or any(re.fullmatch(s, bad) for s in ok_states):
            continue
        if (bad == 'canned' and category == 'canned') or (bad == 'frozen' and category == 'frozen'):
            continue
        if re.search(rf'\b{bad}\b', desc):
            score -= 0.5
    for w in OTHER_PRODUCT_WORDS:
        if w not in want and w in have and w != klass:      # "Soup, stock, chicken" is a stock
            score -= 0.6 if w in head else 0.3
    if 'with' in desc.split() and 'with' not in want and not re.search(
            r'\bwith(out)? (added|salt|skin|bone)', desc):
        score -= 0.3
    if re.search(r'\((alaska native|navajo|hopi|apache|shoshone|[^)]*indians?)\)', desc):
        score -= 0.4                                          # regional/traditional variants
    score -= 0.01 * max(0, len(have) - len(want))
    return score


def best_match(name: str, foods: List[dict], *, category: str = '',
               query: Optional[str] = None) -> Tuple[Optional[dict], float]:
    """Best SR Legacy food for a canonical name (or `query` hint) and a 0..1 confidence.

    A food qualifies only when a query token is in its HEAD (see `_head`); branded,
    restaurant, snack and prepared foods are excluded. Score = share of query tokens
    in the description, +0.25 when the head holds them all, category-aware state
    bonuses/penalties, -0.3 for other-product words (oil, sauce, bread…), and a
    small length penalty. Ties go to the lower fdcId.
    """
    want = _tokens(query or name)
    if not want:
        return None, 0.0
    best, best_key = None, (0.0, 0)
    for f in foods:
        s = _score(want, f, category)
        key = (s, -int(f.get('fdcId') or 0))
        if s > 0 and (best is None or key > best_key):
            best, best_key = f, key
    return (best, round(min(best_key[0], 1.0), 2)) if best is not None else (None, 0.0)


def nutrients_of(food: dict) -> Dict[str, float]:
    out = {}
    for fn in food.get('foodNutrients') or []:
        nid = (fn.get('nutrient') or {}).get('id')
        if nid in NUTRIENT_IDS:
            out[NUTRIENT_IDS[nid]] = float(fn.get('amount') or 0.0)
    return out


def _portions(food: dict):
    """Yield (grams per 1 measure, unit name, modifier) for every portion with a weight."""
    for p in food.get('foodPortions') or []:
        g = p.get('gramWeight')
        amt = p.get('amount') or 1.0
        unit = ((p.get('measureUnit') or {}).get('name') or '').lower()
        mod = (p.get('modifier') or '').lower()
        if g:
            yield float(g) / float(amt), unit, mod


def derive_density(food: dict) -> Optional[float]:
    """g/ml from the first tbsp/tsp/cup portion (USDA cup = 240 ml), else None."""
    for g, unit, mod in _portions(food):
        key = unit if unit in USDA_ML else next((u for u in USDA_ML if re.search(rf'\b{u}\b', mod)), None)
        if key:
            return round(g / USDA_ML[key], 3)
    return None


def derive_piece_weights(food: dict) -> Dict[str, Any]:
    piece = None
    unit_weights: Dict[str, float] = {}
    for g, unit, mod in _portions(food):
        words = set(re.split(r'[^a-z]+', f'{unit} {mod}'))
        for usda_word, cz in UNIT_MODIFIERS.items():
            if usda_word in words and cz not in unit_weights:
                unit_weights[cz] = round(g, 1)
        if piece is None and any(w in words for w in PIECE_MODIFIERS):
            piece = round(g, 1)
    return {'piece_weight_g': piece, 'unit_weights': unit_weights}


def _split_header(text: str) -> Tuple[str, str]:
    """(leading comment/blank lines, rest) so a rewrite keeps the file header."""
    lines = text.splitlines(keepends=True)
    i = 0
    while i < len(lines) and (lines[i].startswith('#') or not lines[i].strip()):
        i += 1
    return ''.join(lines[:i]), ''.join(lines[i:])


def _hand_set(existing: dict) -> Dict[str, Any]:
    """Hand-maintained piece/unit weights from an existing nutrition block."""
    kept = {}
    if existing.get('piece_weight_g') is not None:
        kept['piece_weight_g'] = existing['piece_weight_g']
    if existing.get('unit_weights'):
        kept['unit_weights'] = dict(existing['unit_weights'])
    return kept


class Command(BaseCommand):
    help = 'Match canonical ingredients to USDA SR Legacy foods and build their nutrition blocks.'

    def add_arguments(self, parser):
        parser.add_argument('--sr-legacy', required=True, help='Path to the SR Legacy food JSON file.')
        parser.add_argument('--yaml', default=str(DEFAULT_FILE), help='Canonical ingredients YAML.')
        parser.add_argument('--report', help='Write a review CSV to this path.')
        parser.add_argument('--write-yaml', action='store_true', help='Write nutrition blocks back into the YAML.')

    def handle(self, *args, **opts):
        sr_path = Path(opts['sr_legacy'])
        yaml_path = Path(opts['yaml'])
        if not sr_path.exists():
            raise CommandError(f'SR Legacy file not found: {sr_path}')
        if not yaml_path.exists():
            raise CommandError(f'YAML not found: {yaml_path}')

        foods = json.loads(sr_path.read_text(encoding='utf-8')).get('SRLegacyFoods') or []
        header, body = _split_header(yaml_path.read_text(encoding='utf-8'))
        entries = yaml.safe_load(body) or []
        if not isinstance(entries, list):
            raise CommandError(f'{yaml_path} must contain a list of entries')

        counts = {'matched': 0, 'kept_manual': 0, 'needs_review': 0}
        rows = []
        for e in entries:
            name = e.get('name') or ''
            slug = e.get('slug') or slugify(name)
            existing = e.get('nutrition') or {}
            row = {c: '' for c in REPORT_COLUMNS}
            row.update(slug=slug, name_cs=e.get('name_cs') or '')

            source = str(existing.get('source') or '')
            if source.startswith(MANUAL_PREFIXES):
                counts['kept_manual'] += 1
                row['status'] = 'kept_manual'
                rows.append(row)
                continue

            match, conf = best_match(name, foods, category=e.get('category') or '', query=e.get('usda_query'))
            nutr = nutrients_of(match) if match is not None else {}
            if match is not None:
                row.update(usda_description=match.get('description', ''), fdc_id=match.get('fdcId', ''),
                           confidence=conf)
            hand = _hand_set(existing)

            if match is None or conf < MIN_CONFIDENCE or any(k not in nutr for k in ('kcal', 'protein', 'carbs', 'fat')):
                counts['needs_review'] += 1
                row['status'] = 'needs_review'
                rows.append(row)
                e['nutrition'] = {**hand, 'source': 'needs_review'}
                continue

            block: Dict[str, Any] = {k: nutr[k] for k in ('kcal', 'protein', 'carbs', 'fat')}
            density = derive_density(match)
            if density is not None:
                block['density'] = density
            pw = derive_piece_weights(match)
            piece = hand.get('piece_weight_g', pw['piece_weight_g'])
            if piece is not None:
                block['piece_weight_g'] = piece
            unit_weights = {**pw['unit_weights'], **hand.get('unit_weights', {})}
            if unit_weights:
                block['unit_weights'] = unit_weights
            block['source'] = f"usda:{match['fdcId']}"
            e['nutrition'] = block

            counts['matched'] += 1
            row.update(status='matched', density=block.get('density', ''),
                       piece_weight_g=block.get('piece_weight_g', ''),
                       **{k: block[k] for k in ('kcal', 'protein', 'carbs', 'fat')})
            rows.append(row)

        if opts.get('report'):
            with open(opts['report'], 'w', newline='', encoding='utf-8') as fh:
                w = csv.DictWriter(fh, fieldnames=REPORT_COLUMNS)
                w.writeheader()
                w.writerows(rows)

        if opts.get('write_yaml'):
            yaml_path.write_text(
                header + yaml.safe_dump(entries, allow_unicode=True, sort_keys=False, width=100),
                encoding='utf-8')

        self.stdout.write(
            f"matched={counts['matched']} kept_manual={counts['kept_manual']} "
            f"needs_review={counts['needs_review']} total={len(entries)}")
