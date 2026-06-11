# diet_planner/models/__init__.py
"""
Models package for Diet Planner.

Re-exports all models and constants so existing imports like
`from .models import DietaryGoal` continue to work unchanged.
"""
from .core import (  # noqa: F401
    # Constants
    COUNTRY_CURRENCY_MAP,
    SHOP_CHOICES,
    SHOP_TO_SOURCE_URL,
    COUNTRY_TO_SHOPS,
    # Utility functions
    get_currency_for_country,
    get_shops_for_country,
    # Models
    HistoricNutritionPlan,
    DietaryGoal,
    DietaryPlan,
    LeafletOffer,
    Recipe,
    MealInstance,
    PriceFeedback,
)

from .catalog import (  # noqa: F401
    GroceryStore,
    CanonicalIngredient,
    IngredientAlias,
    IngredientSubstitute,
    StoreProduct,
)

from .pricing import (  # noqa: F401
    PriceSourceType,
    PriceRecord,
    PriceFreshnessPolicy,
)

from .scraping import (  # noqa: F401
    ScrapeRun,
)

from .curated import (  # noqa: F401
    CuratedRecipe,
)
