"""
Views for serving React frontend
"""
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
import os


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
                </body>
            </html>
            """,
            status=503
        )

