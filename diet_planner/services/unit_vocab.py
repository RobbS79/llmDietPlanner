"""The one unit vocabulary for recipes, pricing and nutrition.

Codes: mass g/dkg/kg; volume ml/cl/dl/l/tsp/tbsp/cup/konzerva/sklenice;
count ks + ingredient-specific pieces (stroužek, plátek, svazek, hrst, balení, hlava, cm,
dávka, stonek, kostka);
garnish units with a fixed gram default (špetka, snítka, lístek).
"""
from typing import Dict, Optional, Tuple

ALIASES: Dict[str, str] = {
    # mass
    'g': 'g', 'gram': 'g', 'gramy': 'g', 'gramu': 'g', 'gramů': 'g', 'gramow': 'g', 'g.': 'g',
    'mg': 'mg', 'miligram': 'mg', 'miligramy': 'mg', 'miligramů': 'mg',
    'dkg': 'dkg', 'dag': 'dkg', 'deka': 'dkg',
    'kg': 'kg', 'kilogram': 'kg', 'kilogramy': 'kg', 'kilogramů': 'kg', 'kilogramow': 'kg', 'kg.': 'kg',
    # volume
    'ml': 'ml', 'mililitr': 'ml', 'mililitry': 'ml', 'mililitrů': 'ml', 'milliliter': 'ml', 'millilitre': 'ml', 'ml.': 'ml',
    'cl': 'cl', 'dl': 'dl', 'deci': 'dl', 'decilitr': 'dl', 'decilitry': 'dl',
    'l': 'l', 'litr': 'l', 'litry': 'l', 'litrů': 'l', 'litrow': 'l', 'liter': 'l', 'litre': 'l', 'l.': 'l',
    'lžička': 'tsp', 'lžičky': 'tsp', 'lžiček': 'tsp', 'lžičku': 'tsp', 'čl': 'tsp', 'čajová lžička': 'tsp',
    'lyzicka': 'tsp', 'lzicka': 'tsp', 'tsp': 'tsp', 'teaspoon': 'tsp',
    'lžíce': 'tbsp', 'lžíci': 'tbsp', 'lžic': 'tbsp', 'pl': 'tbsp', 'polévková lžíce': 'tbsp',
    'polevkova lzice': 'tbsp', 'lzice': 'tbsp', 'tbsp': 'tbsp', 'tablespoon': 'tbsp',
    'hrnek': 'cup', 'hrnky': 'cup', 'hrnků': 'cup', 'hrnku': 'cup', 'šálek': 'cup', 'šálky': 'cup',
    'salek': 'cup', 'cup': 'cup', 'cups': 'cup',
    'konzerva': 'konzerva', 'plechovka': 'konzerva', 'sklenice': 'sklenice',
    # count
    'ks': 'ks', 'ks.': 'ks', 'kus': 'ks', 'kusy': 'ks', 'kusů': 'ks', 'kusu': 'ks', 'kusow': 'ks',
    'piece': 'ks', 'pieces': 'ks', 'pcs': 'ks', 'pc': 'ks', 'szt': 'ks', 'sztuk': 'ks', 'sztuki': 'ks',
    'stroužek': 'stroužek', 'stroužky': 'stroužek', 'stroužků': 'stroužek', 'strouzek': 'stroužek',
    'plátek': 'plátek', 'plátky': 'plátek', 'plátků': 'plátek', 'platek': 'plátek',
    'svazek': 'svazek', 'svazky': 'svazek', 'svazků': 'svazek', 'svazku': 'svazek',
    'hlava': 'hlava', 'hlavy': 'hlava', 'hlávka': 'hlava', 'hlávky': 'hlava', 'hlávek': 'hlava',
    'hlavička': 'hlava', 'hlavičky': 'hlava',
    'cm': 'cm',
    'dávka': 'dávka', 'dávky': 'dávka', 'dávek': 'dávka', 'odměrka': 'dávka', 'odměrky': 'dávka',
    'scoop': 'dávka',
    'stonek': 'stonek', 'stonky': 'stonek', 'stonků': 'stonek', 'řapík': 'stonek', 'řapíky': 'stonek',
    'kostka': 'kostka', 'kostky': 'kostka', 'kostek': 'kostka',
    'hrst': 'hrst', 'hrstka': 'hrst', 'malá hrst': 'hrst',
    'balení': 'balení', 'sáček': 'balení', 'balíček': 'balení',
    # garnish
    'špetka': 'špetka', 'špetky': 'špetka', 'spetka': 'špetka', 'pinch': 'špetka',
    'snítka': 'snítka', 'snítky': 'snítka', 'snítek': 'snítka', 'větvička': 'snítka',
    'větvičky': 'snítka', 'větviček': 'snítka', 'vetvicka': 'snítka',
    'lístek': 'lístek', 'lístky': 'lístek', 'lístků': 'lístek', 'lístku': 'lístek',
    'listy': 'lístek', 'list': 'lístek',
}

MASS_G: Dict[str, float] = {'mg': 0.001, 'g': 1.0, 'dkg': 10.0, 'kg': 1000.0}
VOLUME_ML: Dict[str, float] = {'ml': 1.0, 'cl': 10.0, 'dl': 100.0, 'l': 1000.0,
                               'tsp': 5.0, 'tbsp': 15.0, 'cup': 250.0,
                               'konzerva': 400.0, 'sklenice': 300.0}
COUNT_UNITS = ('ks', 'stroužek', 'plátek', 'svazek', 'hrst', 'balení',
               'hlava', 'cm', 'dávka', 'stonek', 'kostka')
GARNISH_G: Dict[str, float] = {'špetka': 1.0, 'snítka': 2.0, 'lístek': 1.0}


def normalize_unit(unit) -> str:
    if not unit:
        return ''
    key = str(unit).strip().lower()
    if key not in ALIASES:
        key = key.rstrip('.').strip()
    return ALIASES.get(key, key)


def unit_kind(code: str) -> Optional[str]:
    if code in MASS_G:
        return 'mass'
    if code in VOLUME_ML:
        return 'volume'
    if code in COUNT_UNITS:
        return 'count'
    if code in GARNISH_G:
        return 'garnish'
    return None


# Volume units for nutrition only; pricing leaves them unconvertible (as before).
_UNPRICED_VOLUME = ('konzerva', 'sklenice')


def to_base(value: float, unit) -> Tuple[float, Optional[str]]:
    """(base_value, dimension) for pricing: mass→g, volume→ml, count→ks.
    Only `špetka` bridges to pricing (a pinch ≈ 0.3 ml); `snítka` and `lístek`
    are unpriced (dimension None), as before. Ingredient-
    specific pieces (stroužek, plátek, ...) are NOT convertible for pricing
    (dimension None) — only plain `ks` is a count."""
    code = normalize_unit(unit)
    if code in MASS_G:
        return value * MASS_G[code], 'mass'
    if code in VOLUME_ML and code not in _UNPRICED_VOLUME:
        return value * VOLUME_ML[code], 'volume'
    if code == 'ks':
        return value, 'count'
    if code == 'špetka':
        return value * 0.3, 'volume'
    return value, None
