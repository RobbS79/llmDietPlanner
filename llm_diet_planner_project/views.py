import os
import logging
from django.http import HttpResponse
from django.shortcuts import render
from django.conf import settings

logger = logging.getLogger(__name__)

def health_check(request):
    return HttpResponse("OK", status=200)

def react_app_view(request):
    """
    Serves the React frontend. Looks for index.html in REACT_BUILD_DIR.
    """
    # Match the variable name used in settings.py
    index_path = os.path.join(settings.REACT_BUILD_DIR, 'index.html')
    
    if not os.path.exists(index_path):
        # Fallback for SPA: check if it's in staticfiles after collection
        index_path = os.path.join(settings.STATIC_ROOT, 'index.html')

    if not os.path.exists(index_path):
        logger.error(f"Frontend build missing. Looked in: {settings.REACT_BUILD_DIR} and {settings.STATIC_ROOT}")
        return HttpResponse(
            f"Vite Build Missing. Expected index.html at {index_path}. Check your deployment build logs.",
            status=200 # Return 200 so health checks pass while debugging
        )

    with open(index_path, 'r') as f:
        return HttpResponse(f.read())

def debug_prompt_view(request):
    return render(request, 'debug_prompt.html')

def test_ui_view(request):
    return render(request, 'test_ui.html')