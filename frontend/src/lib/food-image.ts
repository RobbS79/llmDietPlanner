const FALLBACK_CATEGORY = 'kure';

const KEYWORD_RULES: [string[], string][] = [
  [['ovesn', 'kaše', 'müsli', 'porridge', 'oatmeal'], 'ovesna-kase'],
  [['palačink', 'lívanc', 'pancake'], 'palacinky'],
  [['smoothie', 'koktejl', 'shake'], 'smoothie'],
  [['jogurt', 'yogurt', 'granola'], 'jogurt'],
  [['vajíčk', 'omeleta', 'míchan', 'vejce', 'egg'], 'vajicka'],
  [['toast', 'sendvič', 'sandwich', 'chléb', 'bageta'], 'toast-sendvic'],
  [['polévk', 'soup', 'vývar', 'krém z'], 'polevka'],
  [['salát', 'salad'], 'salat'],
  [['těstovin', 'pasta', 'špaget', 'penne', 'fusilli', 'lasagn', 'gnocchi'], 'testoviny'],
  [['pizza', 'focaccia'], 'pizza'],
  [['burger', 'hamburger'], 'burger'],
  [['wrap', 'tortill', 'burrito', 'quesadilla', 'taco'], 'wrap'],
  [['guláš', 'goulash', 'dušen'], 'gulas'],
  [['knedlík', 'svíčkov', 'bramborák'], 'knedliky'],
  [['rizoto', 'risotto'], 'rizoto'],
  [['wok', 'stir-fry', 'asij', 'teriyaki', 'pad thai', 'curry', 'nudle'], 'wok'],
  [['tofu', 'tempeh'], 'tofu'],
  [['čočk', 'fazol', 'cizrn', 'luštěnin', 'hummus'], 'lusteniny'],
  [['vegan', 'buddha bowl', 'quinoa bowl'], 'vegan-miska'],
  [['zapékan', 'gratin', 'zapečen'], 'zapekanka'],
  [['losos', 'salmon', 'tresk', 'filé', 'ryba', 'rybí', 'tuňák', 'pstruh', 'kapr', 'mořsk', 'krevet'], 'ryba'],
  [['hovězí', 'beef', 'steak', 'tatarák'], 'hovezi'],
  [['vepřov', 'pork', 'koleno', 'řízek', 'schnitzel'], 'veprove'],
  [['mlet', 'bolognese', 'boloňsk', 'karbanát', 'sekaná'], 'mlete-maso'],
  [['kuřec', 'chicken', 'drůbež', 'krůt'], 'kure'],
  [['brambor', 'potato', 'pyré', 'hranolk'], 'brambory'],
  [['dezert', 'dort', 'cake', 'čokolád', 'koláč', 'muffin', 'brownie', 'tiramisu'], 'dezert'],
  [['ovoc', 'fruit', 'jablk', 'banán', 'mango'], 'ovoce'],
  [['svačin', 'snack', 'tyčink', 'ořech', 'mandle'], 'svacina'],
];

function guessCategory(name: string): string {
  const lower = name.toLowerCase();
  for (const [keywords, category] of KEYWORD_RULES) {
    for (const kw of keywords) {
      if (lower.includes(kw)) return category;
    }
  }
  return FALLBACK_CATEGORY;
}

export function getFoodImageUrl(category?: string, mealName?: string): string {
  const slug = category || (mealName ? guessCategory(mealName) : FALLBACK_CATEGORY);
  return `/static/food-images/${slug}.webp`;
}
