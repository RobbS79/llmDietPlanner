from django.urls import path

from . import views

app_name = 'social'

urlpatterns = [
    path('card/<int:pk>/<slug:sig>.png', views.card_png, name='card'),
    path('slack/interact/', views.SlackInteractView.as_view(), name='slack-interact'),
]
