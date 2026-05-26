FOOD_CATEGORIES = {
    'ovesna-kase': {
        'name': 'Ovesná kaše a müsli',
        'prompt': 'A warm bowl of oatmeal porridge topped with fresh berries, honey drizzle, and nuts',
    },
    'vajicka': {
        'name': 'Vaječné pokrmy',
        'prompt': 'Scrambled eggs with herbs on a plate, golden and fluffy, with toast on the side',
    },
    'toast-sendvic': {
        'name': 'Toasty a sendviče',
        'prompt': 'Open-faced avocado toast with seeds and microgreens on sourdough bread',
    },
    'smoothie': {
        'name': 'Smoothie a koktejly',
        'prompt': 'A thick berry smoothie in a glass with fresh fruit garnish and a straw',
    },
    'palacinky': {
        'name': 'Palačinky a lívance',
        'prompt': 'A stack of golden pancakes with maple syrup, berries, and powdered sugar',
    },
    'jogurt': {
        'name': 'Jogurt a granola',
        'prompt': 'Greek yogurt bowl with granola, fresh fruit, and honey drizzle',
    },
    'polevka': {
        'name': 'Polévky',
        'prompt': 'A steaming bowl of creamy vegetable soup with a swirl of cream and herbs',
    },
    'salat': {
        'name': 'Saláty',
        'prompt': 'A vibrant mixed green salad with cherry tomatoes, cucumber, and vinaigrette',
    },
    'testoviny': {
        'name': 'Těstoviny',
        'prompt': 'A plate of spaghetti with rich tomato sauce, fresh basil, and parmesan',
    },
    'kure': {
        'name': 'Kuřecí pokrmy',
        'prompt': 'Grilled chicken breast sliced on a plate with roasted vegetables and herbs',
    },
    'hovezi': {
        'name': 'Hovězí pokrmy',
        'prompt': 'Tender beef steak sliced on a wooden board with roasted potatoes and greens',
    },
    'veprove': {
        'name': 'Vepřové pokrmy',
        'prompt': 'Juicy pork chop with crispy golden crust, served with mashed potatoes and gravy',
    },
    'ryba': {
        'name': 'Rybí pokrmy',
        'prompt': 'Pan-seared salmon fillet with lemon, asparagus, and a light sauce',
    },
    'mlete-maso': {
        'name': 'Mleté maso',
        'prompt': 'Bolognese sauce with ground meat over pasta, garnished with parmesan and basil',
    },
    'gulas': {
        'name': 'Guláš a dušená masa',
        'prompt': 'A hearty bowl of beef goulash with rich dark sauce, bread dumplings on the side',
    },
    'rizoto': {
        'name': 'Rizoto a rýžové pokrmy',
        'prompt': 'Creamy mushroom risotto in a bowl, garnished with parmesan and fresh parsley',
    },
    'wok': {
        'name': 'Asijské pokrmy',
        'prompt': 'Colorful stir-fry with vegetables and chicken in a wok, served with rice',
    },
    'zapekanka': {
        'name': 'Zapékanky a gratiny',
        'prompt': 'A golden-topped casserole dish fresh from the oven with melted cheese bubbling',
    },
    'vegan-miska': {
        'name': 'Veganské misky',
        'prompt': 'A colorful Buddha bowl with quinoa, roasted chickpeas, avocado, and tahini dressing',
    },
    'tofu': {
        'name': 'Tofu a tempeh',
        'prompt': 'Crispy fried tofu cubes with sesame seeds, stir-fried vegetables, and soy glaze',
    },
    'lusteniny': {
        'name': 'Luštěniny',
        'prompt': 'A rustic bowl of lentil stew with carrots, celery, and crusty bread on the side',
    },
    'burger': {
        'name': 'Burgery',
        'prompt': 'A gourmet burger with lettuce, tomato, melted cheese, and a brioche bun',
    },
    'wrap': {
        'name': 'Wrapy a tortilly',
        'prompt': 'A sliced chicken wrap with fresh vegetables, sauce, and herbs visible inside',
    },
    'pizza': {
        'name': 'Pizza',
        'prompt': 'A freshly baked margherita pizza with bubbling mozzarella, basil, and tomato sauce',
    },
    'brambory': {
        'name': 'Bramborové pokrmy',
        'prompt': 'Golden roasted potatoes with rosemary and garlic, crispy on the outside',
    },
    'dezert': {
        'name': 'Dezerty',
        'prompt': 'A slice of chocolate cake with ganache, fresh raspberries, and powdered sugar',
    },
    'ovoce': {
        'name': 'Ovocné pokrmy',
        'prompt': 'A colorful fruit plate with sliced mango, strawberries, kiwi, and blueberries',
    },
    'svacina': {
        'name': 'Svačiny',
        'prompt': 'A snack plate with hummus, vegetable sticks, crackers, and mixed nuts',
    },
    'knedliky': {
        'name': 'Knedlíky a české pokrmy',
        'prompt': 'Traditional Czech dumplings (knedlíky) with roasted pork and sauerkraut',
    },
    'proteinovy-napoj': {
        'name': 'Proteinové nápoje',
        'prompt': 'A creamy protein shake in a tall glass with banana and oat garnish',
    },
}

CATEGORY_CHOICES = [(slug, cat['name']) for slug, cat in FOOD_CATEGORIES.items()]

DEFAULT_CATEGORY = 'kure'

CATEGORY_SLUGS = list(FOOD_CATEGORIES.keys())
