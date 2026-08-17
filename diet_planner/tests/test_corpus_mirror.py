"""Round-trip the published corpus so the farm can run off-prod."""
import json
import os
import tempfile
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from diet_planner.models import CuratedRecipe


def _recipe(slug, status=CuratedRecipe.Status.PUBLISHED, **kw):
    defaults = dict(
        slug=slug, name_cs=slug, meal_types=['dinner'], base_servings=2,
        source_url=f'https://example.com/{slug}', source_name='Example',
        status=status,
        ingredients=[{'name': 'sůl', 'canonical': 'salt', 'quantity': 5, 'unit': 'g'}],
        instructions=[{'text': 'Uvařte.'}],
    )
    defaults.update(kw)
    return CuratedRecipe.objects.create(**defaults)


class CorpusMirrorTests(TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.path = os.path.join(self.dir, 'corpus.json')

    def test_dump_writes_only_published(self):
        _recipe('published-one')
        _recipe('draft-one', status=CuratedRecipe.Status.DRAFT)
        out = StringIO()
        call_command('dump_curated_corpus', '--output', self.path, stdout=out)
        payload = json.loads(open(self.path, encoding='utf-8').read())
        slugs = [row['fields']['slug'] for row in payload]
        self.assertEqual(slugs, ['published-one'])
        self.assertIn('dumped=1', out.getvalue())

    def test_load_restores_a_deleted_corpus(self):
        _recipe('published-one', name_cs='Svíčková')
        call_command('dump_curated_corpus', '--output', self.path, stdout=StringIO())
        CuratedRecipe.objects.all().delete()

        call_command('load_curated_corpus', '--input', self.path, stdout=StringIO())
        restored = CuratedRecipe.objects.get(slug='published-one')
        self.assertEqual(restored.name_cs, 'Svíčková')
        self.assertEqual(restored.status, CuratedRecipe.Status.PUBLISHED)

    def test_load_drops_the_chat_user_link(self):
        """created_for_user points at a prod User row that does not exist
        locally; keeping the id would break the FK on load."""
        from django.contrib.auth import get_user_model
        user = get_user_model().objects.create_user(
            username='someone', email='someone@example.com', password='x')
        _recipe('published-one', created_for_user=user)
        call_command('dump_curated_corpus', '--output', self.path, stdout=StringIO())
        CuratedRecipe.objects.all().delete()
        user.delete()

        call_command('load_curated_corpus', '--input', self.path, stdout=StringIO())
        self.assertIsNone(
            CuratedRecipe.objects.get(slug='published-one').created_for_user_id)

    def test_load_flush_replaces_existing_rows(self):
        _recipe('published-one')
        call_command('dump_curated_corpus', '--output', self.path, stdout=StringIO())
        _recipe('stale-local-row')

        call_command('load_curated_corpus', '--input', self.path, '--flush',
                     stdout=StringIO())
        self.assertEqual(
            sorted(CuratedRecipe.objects.values_list('slug', flat=True)),
            ['published-one'])
