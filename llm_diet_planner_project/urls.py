from django.contrib import admin
from django.urls import path, re_path, include
from . import views

urlpatterns = [
    # Health check for DigitalOcean (Returns 200)
    path("health/", views.health_check, name="health-check"),
    
    path("admin/", admin.site.urls),
    path("api/auth/", include("login_app.urls")),
    path("api/", include("diet_planner.urls")),
    path("debug-prompt/", views.debug_prompt_view, name="debug-prompt"),
    path("test-ui/", views.test_ui_view, name="test-ui"),
    
    # CATCH-ALL: Serve React App (Must be last)
    re_path(r'^.*$', views.react_app_view, name="react-app"),
]