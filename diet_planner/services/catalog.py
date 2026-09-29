"""
Shared catalog constants.

- ``PANTRY_STAPLES``: pantry items assumed available without a store match
  (used by ``price_resolver``).
- ``DIETARY_EXCLUSIONS``: keyword filters per dietary tag (used by
  ``restrictions``).
"""


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
