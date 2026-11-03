"""
URL configuration for diet_planner app.
"""
from django.urls import path
from . import views
from diet_planner import views_discover

app_name = 'diet_planner'

urlpatterns = [
    path('goals/', views.DietaryGoalCreateView.as_view(), name='goal-create'),
    path('goals/list/', views.DietaryGoalListView.as_view(), name='goal-list'),
    path('goals/bulk-delete/', views.DietaryGoalBulkDeleteView.as_view(), name='goal-bulk-delete'),
    path('shops/', views.ShopsListView.as_view(), name='shops-list'),
    path('goals/<int:goal_id>/', views.DietaryGoalDetailView.as_view(), name='goal-detail'),
    path('goals/<int:goal_id>/task-status/', views.DietaryGoalTaskStatusView.as_view(), name='goal-task-status'),
    path('goals/<int:goal_id>/admin-retry/', views.AdminRetryGoalView.as_view(), name='goal-admin-retry'),
    path('goals/<int:goal_id>/meal-instances/', views.MealInstanceBatchView.as_view(), name='meal-instance-batch'),
    path('debug/scraper/', views.ScraperDebugView.as_view(), name='scraper-debug'),
    # Public recipe endpoints (no auth)
    path('recipes/public/', views.PublicRecipeListView.as_view(), name='public-recipe-list'),
    path('recipes/public/<int:pk>/', views.PublicRecipeDetailView.as_view(), name='public-recipe-detail'),
    # Uvařto first-visit endpoints (spec 2026-11-03)
    path('discover/', views_discover.DiscoverView.as_view(), name='discover'),
    path('discover/recipe/<int:pk>/', views_discover.DiscoverRecipeView.as_view(), name='discover-recipe'),
    path('deals/this-week/', views_discover.DealsThisWeekView.as_view(), name='deals-this-week'),
    path('shopping-list/compose/', views_discover.ShoppingListComposeView.as_view(), name='shopping-list-compose'),
    path('shopping-lists/', views_discover.SavedShoppingListView.as_view(), name='shopping-lists'),
    # Authenticated recipe endpoints
    path('recipes/research/<int:job_id>/', views.RecipeResearchJobView.as_view(), name='recipe-research-job'),
    path('recipes/<str:meal_identifier>/replace/', views.RecipeReplaceView.as_view(), name='recipe-replace'),
    path('recipes/<str:meal_identifier>/refine/', views.RecipeRefineView.as_view(), name='recipe-refine'),
    path('recipes/<str:meal_identifier>/', views.RecipeDetailView.as_view(), name='recipe-detail'),
    # Meal instance endpoints
    path('meals/<str:meal_identifier>/', views.MealInstanceView.as_view(), name='meal-instance'),
    path('meals/cooked/', views.MealInstanceCookedListView.as_view(), name='meal-instance-cooked-list'),
    # Protocol endpoints
    path('protocols/', views.ProtocolListView.as_view(), name='protocol-list'),
    path('protocols/upload/', views.ProtocolUploadView.as_view(), name='protocol-upload'),
    path('protocols/<int:protocol_id>/', views.ProtocolDetailView.as_view(), name='protocol-detail'),
]
