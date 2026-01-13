# File: llm_diet_planner_project/views.py
import os
import logging
from django.http import HttpResponse, Http404
from django.shortcuts import render
from django.conf import settings
from pathlib import Path

logger = logging.getLogger(__name__)

def health_check(request):
    return HttpResponse("OK", status=200)

def react_app_view(request):
    """
    Single Entry Point for React Application.
    Prevents serving HTML for missing static assets to avoid MIME errors.
    """
    path_str = request.path.lstrip('/')
    
    # --- MIME PROTECTION ---
    # If the requested path has a dot (extension) and reached this catch-all view,
    # it means the file is not in static storage. Return 404 instead of index.html
    # so the browser doesn't try to parse HTML as CSS or JavaScript.
    if path_str and '.' in path_str and not path_str.endswith('.html'):
        logger.warning(f"Static file not found (intercepted by catch-all): {path_str}")
        raise Http404(f"Asset '{path_str}' not found.")

    index_path = Path(settings.REACT_BUILD_DIR) / 'index.html'
    if not index_path.exists():
        index_path = Path(settings.STATIC_ROOT) / 'index.html'

    if not index_path.exists():
        return HttpResponse(
            f"<h1>Deployment Configuration Error</h1><p>index.html not found.</p>",
            status=200
        )

    try:
        with open(index_path, 'r', encoding='utf-8') as f:
            return HttpResponse(f.read(), content_type="text/html")
    except Exception as e:
        logger.error(f"Error serving index.html: {e}")
        return HttpResponse("Internal Server Error", status=500)

def debug_prompt_view(request):
    return render(request, 'debug_prompt.html')

def test_ui_view(request):
    return render(request, 'test_ui.html')