import os
import logging
from django.http import HttpResponse
from django.shortcuts import render
from django.conf import settings

logger = logging.getLogger(__name__)

def react_app_view(request):
    """
    Serve React app's index.html from the Vite 'dist' directory.
    This ensures that Django serves the correctly styled CSS/JS from the single entry point.
    """
    # Vite builds to 'dist'. Dockerfile.prod ensures this path exists.
    dist_index_path = os.path.join(settings.BASE_DIR, 'frontend', 'dist', 'index.html')
    
    try:
        with open(dist_index_path, 'r') as f:
            return HttpResponse(f.read())
    except FileNotFoundError:
        logger.error(f"Vite build missing at: {dist_index_path}")
        return HttpResponse(
            """
            <html>
                <body style="background: #0a0f1e; color: white; text-align: center; font-family: sans-serif; padding-top: 20%;">
                    <h1>Vite App Not Built</h1>
                    <p>The production 'dist' folder is missing.</p>
                    <p>Deployment Error: Build stage may have failed.</p>
                </body>
            </html>
            """,
            status=503
        )

def debug_prompt_view(request):
    return render(request, 'debug_prompt.html')

def test_ui_view(request):
    return render(request, 'test_ui.html')