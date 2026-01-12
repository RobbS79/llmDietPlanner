"""
Views for serving the modern React frontend built with Vite.
"""
import os
import logging
from django.http import HttpResponse
from django.shortcuts import render
from django.conf import settings

logger = logging.getLogger(__name__)

def react_app_view(request):
    """
    Serve the React app's index.html from the Vite 'dist' directory.
    This replaces the traditional template system for the frontend SPA.
    """
    # Vite builds to 'dist' by default. Update settings.py REACT_BUILD_DIR if different.
    # In our Dockerfile.prod, we copied it to /app/frontend/dist
    dist_index_path = os.path.join(settings.BASE_DIR, 'frontend', 'dist', 'index.html')
    
    try:
        with open(dist_index_path, 'r') as f:
            return HttpResponse(f.read())
    except FileNotFoundError:
        logger.error(f"Frontend build missing at: {dist_index_path}")
        return HttpResponse(
            """
            <html>
                <body style="font-family: sans-serif; text-align: center; padding: 50px; background: #0a0f1e; color: white;">
                    <h1>Frontend Build Not Found</h1>
                    <p>The React application has not been built or the directory is incorrect.</p>
                    <p>Path checked: <code>frontend/dist/index.html</code></p>
                    <hr style="border-color: #2d3748;">
                    <p><a href="/admin/" style="color: #2563eb;">Access Django Admin</a></p>
                </body>
            </html>
            """,
            status=503
        )

def debug_prompt_view(request):
    """Debug page to view LLM JSON prompt structure."""
    return render(request, 'debug_prompt.html')

def test_ui_view(request):
    """Test UI page for dietary goals."""
    return render(request, 'test_ui.html')