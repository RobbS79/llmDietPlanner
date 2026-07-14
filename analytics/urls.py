from django.urls import path

from analytics.views import ConsentView

app_name = "analytics"

urlpatterns = [
    path("consent/", ConsentView.as_view(), name="consent"),
]
