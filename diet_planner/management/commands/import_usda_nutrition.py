"""Build the per-canonical nutrition table from USDA SR Legacy (public domain).

    python manage.py import_usda_nutrition --sr-legacy /path/FoodData_Central_sr_legacy_food_json_2018-04.json \
        --report /path/nutrition_review.csv --write-yaml

Matches each canonical (English `name`, or the entry's `usda_query` hint) to
an SR Legacy food, extracts kcal/protein/carbs/fat per 100 g, density from a
tbsp/tsp/cup portion and piece/unit weights from medium/each/clove/slice
portions, and writes a `nutrition:` block into data/canonical_ingredients.yaml
for rows with confidence >= MIN_CONFIDENCE. Rows already tagged `manual:` /
`frida:` are never overwritten; hand-set piece_weight_g / unit_weights win over
USDA portions; unmatched rows are left untouched (the --report CSV is the
worklist). Idempotent.

The YAML is edited as TEXT, in place (see `_write_blocks`): only `nutrition:`
blocks are replaced or appended, so comments, flow-style aliases and key order
elsewhere in the file survive byte-for-byte.
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
# Portion modifiers that give "1 ks", best first (medium beats large for strawberries).
PIECE_MODIFIERS = ('medium', 'each', 'piece', 'whole', 'large')
# USDA count words -> Czech count units stored in unit_weights.
UNIT_MODIFIERS = {'clove': 'stroužek', 'slice': 'plátek', 'bunch': 'svazek', 'sprig': 'snítka', 'leaf': 'lístek'}
# A portion measured in these is a volume/weight, never a piece ("oz (23 whole kernels)").
MEASURE_WORDS = {'cup', 'tbsp', 'tsp', 'oz', 'lb', 'ml', 'fl'}
# Cup qualifiers that describe a cut/packed form, whose weight is not the liquid density.
CUP_FORM_WORDS = ('chopped', 'shredded', 'sliced', 'pureed', 'packed', 'leaves', 'whole', 'slivered',
                  'diced', 'halves', 'crumbled', 'grated', 'cubes', 'mashed', 'pieces', 'flaked', 'ground')
DENSITY_RANGE = (0.2, 2.0)   # g/ml outside this is a parsing artefact, not a food
# Preparation/processing words: -0.5 each unless the query or category allows them
# (a raw canonical must not pick "cooked"/"canned" rows).
BAD_WORDS = ('breaded', 'batter', 'cooked', 'roasted', 'fried', 'boiled', 'braised', 'baked', 'canned',
             'frozen', 'dried', 'microwaved', 'juice', 'babyfood', 'fast foods', 'restaurant')
# Formulation variants: -0.4 unless the query asks for them (bacon != "Bacon, meatless").
VARIANT_RE = re.compile(r'\bmeatless\b|\bimitation\b|freeze-dried|\bdehydrated\b|\blow ?fat\b|'
                        r'\breduced fat\b|\bnonfat\b|\bskim\b|\bfat[- ]free\b|\bcandied\b|\b[12]%')
# Colours that mark a non-default variety when the query names no colour (walnuts != black walnuts).
ODD_COLORS = {'yellow', 'black', 'purple', 'golden'}
DEFAULT_FILE = Path(__file__).resolve().parents[2] / 'data' / 'canonical_ingredients.yaml'
MANUAL_PREFIXES = ('manual:', 'frida:')
REPORT_COLUMNS = ['slug', 'name_cs', 'status', 'query', 'usda_description', 'fdc_id', 'confidence',
                  'kcal', 'protein', 'carbs', 'fat', 'density', 'piece_weight_g', 'notes']
# Written key order inside a `nutrition:` block; unknown keys go after usda_query.
BLOCK_ORDER = ('kcal', 'protein', 'carbs', 'fat', 'density', 'piece_weight_g', 'unit_weights',
               'usda_query', 'source')


# Description tokens that exclude a food outright (restaurant, branded, snack, prepared dishes)
# unless the query itself contains the token.
EXCLUDE_TOKENS = {'restaurant', 'fast', 'school', 'candies', 'candy', 'snacks', 'snack', 'babyfood',
                  'formula', 'supplement', 'applebee', 'mcdonald', 'kfc', 'burger', 'pizza', 'taco',
                  'campbell', 'kraft', 'nestle', 'hershey', 'prepared', 'mix'}
# Words that mark a different product when the query lacks them (walnuts -> walnut oil):
# -0.6 when the word is in the head, -0.3 elsewhere in the description.
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
    (r'\bbeetroots?\b', 'beets'), (r'\bhome-prepared\b', 'homemade'),
    (r'\bfilberts?\b', 'hazelnuts'), (r'\bmangetout\b', 'snow peas'),
    (r'\bmince[d]?\b', 'ground'), (r'\bfillets?\b', ''),
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
                 'distilled', 'variety', 'meat', 'and', 'product', 'cured'}
COLORS = {'white', 'red', 'green', 'yellow', 'black', 'brown', 'orange', 'purple', 'golden'}
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


_PERCENT = re.compile(r'\d+(?:\.\d+)?%')


def _tokens(s: str) -> set:
    """Singular-folded words (3+ letters) plus percent tokens ("2%", "85%") so fat grades differ."""
    n = _norm(s)
    return {_singular(t) for t in re.split(r'[^a-z]+', n) if len(t) > 2} | set(_PERCENT.findall(n))


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


def _score(want: set, food: dict, category: str, q_norm: str = '') -> float:
    desc_raw = food.get('description') or ''
    desc, have, head, klass = _profile(desc_raw)
    strong = want - WEAK_TOKENS or want
    if not (strong & head) or _excluded(desc_raw, have, want):
        return 0.0
    weight = {t: (0.5 if t in WEAK_TOKENS and t not in strong else 1.0) for t in want}
    score = sum(weight[t] for t in want & have) / sum(weight.values())
    if strong <= head:
        score += 0.25                                         # the head names exactly this food
    class_tokens = set(klass.split()) if klass in PURE_CLASSES else set()
    score -= 0.1 * len(head - want - class_tokens)          # "Milk, buttermilk" is not "whole milk"
    want_colors, head_colors = want & COLORS, head & COLORS
    if want_colors and head_colors and not want_colors & head_colors:
        score -= 0.5                                          # white wine vinegar != red wine vinegar
    elif not want_colors and have & ODD_COLORS:
        score -= 0.2                                          # walnuts -> english, not black
    if klass and category and klass in CLASS_CATEGORIES and category not in CLASS_CATEGORIES[klass]:
        score -= 0.5                                          # class serves another category
    for v in VARIANT_RE.findall(desc):                        # phrase test on the query text, in order
        if v not in q_norm and v.replace('-', ' ') not in q_norm:
            score -= 0.4
    if category in ('meat', 'fish') and 'ground' in have and 'ground' not in want:
        score -= 0.3                                          # a cut, not mince
    if category in ('meat', 'fish') and 'skin' in have and 'skin' not in want:
        score -= 0.2                                          # chicken breast = meat only
    ok_states = STATE_OK.get(category, ())
    if category in ('meat', 'fish', 'eggs', 'vegetables', 'fruits', 'other', '') and 'raw' in have:
        score += 0.15                                         # as-bought form for fresh foods
    if any(re.search(rf'\b{s}\b', desc) for s in ok_states):
        score += 0.1                                          # category's as-bought state
    for bad in BAD_WORDS:
        if bad in want or any(re.fullmatch(s, bad) for s in ok_states):
            continue
        if (bad == 'canned' and category == 'canned') or (bad == 'frozen' and category == 'frozen'):
            continue
        if re.search(rf'\b{bad}\b', desc):
            score -= 0.5
    for w in OTHER_PRODUCT_WORDS:
        if w in want or w not in have:
            continue
        if w == klass and klass in PURE_CLASSES:              # "Soup, stock, chicken" is a stock
            continue
        score -= 0.6 if w in head else 0.3                    # olives != "Oil, olive"
    if 'with' in desc.split() and 'with' not in want and not re.search(
            r'\bwith(out)? (added|salt|skin|bone)', desc):
        score -= 0.3                                          # "made with"/"with cheese" dishes
    if re.search(r'\((alaska native|navajo|hopi|apache|shoshone|[^)]*indians?)\)', desc):
        score -= 0.4                                          # regional/traditional variants
    score -= 0.01 * max(0, len(have) - len(want))            # prefer the plainest description
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
    q_norm = _norm(query or name)
    if not want:
        return None, 0.0
    best, best_key = None, (0.0, 0)
    for f in foods:
        s = _score(want, f, category, q_norm)
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


def _measure(unit: str, mod: str) -> Tuple[Optional[str], str]:
    """(tbsp|tsp|cup or None, remaining qualifier) for one portion."""
    if unit in USDA_ML:
        return unit, mod
    m = re.match(r'(tbsp|tsp|cup)s?\b[,\s]*(.*)', mod)
    return (m.group(1), m.group(2)) if m else (None, mod)


def derive_density(food: dict) -> Optional[float]:
    """g/ml from a tbsp/tsp portion, else a plain cup (USDA cup = 240 ml); None if implausible.

    Cut or packed forms ("cup, chopped", "tbsp chopped") are skipped: their weight
    reflects air gaps, not the density of the food.
    """
    candidates = []
    for g, unit, mod in _portions(food):
        key, rest = _measure(unit, mod)
        if key is None or any(w in rest for w in CUP_FORM_WORDS):
            continue
        candidates.append((0 if key in ('tbsp', 'tsp') else 1, g / USDA_ML[key]))
    for _, d in sorted(candidates, key=lambda c: c[0]):
        if DENSITY_RANGE[0] <= d <= DENSITY_RANGE[1]:
            return round(d, 3)
    return None


def derive_piece_weights(food: dict) -> Dict[str, Any]:
    """{'piece_weight_g', 'unit_weights'} from count portions (medium/each/clove/leaf…).

    Portions measured by volume/weight are ignored; a portion that names a count
    unit (leaf, slice, clove…) only sets that unit, never the piece weight. Among
    several portions for the same unit, the plain or `medium` one wins.
    """
    pieces: Dict[str, float] = {}
    units: Dict[str, Tuple[int, float]] = {}
    for g, unit, mod in _portions(food):
        words = {_singular(w) for w in re.split(r'[^a-z]+', f'{unit} {mod}') if w}
        if words & MEASURE_WORDS:
            continue
        unit_hits = [cz for usda_word, cz in UNIT_MODIFIERS.items() if usda_word in words]
        if unit_hits:
            rank = 0 if len(words - {'undetermined'}) == 1 else (1 if 'medium' in words else 2)
            for cz in unit_hits:
                if cz not in units or rank < units[cz][0]:
                    units[cz] = (rank, round(g, 1))
            continue
        for w in PIECE_MODIFIERS:
            if w in words and w not in pieces:
                pieces[w] = round(g, 1)
    piece = next((pieces[w] for w in PIECE_MODIFIERS if w in pieces), None)
    return {'piece_weight_g': piece, 'unit_weights': {cz: v for cz, (_, v) in units.items()}}


def _hand_set(existing: dict) -> Dict[str, Any]:
    """Hand-maintained piece/unit weights from an existing nutrition block."""
    kept = {}
    if existing.get('piece_weight_g') is not None:
        kept['piece_weight_g'] = existing['piece_weight_g']
    if existing.get('unit_weights'):
        kept['unit_weights'] = dict(existing['unit_weights'])
    return kept


def _scalar(v: Any) -> str:
    """One YAML value on one line (flow style for mappings)."""
    out = yaml.safe_dump(v, default_flow_style=True, allow_unicode=True, width=10_000).strip()
    return out[:-4].rstrip() if out.endswith('\n...') else out


_KEY_LINE = re.compile(r'^(\s+)([A-Za-z_][\w-]*):\s*(.*?)(\s+#.*)?$')


def _render_block(block: Dict[str, Any], old_lines: List[str], indent: str) -> List[str]:
    """`nutrition:` lines in BLOCK_ORDER; an old key line whose value is unchanged is kept verbatim
    (so its trailing `# comment` survives)."""
    old: Dict[str, str] = {}
    for line in old_lines[1:]:
        m = _KEY_LINE.match(line.rstrip('\n'))
        if m:
            old[m.group(2)] = line
    keys = [k for k in BLOCK_ORDER if k in block]
    extra = [k for k in block if k not in BLOCK_ORDER]
    pos = keys.index('source') if 'source' in keys else len(keys)
    keys[pos:pos] = extra
    out = [f'{indent}nutrition:\n']
    for k in keys:
        line = old.get(k)
        if line is not None:
            m = _KEY_LINE.match(line.rstrip('\n'))
            try:
                same = yaml.safe_load(m.group(3)) == block[k]
            except yaml.YAMLError:
                same = False
            if same:
                out.append(line if line.endswith('\n') else line + '\n')
                continue
        out.append(f'{indent}  {k}: {_scalar(block[k])}\n')
    return out


def _write_blocks(text: str, blocks: Dict[int, Dict[str, Any]], names: List[str],
                  has_nutrition: frozenset = frozenset()) -> str:
    """Replace/append `nutrition:` blocks for list entries by index, editing text in place.

    Entries are the top-level `- name:` items; an entry runs until the next line
    that starts at column 0. An existing `nutrition:` block (the key line plus its
    more-indented continuation lines, or an inline `nutrition: {...}`) is replaced
    where it is; otherwise the block is inserted after the entry's last line.
    """
    lines = text.splitlines(keepends=True)
    if lines and not lines[-1].endswith('\n'):
        lines[-1] += '\n'
    starts = [i for i, l in enumerate(lines) if l.startswith('- ')]
    if len(starts) != len(names):
        raise CommandError(f'found {len(starts)} "- " entries in the text but {len(names)} parsed')
    for idx in sorted(blocks, reverse=True):              # bottom-up keeps earlier indexes valid
        start = starts[idx]
        head = yaml.safe_load(lines[start]) or [{}]
        if not isinstance(head, list) or (head[0] or {}).get('name') != names[idx]:
            raise CommandError(f'entry {idx} text/parse mismatch at line {start + 1}')
        end = start + 1
        while end < len(lines) and (not lines[end].strip() or lines[end][0] in ' \t'):
            end += 1
        while end > start + 1 and not lines[end - 1].strip():
            end -= 1                                        # trailing blank lines stay outside
        indent = '  '
        nb_start = next((i for i in range(start + 1, end)
                         if re.match(r'^\s+nutrition:', lines[i])), None)
        if nb_start is not None:
            indent = re.match(r'^(\s+)', lines[nb_start]).group(1)
            nb_end = nb_start + 1
            while nb_end < end and (lines[nb_end][:len(indent) + 1].strip() == ''
                                    and len(lines[nb_end]) - len(lines[nb_end].lstrip()) > len(indent)):
                nb_end += 1
            old = lines[nb_start:nb_end]
            lines[nb_start:nb_end] = _render_block(blocks[idx], old, indent)
        elif idx in has_nutrition:   # a column-0 comment cut the entry short; appending would duplicate the key
            raise CommandError(f'entry {names[idx]!r} has a nutrition: key outside its line range '
                               f'(line {start + 1}); move the comment or fix the entry by hand')
        else:
            lines[end:end] = _render_block(blocks[idx], [], indent)
    return ''.join(lines)


def _num(v: Any) -> Any:
    return '' if v is None else v


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
        text = yaml_path.read_text(encoding='utf-8')
        entries = yaml.safe_load(text) or []
        if not isinstance(entries, list):
            raise CommandError(f'{yaml_path} must contain a list of entries')

        counts = {'matched': 0, 'kept_manual': 0, 'needs_review': 0}
        rows = []
        blocks: Dict[int, Dict[str, Any]] = {}
        for idx, e in enumerate(entries):
            name = e.get('name') or ''
            slug = e.get('slug') or slugify(name)
            existing = dict(e.get('nutrition') or {})
            query = existing.get('usda_query') or e.get('usda_query')
            row = {c: '' for c in REPORT_COLUMNS}
            row.update(slug=slug, name_cs=e.get('name_cs') or '', query=query or '')

            source = str(existing.get('source') or '')
            if source.startswith(MANUAL_PREFIXES):
                counts['kept_manual'] += 1
                row.update(status='kept_manual', notes=source,
                           **{k: _num(existing.get(k)) for k in
                              ('kcal', 'protein', 'carbs', 'fat', 'density', 'piece_weight_g')})
                rows.append(row)
                continue

            match, conf = best_match(name, foods, category=e.get('category') or '', query=query)
            nutr = nutrients_of(match) if match is not None else {}
            if match is not None:
                row.update(usda_description=match.get('description', ''), fdc_id=match.get('fdcId', ''),
                           confidence=conf)
            missing = [k for k in ('kcal', 'protein', 'carbs', 'fat') if k not in nutr]
            if match is None or conf < MIN_CONFIDENCE or missing:
                counts['needs_review'] += 1
                row.update(status='needs_review', notes=(
                    'no candidate' if match is None else
                    f'below {MIN_CONFIDENCE}' if conf < MIN_CONFIDENCE else f'missing {",".join(missing)}'))
                rows.append(row)
                continue                                  # YAML left untouched; the CSV is the worklist

            hand = _hand_set(existing)
            block: Dict[str, Any] = dict(existing)        # keeps unknown keys
            block.update({k: nutr[k] for k in ('kcal', 'protein', 'carbs', 'fat')})
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
            if query:
                block['usda_query'] = query
            block['source'] = f"usda:{match['fdcId']}"
            blocks[idx] = block

            counts['matched'] += 1
            notes = []
            if 'piece_weight_g' in hand and pw['piece_weight_g'] not in (None, hand['piece_weight_g']):
                notes.append(f"usda piece {pw['piece_weight_g']} g ignored")
            row.update(status='matched', density=_num(block.get('density')),
                       piece_weight_g=_num(block.get('piece_weight_g')), notes='; '.join(notes),
                       **{k: block[k] for k in ('kcal', 'protein', 'carbs', 'fat')})
            rows.append(row)

        if opts.get('report'):
            with open(opts['report'], 'w', newline='', encoding='utf-8') as fh:
                w = csv.DictWriter(fh, fieldnames=REPORT_COLUMNS)
                w.writeheader()
                w.writerows(rows)

        if opts.get('write_yaml') and blocks:
            new_text = _write_blocks(text, blocks, [e.get('name') for e in entries],
                                     frozenset(i for i, e in enumerate(entries) if 'nutrition' in e))
            if new_text != text:
                yaml_path.write_text(new_text, encoding='utf-8')

        self.stdout.write(
            f"matched={counts['matched']} kept_manual={counts['kept_manual']} "
            f"needs_review={counts['needs_review']} total={len(entries)}")
