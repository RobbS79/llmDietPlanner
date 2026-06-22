"""aggregate_ingredients_from_meals must preserve the canonical/catalog_id that
curation pre-mapped onto each ingredient. Without it the pricer falls back to
re-resolving the free-text name, which fails for type-adjective variants
("červené zelí", "hnědá rýže") and silently drops them from the cost estimate.
See [[pricing-catalog-id-resolution]]."""
from django.test import SimpleTestCase

from diet_planner.tasks import aggregate_ingredients_from_meals


class AggregateCanonicalPassthroughTest(SimpleTestCase):
    def test_preserves_canonical_and_catalog_id(self):
        days = [{
            'day_number': 1,
            'lunch': {'ingredients': [
                {'name': 'červené zelí', 'quantity': 300, 'unit': 'g',
                 'canonical': 'red-cabbage', 'catalog_id': 4242},
            ]},
        }]
        items = aggregate_ingredients_from_meals(days)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['ingredient'], 'červené zelí')
        self.assertEqual(items[0].get('canonical'), 'red-cabbage')
        self.assertEqual(items[0].get('catalog_id'), 4242)
