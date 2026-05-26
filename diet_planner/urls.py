"""
URL configuration for diet_planner app.
"""
from django.urls import path
from . import views

app_name = 'diet_planner'

urlpatterns = [
    path('goals/', views.DietaryGoalCreateView.as_view(), name='goal-create'),
    path('goals/list/', views.DietaryGoalListView.as_view(), name='goal-list'),
    path('shops/', views.ShopsListView.as_view(), name='shops-list'),
    path('goals/<int:goal_id>/', views.DietaryGoalDetailView.as_view(), name='goal-detail'),
    path('goals/<int:goal_id>/task-status/', views.DietaryGoalTaskStatusView.as_view(), name='goal-task-status'),
    path('goals/<int:goal_id>/prompt-debug/', views.DietaryGoalPromptDebugView.as_view(), name='goal-prompt-debug'),
    path('goals/<int:goal_id>/meal-instances/', views.MealInstanceBatchView.as_view(), name='meal-instance-batch'),
    path('debug/scraper/', views.ScraperDebugView.as_view(), name='scraper-debug'),
    # Public recipe endpoints (no auth)
    path('recipes/public/', views.PublicRecipeListView.as_view(), name='public-recipe-list'),
    path('recipes/public/<int:pk>/', views.PublicRecipeDetailView.as_view(), name='public-recipe-detail'),
    # Authenticated recipe endpoints
    path('recipes/<str:meal_identifier>/', views.RecipeDetailView.as_view(), name='recipe-detail'),
    # Meal instance endpoints
    path('meals/<str:meal_identifier>/', views.MealInstanceView.as_view(), name='meal-instance'),
    path('meals/cooked/', views.MealInstanceCookedListView.as_view(), name='meal-instance-cooked-list'),
]
