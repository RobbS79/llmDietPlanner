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


from django.http import HttpResponse
from django.shortcuts import render
from django.conf import settings
import os

def react_app_view(request):
    """
    Serve React app's index.html for all non-API routes.
    """
    # Use absolute path to the built index.html
    index_path = os.path.join(settings.REACT_BUILD_DIR, 'index.html')
    
    try:
        with open(index_path, 'r') as f:
            return HttpResponse(f.read())
    except FileNotFoundError:
        return HttpResponse(
            f"React build not found at {index_path}. Please ensure 'npm run build' was successful.",
            status=503
        )
