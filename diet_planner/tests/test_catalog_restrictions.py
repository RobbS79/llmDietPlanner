"""CatalogService now consumes ResolvedRestrictions instead of reading
goal.dietary_restrictions directly."""
from unittest.mock import MagicMock

from diet_planner.services.catalog import CatalogService
from diet_planner.services.restrictions import ResolvedRestrictions


def _goal():
    g = MagicMock()
    g.id = 1
    g.shop = "rohlik"
    g.dietary_restrictions = ""  # intentionally empty
    g.prompt = "bezlepkový týden"
    return g


class TestCatalogConsumesResolvedRestrictions:
    def test_filter_uses_exclusions_argument_not_goal_field(self, monkeypatch):
        # Stub _load_products so we don't need the DB
        flour = {"name": "pšeničná mouka", "display_name": "Hladká mouka"}
        chicken = {"name": "kuřecí prsa", "display_name": "Kuřecí prso"}
        rice = {"name": "rýže", "display_name": "Basmati rýže"}
        monkeypatch.setattr(
            CatalogService,
            "_load_products",
            lambda self, goal: [flour, chicken, rice],
        )
        monkeypatch.setattr(
            CatalogService,
            "_get_pantry_staples",
            lambda self, goal: [],
        )

        exclusions = ResolvedRestrictions(
            tags=frozenset({"gluten_free"}),
            exclusion_keywords=frozenset({"mouka", "flour"}),
            freeform_allergens=frozenset(),
        )
        result = CatalogService().build_catalog_for_prompt(
            _goal(), exclusions=exclusions
        )

        flat = [
            p for items in result["products_by_category"].values() for p in items
        ]
        names = [p["name"] for p in flat]
        assert "kuřecí prsa" in names
        assert "rýže" in names
        assert "pšeničná mouka" not in names  # filtered out

    def test_no_exclusions_returns_unfiltered(self, monkeypatch):
        flour = {"name": "pšeničná mouka", "display_name": "Hladká mouka"}
        monkeypatch.setattr(CatalogService, "_load_products", lambda self, goal: [flour])
        monkeypatch.setattr(CatalogService, "_get_pantry_staples", lambda self, goal: [])

        result = CatalogService().build_catalog_for_prompt(_goal(), exclusions=None)
        flat = [p for items in result["products_by_category"].values() for p in items]
        assert any(p["name"] == "pšeničná mouka" for p in flat)
