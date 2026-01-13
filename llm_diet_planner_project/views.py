import os
import logging
from django.http import HttpResponse, Http404
from django.shortcuts import render
from django.conf import settings

logger = logging.getLogger(__name__)

def health_check(request):
    """
    Simple health check for DigitalOcean.
    """
    return HttpResponse("OK", status=200)

def react_app_view(request):
    """
    Serves the React frontend. 
    Prevents serving index.html for asset requests to avoid MIME type errors.
    """
    # 1. Guard against serving index.html for static asset requests
    # If the path looks like a file (has an extension) and isn't a route,
    # we should let it 404 so the user doesn't get a MIME type error.
    path = request.path.lstrip('/')
    if path and '.' in path and not path.endswith('.html'):
        logger.warning(f"Prevented catch-all from serving HTML for asset: {path}")
        raise Http404("Asset not found")

    # 2. Resolve the path to index.html
    # In production, this is usually in the dist folder or the static root
    index_path = os.path.join(settings.REACT_BUILD_DIR, 'index.html')
    
    if not os.path.exists(index_path):
        # Fallback for deployments where collectstatic moved everything
        index_path = os.path.join(settings.STATIC_ROOT, 'index.html')

    # 3. Serve the file or show diagnostic
    if not os.path.exists(index_path):
        logger.error(f"Frontend build missing. Checked: {settings.REACT_BUILD_DIR} and {settings.STATIC_ROOT}")
        return HttpResponse(
            f"""
            <html>
                <body style="background: #0a0f1e; color: white; text-align: center; font-family: sans-serif; padding-top: 100px;">
                    <div style="max-width: 600px; margin: 0 auto; padding: 40px; background: #161d2f; border-radius: 24px; border: 1px solid #2563eb;">
                        <h1 style="color: #2563eb;">Vite Build Missing</h1>
                        <p>Django cannot find your React entry point.</p>
                        <div style="text-align: left; background: #0a0f1e; padding: 15px; border-radius: 8px; margin: 20px 0; font-family: monospace; font-size: 0.85em;">
                            Checked: {index_path}
                        </div>
                        <p style="font-size: 0.8em; color: #9ca3af;">Verify <code>npm run build</code> succeeded.</p>
                    </div>
                </body>
            </html>
            """,
            status=200 
        )

    try:
        with open(index_path, 'r') as f:
            return HttpResponse(f.read())
    except Exception as e:
        logger.error(f"Error reading index.html: {str(e)}")
        return HttpResponse("Internal Server Error", status=500)

def debug_prompt_view(request):
    return render(request, 'debug_prompt.html')

def test_ui_view(request):
    return render(request, 'test_ui.html')