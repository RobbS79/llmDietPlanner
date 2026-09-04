"""Branded 1080×1350 cards rendered with Pillow only — no generated imagery,
so nothing in a picture can be false. Palette and fonts mirror the public
site's Market Paper theme (frontend/tailwind.config.js); a test fails if
the hex values drift."""
from __future__ import annotations

import io
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFont, ImageOps

CANVAS = (1080, 1350)
PALETTE = {
    'paper': '#F7F3EC',
    'kraft': '#EFE7D8',
    'line': '#E4DAC8',
    'ink': '#241E1A',
    'muted': '#5E564C',
    'paprika': '#DB5026',
    'paprika_soft': '#FBE6DC',
    'green': '#2E6B43',
    'green_soft': '#E7F0E8',
    'white': '#FFFFFF',
}
FONT_DIR = Path(__file__).parent / 'fonts'
MARGIN = 72
WORDMARK = 'Vařto'


# ------------------------------------------------------------ fonts & text

def _font(kind: str, size: int, weight: int = 400) -> ImageFont.FreeTypeFont:
    path = FONT_DIR / ('BricolageGrotesque.ttf' if kind == 'display' else 'HankenGrotesk.ttf')
    font = ImageFont.truetype(str(path), size)
    try:
        axes = font.get_variation_axes()
        values = []
        for axis in axes:
            name = axis['name']
            if name in (b'Weight', 'Weight'):
                values.append(weight)
            elif name in (b'Optical size', 'Optical size'):
                values.append(min(max(size, axis['minimum']), axis['maximum']))
            else:
                values.append(axis['default'])
        font.set_variation_by_axes(values)
    except Exception:
        pass   # static FreeType build: default instance is fine
    return font


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> list:
    words, lines, current = text.split(), [], ''
    for word in words:
        trial = f'{current} {word}'.strip()
        if draw.textlength(trial, font=font) <= max_width or not current:
            current = trial
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def _fit_text(draw, text, kind, max_width, max_lines, size, min_size, weight=400):
    """Shrink the font until the text fits in max_lines; return (font, lines)."""
    while True:
        font = _font(kind, size, weight)
        lines = _wrap(draw, text, font, max_width)
        if len(lines) <= max_lines or size <= min_size:
            if len(lines) > max_lines:
                lines = lines[:max_lines]
                lines[-1] = lines[-1].rstrip('.,;') + '…'
            return font, lines
        size -= 4


def _ellipsize(draw, text: str, font, max_width: int) -> str:
    """Trim a single line to max_width, ending in an ellipsis if it had to give."""
    if draw.textlength(text, font=font) <= max_width:
        return text
    trimmed = text
    while trimmed and draw.textlength(trimmed + '…', font=font) > max_width:
        trimmed = trimmed[:-1]
    return trimmed.rstrip(' ,;') + '…'


def _draw_lines(draw, lines, font, x, y, fill, line_gap=1.15) -> int:
    height = font.size * line_gap
    for line in lines:
        draw.text((x, y), line, font=font, fill=fill)
        y += height
    return int(y)


def _badge(draw, text, x, y, fill, bg, font):
    pad_x, pad_y = 18, 10
    w = draw.textlength(text, font=font)
    h = font.size
    draw.rounded_rectangle([x, y, x + w + 2 * pad_x, y + h + 2 * pad_y], radius=14, fill=bg)
    draw.text((x + pad_x, y + pad_y - 2), text, font=font, fill=fill)
    return int(x + w + 2 * pad_x)


def _wordmark(draw, img):
    font = _font('display', 40, 700)
    w = draw.textlength(WORDMARK, font=font)
    draw.text((CANVAS[0] - MARGIN - w, CANVAS[1] - MARGIN - 40), WORDMARK,
              font=font, fill=PALETTE['paprika'])
    draw.text((MARGIN, CANVAS[1] - MARGIN - 30), 'eatalnicek.eu',
              font=_font('body', 26, 500), fill=PALETTE['muted'])


def _new_canvas():
    img = Image.new('RGB', CANVAS, PALETTE['paper'])
    return img, ImageDraw.Draw(img)


def _to_png(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format='PNG', optimize=True)
    return buf.getvalue()


# ------------------------------------------------------------ recipe card

def _recipe_card(facts: dict, photo: bytes) -> bytes:
    img, draw = _new_canvas()
    photo_h = int(CANVAS[1] * 0.55)
    src = Image.open(io.BytesIO(photo)).convert('RGB')
    img.paste(ImageOps.fit(src, (CANVAS[0], photo_h), method=Image.LANCZOS), (0, 0))
    draw = ImageDraw.Draw(img)

    y = photo_h + 56
    if facts.get('deals_matched'):
        n = facts['deals_matched']
        word = 'surovina' if n == 1 else 'suroviny' if n < 5 else 'surovin'
        _badge(draw, f'{n} {word} ve slevě tento týden', MARGIN, y,
               PALETTE['green'], PALETTE['green_soft'], _font('body', 28, 600))
        y += 76

    font, lines = _fit_text(draw, facts['name'], 'display', CANVAS[0] - 2 * MARGIN,
                            max_lines=3, size=72, min_size=44, weight=700)
    y = _draw_lines(draw, lines, font, MARGIN, y, PALETTE['ink'], 1.08) + 20

    meta = []
    if facts.get('kcal'):
        meta.append(f"{facts['kcal']} kcal / porce")
    if facts.get('minutes'):
        meta.append(f"{facts['minutes']} min")
    if meta:
        draw.text((MARGIN, y), '  ·  '.join(meta), font=_font('body', 34, 500), fill=PALETTE['muted'])
        y += 52
    if facts.get('source_name'):
        draw.text((MARGIN, y), f"Zdroj receptu: {facts['source_name']}",
                  font=_font('body', 26, 400), fill=PALETTE['muted'])
    _wordmark(draw, img)
    return _to_png(img)


# ------------------------------------------------------------ deals card

def _deals_card(facts: dict) -> bytes:
    img, draw = _new_canvas()
    y = MARGIN + 20
    draw.text((MARGIN, y), 'TENHLE TÝDEN V AKCI', font=_font('body', 28, 600), fill=PALETTE['paprika'])
    y += 50
    font, lines = _fit_text(draw, 'Suroviny ve slevě podle letáků', 'display',
                            CANVAS[0] - 2 * MARGIN, 2, 68, 48, 700)
    y = _draw_lines(draw, lines, font, MARGIN, y, PALETTE['ink'], 1.08) + 36

    name_font, shop_font = _font('display', 44, 600), _font('body', 30, 500)
    rows = facts['deals'][:8]
    # Spread a short list over the free height instead of leaving half the card blank,
    # but never past the footer: `step` is the whole row pitch, divider included.
    free = (CANVAS[1] - MARGIN - 110) - y - (110 if facts.get('recipes') else 0)
    step = max(98, min(150, free // max(len(rows), 1)))
    for deal in rows:
        draw.line([(MARGIN, y), (CANVAS[0] - MARGIN, y)], fill=PALETTE['line'], width=2)
        shop = deal['shop']
        w = draw.textlength(shop, font=shop_font)
        name = _ellipsize(draw, deal['ingredient'], name_font,
                          CANVAS[0] - 2 * MARGIN - w - 40)
        draw.text((MARGIN, y + 22), name, font=name_font, fill=PALETTE['ink'])
        draw.text((CANVAS[0] - MARGIN - w, y + 32), shop, font=shop_font, fill=PALETTE['muted'])
        y += step
    if rows:
        draw.line([(MARGIN, y), (CANVAS[0] - MARGIN, y)], fill=PALETTE['line'], width=2)

    if facts.get('recipes'):
        y += 24
        r = facts['recipes'][0]
        badge_font = _font('body', 26, 600)
        text = _ellipsize(draw, f"Recept: {r['name']} — {r['matched']} z {r['total']} surovin ve slevě",
                          badge_font, CANVAS[0] - 2 * MARGIN - 36)
        _badge(draw, text, MARGIN, y, PALETTE['green'], PALETTE['green_soft'], badge_font)
    _wordmark(draw, img)
    return _to_png(img)


# ------------------------------------------------------------ showcase card

SLOT_LABELS = {'breakfast': 'Snídaně', 'lunch': 'Oběd', 'dinner': 'Večeře'}
NUMBERS_COLUMN = 230   # right-hand strip reserved for kcal + deals badge
MEAL_CARD_H = 164


def _showcase_card(facts: dict) -> bytes:
    img, draw = _new_canvas()
    y = MARGIN + 20
    draw.text((MARGIN, y), 'UŽIVATEL NAPSAL', font=_font('body', 28, 600), fill=PALETTE['paprika'])
    y += 50
    font, lines = _fit_text(draw, f'„{facts["prompt"]}“', 'display',
                            CANVAS[0] - 2 * MARGIN, 4, 56, 40, 600)
    y = _draw_lines(draw, lines, font, MARGIN, y, PALETTE['ink'], 1.12) + 40
    draw.text((MARGIN, y), 'VAŘTO SESTAVILO', font=_font('body', 28, 600), fill=PALETTE['green'])
    y += 56

    label_font, meal_font, kcal_font = _font('body', 26, 600), _font('display', 40, 600), _font('body', 28, 500)
    for meal in facts['meals']:
        draw.rounded_rectangle([MARGIN, y, CANVAS[0] - MARGIN, y + MEAL_CARD_H], radius=20, fill=PALETTE['white'],
                               outline=PALETTE['line'], width=2)
        draw.text((MARGIN + 28, y + 20), SLOT_LABELS.get(meal['slot'], meal['slot']).upper(),
                  font=label_font, fill=PALETTE['muted'])
        name_width = CANVAS[0] - 2 * MARGIN - 56 - NUMBERS_COLUMN
        f, ls = _fit_text(draw, meal['name'], 'display', name_width, 2, 40, 30, 600)
        _draw_lines(draw, ls, f, MARGIN + 28, y + 54, PALETTE['ink'], 1.05)
        right = CANVAS[0] - MARGIN - 28
        if meal.get('kcal'):
            text = f"{meal['kcal']} kcal"
            draw.text((right - draw.textlength(text, font=kcal_font), y + 20), text,
                      font=kcal_font, fill=PALETTE['muted'])
        if meal.get('deals_matched'):
            badge_font = _font('body', 22, 600)
            text = f"{meal['deals_matched']} ve slevě"
            w = draw.textlength(text, font=badge_font) + 36
            _badge(draw, text, right - w, y + 62, PALETTE['green'], PALETTE['green_soft'], badge_font)
        y += MEAL_CARD_H + 20

    if facts.get('total_kcal'):
        draw.text((MARGIN, y + 10), f"Celkem {facts['total_kcal']} kcal za den",
                  font=_font('body', 30, 500), fill=PALETTE['muted'])
    _wordmark(draw, img)
    return _to_png(img)


# ------------------------------------------------------------ dispatch

def render_card(kind: str, facts: dict, photo: Optional[bytes] = None) -> bytes:
    if kind == 'recipe':
        if photo is None:
            raise ValueError('recipe card needs the recipe photo bytes')
        return _recipe_card(facts, photo)
    if kind == 'deals':
        return _deals_card(facts)
    if kind == 'showcase':
        return _showcase_card(facts)
    raise ValueError(f'unknown card kind {kind!r}')
