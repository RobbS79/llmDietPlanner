"""
URL configuration for diet_planner app.
"""
from django.urls import path
from . import views

app_name = 'diet_planner'

urlpatterns = [
    path('goals/', views.DietaryGoalCreateView.as_view(), name='goal-create'),
    path('goals/list/', views.DietaryGoalListView.as_view(), name='goal-list'),
    path('goals/<int:goal_id>/', views.DietaryGoalDetailView.as_view(), name='goal-detail'),
    path('goals/<int:goal_id>/task-status/', views.DietaryGoalTaskStatusView.as_view(), name='goal-task-status'),
    path('goals/<int:goal_id>/prompt-debug/', views.DietaryGoalPromptDebugView.as_view(), name='goal-prompt-debug'),
]
