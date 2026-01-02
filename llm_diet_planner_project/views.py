"""
Views for serving React frontend
"""
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import render
from django.conf import settings
import os


def debug_prompt_view(request):
    """
    Debug page to view LLM JSON prompt structure.
    Accessible at /debug-prompt/
    """
    return render(request, 'debug_prompt.html')


def test_ui_view(request):
    """
    Test UI page to create dietary goals and view JSON prompts.
    Accessible at /test-ui/
    """
    return render(request, 'test_ui.html')


def react_app_view(request):
    """
    Serve React app's index.html for all non-API routes.
    """
    try:
        with open(os.path.join(settings.REACT_BUILD_DIR, 'index.html'), 'r') as f:
            return HttpResponse(f.read())
    except FileNotFoundError:
        return HttpResponse(
            """
            <html>
                <body>
                    <h1>React app not built</h1>
                    <p>Please run 'npm install && npm run build' in the frontend directory.</p>
                    <p><a href="/debug-prompt/">Or use the Debug Tool to view JSON prompts</a></p>
                </body>
            </html>
            """,
            status=503
        )

