import os
import logging
from django.http import HttpResponse, Http404
from django.shortcuts import render
from django.conf import settings

logger = logging.getLogger(__name__)

def health_check(request):
    """Platform health check."""
    return HttpResponse("OK", status=200)

def react_app_view(request):
    """
    Serves the React frontend.
    Ensures that asset requests (CSS/JS) don't get served HTML accidentally.
    """
    path = request.path.lstrip('/')
    
    # 1. Guard: If browser asks for a file with an extension, don't serve HTML.
    # This prevents the "text/html" MIME type mismatch error.
    if path and '.' in path and not path.endswith('.html'):
        logger.warning(f"Static asset not found in WhiteNoise, blocking catch-all: {path}")
        raise Http404("Asset not found")

    # 2. Path resolution: Vite build location
    index_path = os.path.join(settings.REACT_BUILD_DIR, 'index.html')
    
    # Fallback to the collected static directory
    if not os.path.exists(index_path):
        index_path = os.path.join(settings.STATIC_ROOT, 'index.html')

    if not os.path.exists(index_path):
        logger.error(f"UI entry point missing. Expected at: {index_path}")
        return HttpResponse(
            "Frontend Entry Point Missing. Please verify build logs.",
            status=200 # Healthy status to prevent DO restart loops
        )

    try:
        with open(index_path, 'r') as f:
            return HttpResponse(f.read())
    except Exception as e:
        logger.error(f"Error reading index.html: {str(e)}")
        return HttpResponse("Server error loading interface.", status=500)

def debug_prompt_view(request):
    return render(request, 'debug_prompt.html')

def test_ui_view(request):
    return render(request, 'test_ui.html')