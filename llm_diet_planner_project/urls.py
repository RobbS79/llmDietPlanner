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
    path("api/shopify/", include("shopifyin.urls")),
    path("api/billing/", include("billing.urls")),
    path("api/", include("diet_planner.urls")),

    # 4. SEO: XML Sitemap for Google & Seznam crawlers
    path(
        "sitemap.xml",
        sitemap,
        {"sitemaps": sitemaps},
        name="django.contrib.sitemaps.views.sitemap",
    ),

    # 5. Public recipe pages (Django-rendered HTML for SEO)
    path("recepty/", views.public_recipe_index_view, name="public-recipe-index"),
    path("recepty/<int:pk>/<slug:slug>/", views.public_recipe_view, name="public-recipe-detail"),
    path("recepty/<int:pk>/", views.public_recipe_view, name="public-recipe-no-slug"),

    # 6. RFC 9116 security.txt
    path(".well-known/security.txt", views.security_txt_view, name="security-txt"),

    # 7. CATCH-ALL: Serve React App (Must be last)
    re_path(r'^.*$', views.react_app_view, name="react-app"),
]