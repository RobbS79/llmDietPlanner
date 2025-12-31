"""
App configuration for diet_planner.
"""
from django.apps import AppConfig


class DietPlannerConfig(AppConfig):
    """Configuration for diet_planner app."""
    
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'diet_planner'
    
    def ready(self):
        """Import signal handlers when app is ready."""
        import diet_planner.signals  # noqa
