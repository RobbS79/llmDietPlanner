# File: llm_diet_planner_project/views.py
import json
import logging
import re
from datetime import datetime, timezone, timedelta
from functools import lru_cache
from django.http import HttpResponse, Http404
from django.shortcuts import redirect
from django.utils.html import escape
from django.utils.text import slugify
from django.conf import settings

logger = logging.getLogger(__name__)

PRERENDERED_ROUTES = {
    '/': 'index.html',
    '/login': 'login/index.html',
    '/pricing': 'pricing/index.html',
    '/o-nas': 'o-nas/index.html',
    '/privacy': 'privacy/index.html',
    '/terms': 'terms/index.html',
    '/forgot-password': 'forgot-password/index.html',
}

SITE_URL = getattr(settings, 'FRONTEND_URL', 'https://eatalnicek.eu').rstrip('/')


def _get_index_template():
    for base_dir in [settings.STATIC_ROOT, settings.REACT_BUILD_DIR]:
        candidate = base_dir / "index.html"
        if candidate.exists():
            with open(candidate, 'r', encoding='utf-8') as f:
                return f.read()
    return None


def _replace_meta(html, title, description, canonical):
    html = re.sub(r'<title>.*?</title>', f'<title>{escape(title)}</title>', html)
    html = re.sub(r'<meta name="description" content="[^"]*" />', f'<meta name="description" content="{escape(description)}" />', html)
    html = re.sub(r'<link rel="canonical" href="[^"]*" />', f'<link rel="canonical" href="{canonical}" />', html)
    html = re.sub(r'<meta property="og:title" content="[^"]*" />', f'<meta property="og:title" content="{escape(title)}" />', html)
    html = re.sub(r'<meta property="og:description" content="[^"]*" />', f'<meta property="og:description" content="{escape(description)}" />', html)
    html = re.sub(r'<meta property="og:url" content="[^"]*" />', f'<meta property="og:url" content="{canonical}" />', html)
    html = re.sub(r'<meta name="twitter:title" content="[^"]*" />', f'<meta name="twitter:title" content="{escape(title)}" />', html)
    html = re.sub(r'<meta name="twitter:description" content="[^"]*" />', f'<meta name="twitter:description" content="{escape(description)}" />', html)
    return html


def health_check(request):
    return HttpResponse("OK", status=200)


def public_recipe_view(request, pk, slug=None):
    from diet_planner.models import Recipe
    try:
        recipe = Recipe.objects.get(pk=pk, is_public=True)
    except Recipe.DoesNotExist:
        raise Http404

    if slug != recipe.slug:
        return redirect(recipe.get_absolute_url(), permanent=True)

    template = _get_index_template()
    if not template:
        raise Http404

    ingredients_html = ''
    for ing in (recipe.ingredients or []):
        if isinstance(ing, dict):
            ingredients_html += f'<li>{escape(ing.get("name", ""))} — {escape(str(ing.get("quantity", "")))} {escape(ing.get("unit", ""))}</li>'
        else:
            ingredients_html += f'<li>{escape(str(ing))}</li>'

    instructions_html = ''
    for step in (recipe.instructions or []):
        instructions_html += f'<li>{escape(step)}</li>'

    nutrition_html = ''
    for k, v in (recipe.nutritional_info or {}).items():
        nutrition_html += f'<dt>{escape(k)}</dt><dd>{escape(str(v))}</dd>'

    from diet_planner.food_categories import DEFAULT_CATEGORY, FOOD_CATEGORIES
    img_category = recipe.food_category if recipe.food_category in FOOD_CATEGORIES else DEFAULT_CATEGORY
    img_url = f'/static/food-images/{img_category}.webp'

    schema_ld = {
        "@context": "https://schema.org",
        "@type": "Recipe",
        "name": recipe.name,
        "description": recipe.description or "",
        "image": img_url,
        "recipeIngredient": [
            f"{ing.get('quantity', '')} {ing.get('unit', '')} {ing.get('name', '')}".strip()
            if isinstance(ing, dict) else str(ing)
            for ing in (recipe.ingredients or [])
        ],
        "recipeInstructions": [
            {"@type": "HowToStep", "position": i + 1, "text": step}
            for i, step in enumerate(recipe.instructions or [])
        ],
    }
    if recipe.preparation_time:
        schema_ld["prepTime"] = f"PT{recipe.preparation_time}M"
    if recipe.cooking_time:
        schema_ld["cookTime"] = f"PT{recipe.cooking_time}M"
    if recipe.servings:
        schema_ld["recipeYield"] = str(recipe.servings)
    if recipe.nutritional_info:
        ni = recipe.nutritional_info
        schema_ld["nutrition"] = {"@type": "NutritionInformation"}
        for k, v in ni.items():
            kl = k.lower()
            if 'calor' in kl or kl == 'kcal':
                schema_ld["nutrition"]["calories"] = str(v)
            elif 'protein' in kl:
                schema_ld["nutrition"]["proteinContent"] = str(v)
            elif 'carb' in kl:
                schema_ld["nutrition"]["carbohydrateContent"] = str(v)
            elif 'fat' in kl:
                schema_ld["nutrition"]["fatContent"] = str(v)

    recipe_html = f'''<div style="max-width:56rem;margin:0 auto;padding:3rem 1.5rem;background:#F7F3EC;color:#241E1A;">
<nav style="margin-bottom:2rem;font-size:0.875rem;"><a href="/recepty/" style="color:#2E6B43;">Recepty</a> / <span>{escape(recipe.name)}</span></nav>
<div style="position:relative;height:20rem;border-radius:1.5rem;overflow:hidden;margin-bottom:2rem;">
<img src="{img_url}" alt="{escape(recipe.name)}" style="width:100%;height:100%;object-fit:cover;" loading="lazy" onerror="this.parentElement.style.display='none'" />
</div>
<h1 style="font-size:2.5rem;font-weight:900;">{escape(recipe.name)}</h1>
{f'<p style="color:#5E564C;margin-top:0.5rem;font-style:italic;">{escape(recipe.description)}</p>' if recipe.description else ''}
<div style="display:flex;gap:1.5rem;margin-top:1rem;font-size:0.75rem;color:#5E564C;">
{f'<span>Priprava: {recipe.preparation_time} min</span>' if recipe.preparation_time else ''}
{f'<span>Vareni: {recipe.cooking_time} min</span>' if recipe.cooking_time else ''}
{f'<span>{recipe.servings} porci</span>' if recipe.servings else ''}
</div>
<div style="display:grid;grid-template-columns:1fr 2fr;gap:2rem;margin-top:2rem;">
<section><h2 style="font-size:1.125rem;font-weight:900;border-bottom:1px solid #E4DAC8;padding-bottom:0.5rem;">Ingredience</h2><ul style="margin-top:1rem;padding-left:1.25rem;">{ingredients_html}</ul></section>
<section><h2 style="font-size:1.125rem;font-weight:900;">Postup</h2><ol style="margin-top:1rem;padding-left:1.25rem;">{instructions_html}</ol></section>
</div>
{f'<section style="margin-top:2rem;"><h3 style="font-size:0.875rem;font-weight:900;">Nutriční hodnoty</h3><dl style="display:grid;grid-template-columns:repeat(4,1fr);gap:0.5rem;margin-top:0.5rem;">{nutrition_html}</dl></section>' if nutrition_html else ''}
<div style="margin-top:3rem;padding:2rem;text-align:center;background:#FFFFFF;border:1px solid #E4DAC8;border-radius:1.5rem;">
<p style="font-size:1.25rem;font-weight:900;">Chcete celý týden takových jídel?</p>
<p style="color:#5E564C;margin-top:0.5rem;">Vařto sestaví jídelníček na míru s recepty a nákupním seznamem s poctivým odhadem ceny.</p>
<a href="/login" style="display:inline-block;margin-top:1rem;padding:0.875rem 2rem;background:#2E6B43;color:white;border-radius:0.75rem;text-decoration:none;font-weight:900;">Vytvořte si jídelníček zdarma</a>
</div>
</div>
<script type="application/ld+json">{json.dumps(schema_ld, ensure_ascii=False)}</script>'''

    html = template.replace('<!--ssr-outlet-->', recipe_html)
    title = f'{recipe.name} — Recept | Vařto'
    desc = (recipe.description or recipe.name)[:160]
    canonical = f'{SITE_URL}/recepty/{recipe.pk}/{recipe.slug}/'
    html = _replace_meta(html, title, desc, canonical)

    return HttpResponse(html, content_type="text/html")


def public_recipe_index_view(request):
    from diet_planner.models import Recipe
    from django.core.paginator import Paginator

    page_num = request.GET.get('page', 1)
    recipes = Recipe.objects.filter(is_public=True).order_by('-created_at')
    paginator = Paginator(recipes, 24)
    page = paginator.get_page(page_num)

    cards = ''
    for r in page:
        cards += f'''<a href="{r.get_absolute_url()}" style="display:block;padding:1.5rem;background:#FFFFFF;border:1px solid #E4DAC8;border-radius:1rem;text-decoration:none;color:inherit;">
<h2 style="font-size:1.125rem;font-weight:bold;color:#241E1A;">{escape(r.name)}</h2>
{f'<p style="color:#5E564C;font-size:0.875rem;margin-top:0.25rem;">{escape((r.description or "")[:120])}</p>' if r.description else ''}
<div style="margin-top:0.5rem;font-size:0.75rem;color:#5E564C;">{f"{r.preparation_time} min" if r.preparation_time else ""}{f" | {r.servings} porcí" if r.servings else ""}</div>
</a>'''

    pagination = ''
    if page.has_previous():
        pagination += f'<a href="?page={page.previous_page_number()}" style="color:#2E6B43;margin-right:1rem;">Předchozí</a>'
    pagination += f'<span style="color:#5E564C;">Strana {page.number} z {paginator.num_pages}</span>'
    if page.has_next():
        pagination += f'<a href="?page={page.next_page_number()}" style="color:#2E6B43;margin-left:1rem;">Další</a>'

    index_html = f'''<div style="max-width:72rem;margin:0 auto;padding:3rem 1.5rem;background:#F7F3EC;color:#241E1A;">
<h1 style="font-size:2.5rem;font-weight:900;">Recepty</h1>
<p style="color:#5E564C;margin-top:0.5rem;">Prozkoumejte naše recepty s nutričními hodnotami a podrobnými postupy.</p>
<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:1.5rem;margin-top:2rem;">{cards}</div>
<div style="text-align:center;margin-top:2rem;">{pagination}</div>
<div style="margin-top:3rem;padding:2rem;text-align:center;background:#FFFFFF;border:1px solid #E4DAC8;border-radius:1.5rem;">
<p style="font-size:1.25rem;font-weight:900;">Chcete vlastní jídelníček na míru?</p>
<a href="/login" style="display:inline-block;margin-top:1rem;padding:0.875rem 2rem;background:#2E6B43;color:white;border-radius:0.75rem;text-decoration:none;font-weight:900;">Vytvořte si jídelníček zdarma</a>
</div>
</div>'''

    template = _get_index_template()
    if not template:
        raise Http404
    html = template.replace('<!--ssr-outlet-->', index_html)
    title = 'Recepty — Vařto'
    desc = 'Prozkoumejte naše recepty s nutričními hodnotami a podrobnými postupy. Každý recept obsahuje ingredience, postup a nutriční hodnoty.'
    canonical = f'{SITE_URL}/recepty/'
    html = _replace_meta(html, title, desc, canonical)

    return HttpResponse(html, content_type="text/html")


def security_txt_view(request):
    expires = (datetime.now(timezone.utc) + timedelta(days=365)).strftime("%Y-%m-%dT00:00:00.000Z")
    body = (
        "Contact: mailto:admin@kentakin.eu\n"
        f"Expires: {expires}\n"
        "Preferred-Languages: cs, en\n"
        "Canonical: https://eatalnicek.eu/.well-known/security.txt\n"
    )
    return HttpResponse(body, content_type="text/plain")


def react_app_view(request):
    path_str = request.path.lstrip('/')

    if path_str and '.' in path_str and not path_str.endswith('.html'):
        logger.warning(f"Static asset 404 intercepted by catch-all: {path_str}")
        raise Http404(f"Asset '{path_str}' not found in static storage.")

    normalized = '/' + path_str.rstrip('/')
    if normalized != '/':
        normalized = normalized.rstrip('/')

    prerendered_file = PRERENDERED_ROUTES.get(normalized)
    if prerendered_file:
        for base_dir in [settings.STATIC_ROOT, settings.REACT_BUILD_DIR]:
            candidate = base_dir / "prerendered" / prerendered_file
            if candidate.exists():
                try:
                    with open(candidate, 'r', encoding='utf-8') as f:
                        return HttpResponse(f.read(), content_type="text/html")
                except Exception as e:
                    logger.error(f"Error reading prerendered {candidate}: {e}")
                    break

    index_locations = [
        settings.STATIC_ROOT / "index.html",
        settings.REACT_BUILD_DIR / "index.html"
    ]

    for index_path in index_locations:
        if index_path.exists():
            try:
                with open(index_path, 'r', encoding='utf-8') as f:
                    return HttpResponse(f.read(), content_type="text/html")
            except Exception as e:
                logger.error(f"Error reading index.html at {index_path}: {e}")

    return HttpResponse(
        "<h1>Deployment Error</h1><p>index.html not found. Check build logs for npm run build errors.</p>",
        status=200
    )

