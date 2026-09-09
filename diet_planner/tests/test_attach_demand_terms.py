"""attach_demand_terms: copies the demand map onto CuratedRecipe rows."""
import json
import tempfile
from io import StringIO
from pathlib import Path

import yaml
from django.core.management import call_command
from django.test import TestCase

from diet_planner.models import CuratedRecipe


def _recipe(slug, name_cs, **kw):
    defaults = dict(
        slug=slug, name_cs=name_cs, meal_types=['lunch', 'dinner'], ingredients=[], instructions=[],
        source_url=f'https://example.com/{slug}', source_name='Example',
        status=CuratedRecipe.Status.PUBLISHED,
    )
    defaults.update(kw)
    return CuratedRecipe.objects.create(**defaults)


class DemandFieldsTests(TestCase):
    def test_new_rows_carry_null_demand_fields(self):
        r = _recipe('x', 'X')
        self.assertEqual(r.demand_term, '')
        self.assertIsNone(r.demand_score)
        self.assertIsNone(r.demand_peak_month)
        self.assertIsNone(r.owner_rating)
