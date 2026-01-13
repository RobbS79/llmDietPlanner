import os
import logging
from django.http import HttpResponse, Http404
from django.shortcuts import render
from django.conf import settings

logger = logging.getLogger(__name__)

def health_check(request):
    """
    Standard health check for DigitalOcean.
    """
    return HttpResponse("OK", status=200)

def react_app_view(request):
    """
    The Single Entry Point for the React Application.
    This view serves index.html and lets React handle routing.
    """
    path = request.path.lstrip('/')
    
    # --- MIME TYPE PROTECTION ---
    # If the browser is asking for an asset (something with a dot in the name)
    # and it hasn't already been served by WhiteNoise, we MUST return 404.
    # If we return index.html, the browser gives the "MIME type mismatch" error.
    if path and '.' in path and not path.endswith('.html'):
        logger.warning(f"Blocking catch-all HTML for asset request: {path}")
        raise Http404("Asset not found in static storage")

    # Resolve index.html path from settings
    index_path = os.path.join(settings.REACT_BUILD_DIR, 'index.html')
    
    # Fallback to static root if build dir is empty
    if not os.path.exists(index_path):
        index_path = os.path.join(settings.STATIC_ROOT, 'index.html')

    # Diagnostic check
    if not os.path.exists(index_path):
        logger.error(f"FATAL: UI entry point missing at {index_path}")
        return HttpResponse(
            f"Build Mismatch: index.html not found. Deployment failed to sync static files.",
            status=200 # Healthy status prevents restart loops
        )

    try:
        with open(index_path, 'r') as f:
            return HttpResponse(f.read())
    except Exception as e:
        logger.error(f"Error reading index.html: {str(e)}")
        return HttpResponse("Internal server error loading the application UI.", status=500)

def debug_prompt_view(request):
    return render(request, 'debug_prompt.html')

def test_ui_view(request):
    return render(request, 'test_ui.html')