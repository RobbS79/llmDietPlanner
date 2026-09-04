import io
import os
import re
from pathlib import Path

from django.test import SimpleTestCase
from PIL import Image, ImageChops, ImageStat

from social.cards import CANVAS, PALETTE, render_card

GOLDEN = Path(__file__).parent / 'golden'
WRITE = os.environ.get('SOCIAL_WRITE_GOLDEN') == '1'

DEALS = {
    'kind': 'deals', 'iso_week': '2026-W37',
    'deals': [{'ingredient': 'cibule', 'shop': 'Lidl', 'valid_until': '2026-09-13'},
              {'ingredient': 'mrkev', 'shop': 'Albert', 'valid_until': '2026-09-10'},
              {'ingredient': 'vepřová plec', 'shop': 'Lidl', 'valid_until': '2026-09-13'},
              {'ingredient': 'brambory', 'shop': 'Kaufland', 'valid_until': '2026-09-12'}],
    'recipes': [{'name': 'Vepřové s cibulí', 'url': 'https://eatalnicek.eu/recepty/1/x/', 'matched': 2, 'total': 4}],
    'link': 'https://eatalnicek.eu/?utm_source={channel}',
}
RECIPE = {
    'kind': 'recipe', 'iso_week': '2026-W37', 'recipe_id': 1,
    'name': 'Vepřová plec na česneku s bramborovým pyré a dušeným špenátem',
    'kcal': 612, 'minutes': 75, 'servings': 4, 'source_name': 'Apetit',
    'source_url': 'https://apetit.cz', 'deals_matched': 3, 'deals_total': 7,
    'deal_shops': ['Lidl'], 'image_url': 'https://eatalnicek.eu/static/x.webp',
    'link': 'https://eatalnicek.eu/recepty/1/x/?utm_source={channel}',
}
SHOWCASE = {
    'kind': 'showcase', 'iso_week': '2026-W37', 'goal_id': 1,
    'prompt': 'Rodina se dvěma dětmi, chceme levně a jednoduše, klasická česká kuchyně.',
    'meals': [{'slot': 'breakfast', 'name': 'Ovesná kaše s jablky', 'kcal': 350, 'deals_matched': 1},
              {'slot': 'lunch', 'name': 'Kuřecí rizoto', 'kcal': 620, 'deals_matched': 0},
              {'slot': 'dinner', 'name': 'Zeleninová polévka s krupicovými noky', 'kcal': 280, 'deals_matched': 2}],
    'total_kcal': 1250, 'link': 'https://eatalnicek.eu/?utm_source={channel}',
}


def _photo() -> bytes:
    img = Image.new('RGB', (800, 600), (180, 90, 40))
    buf = io.BytesIO()
    img.save(buf, format='WEBP')
    return buf.getvalue()


def _assert_matches_golden(test, name: str, png: bytes):
    path = GOLDEN / f'{name}.png'
    if WRITE:
        GOLDEN.mkdir(exist_ok=True)
        path.write_bytes(png)
        return
    test.assertTrue(path.exists(), f'{path} missing — run with SOCIAL_WRITE_GOLDEN=1 once, inspect, commit')
    actual = Image.open(io.BytesIO(png)).convert('RGB')
    expected = Image.open(path).convert('RGB')
    test.assertEqual(actual.size, expected.size)
    diff = ImageChops.difference(actual, expected)
    mean = sum(ImageStat.Stat(diff).mean) / 3
    test.assertLess(mean, 4.0, f'{name} drifted from golden (mean diff {mean:.2f})')


class CardTests(SimpleTestCase):
    def test_canvas_is_portrait_4_5(self):
        self.assertEqual(CANVAS, (1080, 1350))

    def test_palette_matches_tailwind_config(self):
        css = Path(__file__).resolve().parents[2] / 'frontend' / 'tailwind.config.js'
        text = css.read_text()
        for token, value in [('paper', PALETTE['paper']), ('ink', PALETTE['ink'])]:
            self.assertRegex(text, rf"{token}:\s*'{value}'", f'{token} drifted from tailwind')
        self.assertRegex(text, rf"paprika:\s*\{{\s*DEFAULT:\s*'{PALETTE['paprika']}'")
        self.assertRegex(text, rf"green:\s*\{{\s*DEFAULT:\s*'{PALETTE['green']}'")

    def test_recipe_card_renders_and_matches_golden(self):
        png = render_card('recipe', RECIPE, photo=_photo())
        img = Image.open(io.BytesIO(png))
        self.assertEqual(img.size, CANVAS)
        self.assertEqual(img.format, 'PNG')
        _assert_matches_golden(self, 'recipe', png)

    def test_recipe_card_without_optional_fields(self):
        facts = {**RECIPE, 'kcal': None, 'minutes': None, 'deals_matched': 0, 'source_name': ''}
        png = render_card('recipe', facts, photo=_photo())
        self.assertEqual(Image.open(io.BytesIO(png)).size, CANVAS)

    def test_deals_card_matches_golden(self):
        _assert_matches_golden(self, 'deals', render_card('deals', DEALS))

    def test_showcase_card_matches_golden(self):
        _assert_matches_golden(self, 'showcase', render_card('showcase', SHOWCASE))

    def test_unknown_kind_raises(self):
        with self.assertRaises(ValueError):
            render_card('nope', {})
