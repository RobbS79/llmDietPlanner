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
BAD_WORDS = ('cooked', 'roasted', 'fried', 'boiled', 'braised', 'baked', 'canned', 'frozen', 'dried',
             'dehydrated', 'juice', 'babyfood', 'fast foods', 'restaurant')
DEFAULT_FILE = Path(__file__).resolve().parents[2] / 'data' / 'canonical_ingredients.yaml'
MANUAL_PREFIXES = ('manual:', 'frida:')
REPORT_COLUMNS = ['slug', 'name_cs', 'status', 'usda_description', 'fdc_id', 'confidence',
                  'kcal', 'protein', 'carbs', 'fat', 'density', 'piece_weight_g']


def _singular(t: str) -> str:
    """Crude plural fold so 'onion' meets 'Onions' and 'tomato' meets 'Tomatoes'."""
    if t.endswith('ies') and len(t) > 4:
        return t[:-3] + 'y'
    if t.endswith(('oes', 'ches', 'shes', 'sses')):
        return t[:-2]
    if t.endswith('s') and not t.endswith(('ss', 'us')) and len(t) > 3:
        return t[:-1]
    return t


def _tokens(s: str) -> set:
    return {_singular(t) for t in re.split(r'[^a-z]+', (s or '').lower()) if len(t) > 2}


def best_match(name: str, foods: List[dict], *, category: str = '',
               query: Optional[str] = None) -> Tuple[Optional[dict], float]:
    """Best SR Legacy food for a canonical name (or `query` hint) and a 0..1 confidence.

    Score = share of wanted tokens found in the description, +0.15 for a raw
    food, -0.5 per processing word (canned/frozen allowed for those
    categories), minus a small penalty for long, over-specific descriptions.
    """
    want = _tokens(query or name)
    if not want:
        return None, 0.0
    allow_canned = category == 'canned'
    allow_frozen = category == 'frozen'
    best, best_score = None, 0.0
    for f in foods:
        desc = (f.get('description') or '').lower()
        have = _tokens(desc)
        overlap = len(want & have) / len(want)
        if overlap == 0:
            continue
        score = overlap
        if 'raw' in have:
            score += 0.15
        for bad in BAD_WORDS:
            if bad in desc and not ((bad == 'canned' and allow_canned) or (bad == 'frozen' and allow_frozen)):
                score -= 0.5
        score -= 0.01 * max(0, len(have) - len(want))
        if score > best_score:
            best, best_score = f, score
    return (best, round(min(best_score, 1.0), 2)) if best is not None and best_score > 0 else (None, 0.0)


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
