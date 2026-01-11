"""
URL configuration for llm_diet_planner_project project.

This is the main entry point for all routing. It prioritizes API and Admin 
routes before falling back to the React SPA catch-all.
"""
from django.contrib import admin
from django.urls import path, re_path, include
from django.conf import settings
from django.conf.urls.static import static
from . import views

urlpatterns = [
    # 1. Django Admin
    path("admin/", admin.site.urls),
    
    # 2. Authentication API (includes /google/login/ and /google/callback/)
    path("api/auth/", include("login_app.urls")),
    
    # 3. Third-party Integrations
    # Note: Ensure the 'shopifyin' app exists and has a urls.py defined.
    path("api/shopify/", include("shopifyin.urls")),
    
    # 4. Core Application API
    path("api/", include("diet_planner.urls")),
    
    # 5. Debug and Test Tools (Backend-only templates)
    path("debug-prompt/", views.debug_prompt_view, name="debug-prompt"),
    path("test-ui/", views.test_ui_view, name="test-ui"),
    
    # 6. React Catch-all
    # This must be LAST. It serves the React SPA index.html for any route
    # that hasn't been matched by the above (e.g., /login, /goals, etc.)
    re_path(r'^(?!admin|api|static|debug-prompt|test-ui).*', views.react_app_view),
]

# Serve static and media files in development mode
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    # If media handling is added later:
    # urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)