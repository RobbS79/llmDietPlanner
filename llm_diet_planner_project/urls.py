from django.contrib import admin
from django.urls import path, re_path, include
from django.conf import settings
from django.conf.urls.static import static
from . import views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/auth/", include("login_app.urls")),
    path("api/", include("diet_planner.urls")),
    path("debug-prompt/", views.debug_prompt_view, name="debug-prompt"),
    path("test-ui/", views.test_ui_view, name="test-ui"),
    
    # Serve React app for all other routes
    re_path(r'^(?!admin|api|static|debug-prompt|test-ui|media).*', views.react_app_view),
]

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)