"""
Tests for diet_planner.services.recipe_coherence.

This module exists because of a real production bug: plan 108, recipe
108:1:dinner:0 told the user "the beef (klizka) is already prepared"
while charging them 89 CZK for 300 g of fresh klizka on the shopping
list. These tests pin down the multilingual phrase detection and the
end-to-end issue-finding logic so the bug cannot regress silently.

We use SimpleTestCase — no DB needed. The functions under test are pure.
"""
from django.test import SimpleTestCase

from diet_planner.services.recipe_coherence import (
    detect_pre_prepared_ingredient_names,
    filter_pre_prepared,
    find_coherence_issues,
)


def _meal(name, description, ingredients, instructions=None):
    return {
        "name": name,
        "description": description,
        "ingredients": ingredients,
        "instructions": instructions or [],
    }


class DetectPrePreparedIngredientNamesTest(SimpleTestCase):
    # ----- Czech: the actual production bug -----

    def test_klizka_already_prepared_czech(self):
        meal = _meal(
            "Hovězí na cibulce",
            "Hovězí maso (klizka) je již připravené z předchozího dne.",
            [{"name": "klizka", "quantity": 300, "unit": "g"},
             {"name": "cibule", "quantity": 100, "unit": "g"}],
        )
        flagged = detect_pre_prepared_ingredient_names(meal)
        self.assertIn("klizka", flagged)
        self.assertNotIn("cibule", flagged)

    def test_zbytek_z_vcerejska(self):
        meal = _meal(
            "Rýže s kuřetem",
            "Zbytek z včerejška: kuře nakrájejte na kousky.",
            [{"name": "kuře", "quantity": 200, "unit": "g"},
             {"name": "rýže", "quantity": 80, "unit": "g"}],
        )
        flagged = detect_pre_prepared_ingredient_names(meal)
        self.assertIn("kuře", flagged)
        self.assertNotIn("rýže", flagged)

    # ----- English -----

    def test_english_leftover(self):
        meal = _meal(
            "Beef stir-fry",
            "Use leftover beef from yesterday's dinner.",
            [{"name": "beef", "quantity": 300, "unit": "g"},
             {"name": "soy sauce", "quantity": 20, "unit": "ml"}],
        )
        flagged = detect_pre_prepared_ingredient_names(meal)
        self.assertIn("beef", flagged)
        self.assertNotIn("soy sauce", flagged)

    def test_english_already_cooked(self):
        meal = _meal(
            "Chicken salad",
            "The chicken is already cooked.",
            [{"name": "chicken", "quantity": 150, "unit": "g"},
             {"name": "lettuce", "quantity": 80, "unit": "g"}],
        )
        flagged = detect_pre_prepared_ingredient_names(meal)
        self.assertEqual(flagged, {"chicken"})

    # ----- Other supported languages -----

    def test_polish_resztki(self):
        meal = _meal(
            "Kurczak z ryżem",
            "Resztki z poprzedniego dnia: kurczak.",
            [{"name": "kurczak", "quantity": 200, "unit": "g"},
             {"name": "ryż", "quantity": 80, "unit": "g"}],
        )
        flagged = detect_pre_prepared_ingredient_names(meal)
        self.assertIn("kurczak", flagged)
        self.assertNotIn("ryż", flagged)

    def test_german_vom_vortag(self):
        meal = _meal(
            "Rindfleisch-Pfanne",
            "Rindfleisch vom Vortag verwenden.",
            [{"name": "rindfleisch", "quantity": 300, "unit": "g"},
             {"name": "zwiebel", "quantity": 100, "unit": "g"}],
        )
        flagged = detect_pre_prepared_ingredient_names(meal)
        self.assertIn("rindfleisch", flagged)
        self.assertNotIn("zwiebel", flagged)

    # ----- Negative: prep work the user is about to do should not match -----

    def test_does_not_match_active_prep_work(self):
        meal = _meal(
            "Bean stew",
            "Soak the beans overnight — preparation is done in advance.",
            [{"name": "beans", "quantity": 200, "unit": "g"}],
        )
        # "prepared ... in advance" + "soak" -> active prep, not pre-prepared.
        # Our detector explicitly excludes sentences containing prep-verb hints.
        flagged = detect_pre_prepared_ingredient_names(meal)
        self.assertEqual(flagged, set())

    def test_no_pre_prepared_marker_no_match(self):
        meal = _meal(
            "Omelette",
            "Whisk eggs, season with salt, fry in butter.",
            [{"name": "eggs", "quantity": 2, "unit": "ks"},
             {"name": "butter", "quantity": 10, "unit": "g"}],
        )
        self.assertEqual(detect_pre_prepared_ingredient_names(meal), set())

    # ----- Explicit boolean flag from the LLM -----

    def test_explicit_pre_prepared_flag_filters_even_without_text(self):
        meal = _meal(
            "Beef bowl",
            "Assemble the bowl.",
            [{"name": "beef", "quantity": 200, "unit": "g", "pre_prepared": True},
             {"name": "rice", "quantity": 80, "unit": "g"}],
        )
        filtered = filter_pre_prepared(meal)
        kept = [i["name"] for i in filtered["ingredients"]]
        self.assertEqual(kept, ["rice"])
        self.assertEqual(
            [i["name"] for i in filtered["pre_prepared_ingredients"]],
            ["beef"],
        )


class FilterPrePreparedTest(SimpleTestCase):
    def test_filters_klizka_off_ingredients(self):
        meal = _meal(
            "Hovězí na cibulce",
            "Hovězí maso (klizka) je již připravené z předchozího dne.",
            [{"name": "klizka", "quantity": 300, "unit": "g"},
             {"name": "cibule", "quantity": 100, "unit": "g"}],
        )
        filtered = filter_pre_prepared(meal)
        self.assertEqual([i["name"] for i in filtered["ingredients"]], ["cibule"])
        self.assertEqual(
            [i["name"] for i in filtered["pre_prepared_ingredients"]],
            ["klizka"],
        )

    def test_preserves_meal_when_nothing_flagged(self):
        meal = _meal(
            "Omelette",
            "Whisk eggs and fry in butter.",
            [{"name": "eggs", "quantity": 2, "unit": "ks"},
             {"name": "butter", "quantity": 10, "unit": "g"}],
        )
        filtered = filter_pre_prepared(meal)
        self.assertEqual(
            [i["name"] for i in filtered["ingredients"]],
            ["eggs", "butter"],
        )
        self.assertNotIn("pre_prepared_ingredients", filtered)

    def test_robust_to_missing_fields(self):
        # Should not crash on minimal / malformed input.
        self.assertEqual(filter_pre_prepared({})["ingredients"], [])
        self.assertEqual(filter_pre_prepared({"ingredients": []})["ingredients"], [])


class FindCoherenceIssuesTest(SimpleTestCase):
    def test_finds_the_klizka_bug(self):
        days = [{
            "day_number": 1,
            "dinner": {
                "name": "Hovězí na cibulce",
                "description": "Hovězí maso (klizka) je již připravené z předchozího dne.",
                "ingredients": [{"name": "klizka", "quantity": 300, "unit": "g"}],
            },
        }]
        shopping_list = [{"ingredient": "klizka", "quantity": 300, "unit": "g", "price": 89.9}]
        issues = find_coherence_issues(days, shopping_list)
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0]["ingredient"], "klizka")
        self.assertEqual(issues[0]["meal_type"], "dinner")
        self.assertEqual(issues[0]["day_number"], 1)

    def test_substring_match_hovezi_klizka_vs_klizka(self):
        # Shopping list says "hovězí klizka", recipe ingredient is "klizka".
        days = [{
            "day_number": 2,
            "dinner": {
                "name": "Beef stew",
                "description": "Use leftover klizka from yesterday.",
                "ingredients": [{"name": "klizka", "quantity": 300, "unit": "g"}],
            },
        }]
        shopping_list = [{"ingredient": "hovězí klizka", "price": 95.0}]
        issues = find_coherence_issues(days, shopping_list)
        self.assertEqual(len(issues), 1)

    def test_clean_plan_has_no_issues(self):
        days = [{
            "day_number": 1,
            "breakfast": {
                "name": "Omelette",
                "description": "Whisk eggs, fry in butter.",
                "ingredients": [{"name": "eggs", "quantity": 2}],
            },
        }]
        shopping_list = [{"ingredient": "eggs", "quantity": 2, "price": 6.0}]
        self.assertEqual(find_coherence_issues(days, shopping_list), [])

    def test_handles_empty_inputs(self):
        self.assertEqual(find_coherence_issues([], []), [])
        self.assertEqual(find_coherence_issues(None, None), [])
