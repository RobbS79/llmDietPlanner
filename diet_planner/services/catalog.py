"""
Catalog Preparation Service — builds a real product catalog for LLM prompt injection.

Instead of letting the LLM invent ingredients freely, we feed it a compact
representation of products that actually exist in the selected store(s).
The LLM is then constrained to use ONLY these products (plus pantry staples).
"""
import logging
from typing import Dict, Any, List, Optional

from django.utils import timezone

from diet_planner.models import LeafletOffer, DietaryGoal, COUNTRY_TO_SHOPS

logger = logging.getLogger(__name__)


# ─── Pantry staples: always available, don't need a store match ───────────
# Each entry: (name_cs, name_en, category, default_unit, est_price_czk, est_price_eur)
PANTRY_STAPLES = [
    ('sůl', 'salt', 'spices', 'g', 15.0, 0.60),
    ('pepř černý mletý', 'black pepper', 'spices', 'g', 25.0, 1.00),
    ('cukr', 'sugar', 'baking', 'g', 25.0, 1.00),
    ('mouka hladká', 'plain flour', 'baking', 'g', 20.0, 0.80),
    ('mouka hrubá', 'coarse flour', 'baking', 'g', 20.0, 0.80),
    ('olivový olej', 'olive oil', 'oils', 'ml', 80.0, 3.50),
    ('slunečnicový olej', 'sunflower oil', 'oils', 'ml', 50.0, 2.00),
    ('máslo', 'butter', 'dairy', 'g', 45.0, 1.80),
    ('ocet', 'vinegar', 'condiments', 'ml', 25.0, 1.00),
    ('sójová omáčka', 'soy sauce', 'condiments', 'ml', 40.0, 1.60),
    ('med', 'honey', 'condiments', 'g', 60.0, 2.50),
    ('hořčice', 'mustard', 'condiments', 'g', 20.0, 0.80),
    ('česnek', 'garlic', 'vegetables', 'ks', 10.0, 0.40),
    ('cibule', 'onion', 'vegetables', 'ks', 5.0, 0.20),
    ('bazalka sušená', 'dried basil', 'spices', 'g', 20.0, 0.80),
    ('oregano', 'oregano', 'spices', 'g', 20.0, 0.80),
    ('paprika mletá', 'ground paprika', 'spices', 'g', 25.0, 1.00),
    ('kmín', 'caraway', 'spices', 'g', 20.0, 0.80),
    ('skořice', 'cinnamon', 'spices', 'g', 25.0, 1.00),
    ('vanilkový cukr', 'vanilla sugar', 'baking', 'g', 10.0, 0.40),
    ('prášek do pečiva', 'baking powder', 'baking', 'g', 10.0, 0.40),
    ('kakao', 'cocoa powder', 'baking', 'g', 35.0, 1.40),
    ('škrob', 'starch', 'baking', 'g', 20.0, 0.80),
    ('voda', 'water', 'beverages', 'ml', 0.0, 0.0),
    ('kečup', 'ketchup', 'condiments', 'g', 30.0, 1.20),
    ('rajčatový protlak', 'tomato paste', 'canned', 'g', 20.0, 0.80),
    ('kurkuma', 'turmeric', 'spices', 'g', 30.0, 1.20),
    ('zázvor mletý', 'ground ginger', 'spices', 'g', 30.0, 1.20),
    ('tymián', 'thyme', 'spices', 'g', 20.0, 0.80),
    ('rozmarýn', 'rosemary', 'spices', 'g', 20.0, 0.80),
]

# ─── Dietary restriction keyword filters ──────────────────────────────────
DIETARY_EXCLUSIONS = {
    'vegetarian': [
        'kuřecí', 'hovězí', 'vepřové', 'maso', 'salám', 'šunka', 'klobás',
        'ryba', 'losos', 'tuňák', 'treska', 'pstruh', 'krevety', 'garnát',
        'chicken', 'beef', 'pork', 'meat', 'sausage', 'ham', 'fish', 'salmon',
        'tuna', 'shrimp', 'bacon', 'steak', 'řízek', 'párek', 'jitrnice',
    ],
    'vegan': [
        'kuřecí', 'hovězí', 'vepřové', 'maso', 'salám', 'šunka', 'klobás',
        'ryba', 'losos', 'tuňák', 'treska', 'krevety',
        'vejce', 'vajíčk', 'mléko', 'sýr', 'jogurt', 'tvaroh', 'máslo',
        'smetana', 'šlehačka', 'cheese', 'yogurt', 'milk', 'butter', 'cream',
        'egg', 'honey', 'med',
        'chicken', 'beef', 'pork', 'meat', 'fish', 'salmon',
    ],
    'gluten_free': [
        'mouka', 'těstovin', 'chléb', 'pečivo', 'rohlík', 'houska',
        'flour', 'pasta', 'bread', 'roll', 'wheat', 'pšenič',
    ],
    'lactose_free': [
        'mléko', 'smetana', 'jogurt', 'sýr', 'tvaroh', 'šlehačka',
        'milk', 'cream', 'yogurt', 'cheese', 'cottage',
    ],
}

# ─── Product categorization keywords ──────────────────────────────────────
CATEGORY_KEYWORDS = {
    'proteins': ['kuřecí', 'hovězí', 'vepřové', 'maso', 'salám', 'šunka',
                 'ryba', 'losos', 'tuňák', 'tofu', 'tempeh', 'seitan',
                 'chicken', 'beef', 'pork', 'fish', 'salmon', 'tuna'],
    'dairy': ['mléko', 'jogurt', 'tvaroh', 'sýr', 'máslo', 'smetana',
              'milk', 'yogurt', 'cheese', 'butter', 'cream'],
    'eggs': ['vejce', 'vajíčk', 'egg'],
    'grains': ['rýže', 'těstovin', 'mouka', 'chléb', 'ovesné', 'pečivo',
               'rice', 'pasta', 'flour', 'bread', 'oat'],
    'vegetables': ['rajče', 'paprika', 'cibule', 'česnek', 'mrkev', 'brambor',
                   'špenát', 'salát', 'okurka', 'brokolice', 'cuketa', 'dýně',
                   'tomato', 'pepper', 'onion', 'garlic', 'carrot', 'potato',
                   'spinach', 'lettuce', 'cucumber', 'broccoli'],
    'fruits': ['jablko', 'banán', 'pomeranč', 'citron', 'jahod', 'malin',
               'borůvk', 'hrozn', 'avokádo', 'mango',
               'apple', 'banana', 'orange', 'lemon', 'berry', 'grape', 'avocado'],
    'oils_condiments': ['olej', 'ocet', 'omáčka', 'hořčice', 'kečup', 'mayo',
                        'oil', 'vinegar', 'sauce', 'mustard', 'ketchup'],
    'canned': ['konzerv', 'passata', 'protlak', 'fazole', 'kukuřice',
               'canned', 'beans', 'corn'],
    'beverages': ['džus', 'voda', 'čaj', 'káva', 'juice', 'water', 'tea', 'coffee'],
}


class CatalogService:
    """Prepares a filtered, compact product catalog for LLM prompt injection."""

    def build_catalog_for_prompt(
        self,
        goal: DietaryGoal,
        max_products: int = 500,
    ) -> Dict[str, Any]:
        """
        Build a catalog suitable for injecting into the LLM prompt.

        Returns:
            {
                'products_by_category': {'proteins': [...], 'dairy': [...], ...},
                'total_products': int,
                'pantry_staples': [...],
                'store_name': str,
                'catalog_limited': bool,
            }
        """
        products = self._load_products(goal)
        products = self._filter_by_dietary_restrictions(products, goal)
        categorized = self._categorize(products)
        limited = self._limit_products(categorized, max_products)

        total = sum(len(items) for items in limited.values())
        pantry = self._get_pantry_staples(goal)

        store_name = goal.shop or 'local store'
        catalog_limited = total >= max_products

        logger.info(
            f"Catalog for goal {goal.id}: {total} products in {len(limited)} categories, "
            f"{len(pantry)} pantry staples, limited={catalog_limited}"
        )

        return {
            'products_by_category': limited,
            'total_products': total,
            'pantry_staples': pantry,
            'store_name': store_name,
            'catalog_limited': catalog_limited,
        }

    def build_compact_prompt_text(self, catalog: Dict[str, Any], goal: DietaryGoal) -> str:
        """Convert catalog dict to a compact text block for the LLM prompt."""
        lines = []
        for category, products in catalog['products_by_category'].items():
            if not products:
                continue
            lines.append(f"\n[{category.upper()}]")
            for p in products:
                pkg = f" ({p['pkg']})" if p.get('pkg') else ""
                disc = " *AKCE*" if p.get('discounted') else ""
                lines.append(f"  #{p['id']} {p['name']}{pkg} — {p['price']} {goal.currency}{disc}")

        lines.append("\n[PANTRY STAPLES — always available, no store match needed]")
        for s in catalog['pantry_staples']:
            lines.append(f"  {s['name']} ({s['unit']})")

        return "\n".join(lines)

    # ─── Internal methods ─────────────────────────────────────────────

    def _load_products(self, goal: DietaryGoal) -> List[Dict[str, Any]]:
        now = timezone.now()
        filters = {
            'price__isnull': False,
            'price__gt': 0,
        }

        if goal.shop:
            filters['shop'] = goal.shop
            filters['country'] = goal.country

            offers = LeafletOffer.objects.filter(
                expires_at__gt=now,
                **filters,
            ).order_by('ingredient_name')

            if offers.count() == 0:
                offers = LeafletOffer.objects.filter(**filters).order_by('-scraped_at')
                logger.warning(f"No fresh offers for {goal.shop}, using all available ({offers.count()})")
        else:
            shops = COUNTRY_TO_SHOPS.get(goal.country, [])
            offers = LeafletOffer.objects.filter(
                shop__in=shops,
                country=goal.country,
                expires_at__gt=now,
                **filters,
            ).order_by('ingredient_name')

        products = []
        for offer in offers:
            pkg_info = self._extract_package_info(offer.display_name or '', offer.unit or '')
            products.append({
                'id': offer.pk,
                'name': offer.ingredient_name,
                'display_name': offer.display_name,
                'price': float(offer.price),
                'currency': offer.currency,
                'unit': offer.unit or '',
                'pkg': pkg_info,
                'price_type': offer.price_type or 'REGULAR',
                'discounted': offer.price_type == 'DISCOUNTED',
                'shop': offer.shop,
            })

        return products

    def _filter_by_dietary_restrictions(
        self,
        products: List[Dict[str, Any]],
        goal: DietaryGoal,
    ) -> List[Dict[str, Any]]:
        restrictions_text = (goal.dietary_restrictions or '').lower()
        if not restrictions_text:
            return products

        exclude_keywords = set()
        for restriction, keywords in DIETARY_EXCLUSIONS.items():
            if restriction in restrictions_text:
                exclude_keywords.update(kw.lower() for kw in keywords)

        if not exclude_keywords:
            return products

        filtered = []
        for p in products:
            name_lower = p['name'].lower()
            display_lower = (p.get('display_name') or '').lower()
            combined = f"{name_lower} {display_lower}"
            if not any(kw in combined for kw in exclude_keywords):
                filtered.append(p)

        logger.info(f"Dietary filter: {len(products)} -> {len(filtered)} products (excluded {len(exclude_keywords)} keywords)")
        return filtered

    def _categorize(self, products: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        categorized: Dict[str, List[Dict[str, Any]]] = {cat: [] for cat in CATEGORY_KEYWORDS}
        categorized['other'] = []

        for p in products:
            name_lower = p['name'].lower()
            display_lower = (p.get('display_name') or '').lower()
            combined = f"{name_lower} {display_lower}"
            placed = False
            for category, keywords in CATEGORY_KEYWORDS.items():
                if any(kw in combined for kw in keywords):
                    categorized[category].append(p)
                    placed = True
                    break
            if not placed:
                categorized['other'].append(p)

        return categorized

    def _limit_products(
        self,
        categorized: Dict[str, List[Dict[str, Any]]],
        max_total: int,
    ) -> Dict[str, List[Dict[str, Any]]]:
        total = sum(len(items) for items in categorized.values())
        if total <= max_total:
            return categorized

        ratio = max_total / total
        limited = {}
        for cat, items in categorized.items():
            discounted = [i for i in items if i.get('discounted')]
            regular = [i for i in items if not i.get('discounted')]
            cat_limit = max(1, int(len(items) * ratio))
            selected = discounted[:cat_limit]
            remaining = cat_limit - len(selected)
            if remaining > 0:
                selected.extend(regular[:remaining])
            limited[cat] = selected

        return limited

    def _get_pantry_staples(self, goal: DietaryGoal) -> List[Dict[str, str]]:
        lang = goal.language_code or 'cs'
        currency = goal.currency or 'CZK'
        staples = []
        for name_cs, name_en, category, unit, price_czk, price_eur in PANTRY_STAPLES:
            name = name_cs if lang in ('cs', 'sk') else name_en
            price = price_czk if currency == 'CZK' else price_eur
            staples.append({
                'name': name,
                'name_cs': name_cs,
                'name_en': name_en,
                'category': category,
                'unit': unit,
                'estimated_price': price,
                'currency': currency,
            })
        return staples

    def _extract_package_info(self, display_name: str, unit: str) -> str:
        """Extract a compact package description like '500g' or '10ks'."""
        import re
        if not display_name:
            return ''
        patterns = [
            r'(\d+[\.,]?\d*)\s*(kg|g|ml|l|ks|bal)',
        ]
        for pattern in patterns:
            match = re.search(pattern, display_name, re.I)
            if match:
                size = match.group(1).replace(',', '.')
                u = match.group(2).lower()
                return f"{size}{u}"
        return ''
