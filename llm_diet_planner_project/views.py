# File: llm_diet_planner_project/views.py
import logging
from django.http import HttpResponse, Http404
from django.shortcuts import render
from django.conf import settings
from pathlib import Path

logger = logging.getLogger(__name__)

def health_check(request):
    """Health check endpoint for DigitalOcean."""
    return HttpResponse("OK", status=200)

def react_app_view(request):
    """
    Main entry point for the React Single Page Application.
    
    PHASE 2 FIX: Includes a MIME guard to prevent returning HTML for missing assets.
    """
    path_str = request.path.lstrip('/')
    
    # MIME TYPE GUARD:
    # If the path has a dot (e.g. .css, .js) and it reached this view, it means
    # WhiteNoise failed to find it. Returning index.html would cause a MIME error.
    if path_str and '.' in path_str and not path_str.endswith('.html'):
        logger.warning(f"Static asset 404 intercepted by React catch-all: {path_str}")
        raise Http404(f"Asset '{path_str}' not found in static storage.")

    # Serve index.html from staticfiles (where collectstatic put it) or dist folder
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

    # Fallback error if index.html is missing everywhere
    return HttpResponse(
        "<h1>Deployment Error</h1><p>Frontend assets (index.html) not found. Check build logs.</p>",
        status=200
    )

def debug_prompt_view(request):
    return render(request, 'debug_prompt.html')

def test_ui_view(request):
    return render(request, 'test_ui.html')