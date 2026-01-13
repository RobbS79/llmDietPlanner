# File: llm_diet_planner_project/views.py
import os
import logging
from django.http import HttpResponse, Http404
from django.shortcuts import render
from django.conf import settings
from pathlib import Path

logger = logging.getLogger(__name__)

def health_check(request):
    """
    Standard health check for DigitalOcean.
    """
    return HttpResponse("OK", status=200)

def react_app_view(request):
    """
    Serves the index.html for React SPA.
    Protects against MIME type errors by raising 404 for missing assets.
    """
    path_str = request.path.lstrip('/')
    
    # --- CRITICAL: PREVENT MIME TYPE ERROR ---
    # If the request is for a file (contains a dot) and it reached this view,
    # it means WhiteNoise/Nginx failed to find the actual physical file.
    # Returning index.html as a response to a .css or .js request causes the browser
    # to refuse it due to incorrect MIME type. We MUST raise 404 here.
    if path_str and '.' in path_str and not path_str.endswith('.html'):
        logger.error(f"Static asset requested but not found in storage: {path_str}")
        raise Http404(f"Asset '{path_str}' not found.")

    # Proceed to serve the index.html from the build folder
    index_path = Path(settings.REACT_BUILD_DIR) / 'index.html'
    if not index_path.exists():
        index_path = Path(settings.STATIC_ROOT) / 'index.html'

    if not index_path.exists():
        return HttpResponse("Deployment Error: index.html not found.", status=200)

    try:
        with open(index_path, 'r', encoding='utf-8') as f:
            content = f.read()
            return HttpResponse(content, content_type="text/html")
    except Exception as e:
        return HttpResponse("Internal Server Error", status=500)

def debug_prompt_view(request):
    """Utility view for debugging LLM prompts."""
    return render(request, 'debug_prompt.html')

def test_ui_view(request):
    """Utility view for testing UI components without React build."""
    return render(request, 'test_ui.html')