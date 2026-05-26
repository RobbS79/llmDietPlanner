# File: llm_diet_planner_project/views.py
import logging
from django.http import HttpResponse, Http404
from django.conf import settings
from pathlib import Path

logger = logging.getLogger(__name__)

PRERENDERED_ROUTES = {
    '/': 'index.html',
    '/login': 'login/index.html',
    '/pricing': 'pricing/index.html',
    '/privacy': 'privacy/index.html',
    '/terms': 'terms/index.html',
    '/forgot-password': 'forgot-password/index.html',
}

def health_check(request):
    """Basic health check for DigitalOcean."""
    return HttpResponse("OK", status=200)

def react_app_view(request):
    """
    Catch-all view that serves the React SPA.

    For public routes with prerendered HTML, serves the static version
    for SEO (Seznam.cz, Google). For all other routes, serves the
    standard SPA index.html shell.
    """
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

