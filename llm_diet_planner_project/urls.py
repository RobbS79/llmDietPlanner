from django.contrib import admin
from django.contrib.sitemaps.views import sitemap
from django.urls import path, re_path, include
from . import views
from .sitemaps import sitemaps

"""
ROOT URL CONFIGURATION
======================
Strict separation of concerns:
1. /health/      -> Platform health checks
2. /admin/       -> Django Administrative interface
3. /api/         -> All backend logic (Login, Diet Planning, Shopify)
4. /sitemap.xml  -> SEO sitemap for search engines
5. Catch-all     -> Serves the React SPA
"""

urlpatterns = [
    # 1. Health check for DigitalOcean (Returns 200)
    path("health/", views.health_check, name="health-check"),

    # 2. Django Admin
    path("admin/", admin.site.urls),

    # 3. API Namespace (Strictly separated from frontend routes)
    path("api/auth/", include("login_app.urls")),
    path("api/", include("diet_planner.urls")),

    # 4. SEO: XML Sitemap for Google & Seznam crawlers
    path(
        "sitemap.xml",
        sitemap,
        {"sitemaps": sitemaps},
        name="django.contrib.sitemaps.views.sitemap",
    ),

    # 5. CATCH-ALL: Serve React App (Must be last)
    # This view is now guarded against asset requests to prevent MIME errors.
    re_path(r'^.*$', views.react_app_view, name="react-app"),
]