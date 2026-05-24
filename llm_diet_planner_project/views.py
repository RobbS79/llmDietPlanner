# File: llm_diet_planner_project/views.py
import logging
from django.http import HttpResponse, Http404
from django.conf import settings
from pathlib import Path

logger = logging.getLogger(__name__)

def health_check(request):
    """Basic health check for DigitalOcean."""
    return HttpResponse("OK", status=200)

def react_app_view(request):
    """
    Catch-all view that serves the React Single Page Application.
    
    PHASE 2 FIX: Prevents returning HTML for missing static assets.
    If the path has a dot (e.g. .css) and it reached this view, it means WhiteNoise 
    didn't find the file. We must return 404 to avoid MIME errors.
    """
    path_str = request.path.lstrip('/')
    
    # MIME TYPE GUARD
    if path_str and '.' in path_str and not path_str.endswith('.html'):
        logger.warning(f"Static asset 404 intercepted by catch-all: {path_str}")
        raise Http404(f"Asset '{path_str}' not found in static storage.")

    # In production, look in STATIC_ROOT first (where collectstatic put it)
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

