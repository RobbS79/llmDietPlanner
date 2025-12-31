"""
App configuration for login_app.
"""
from django.apps import AppConfig


class LoginAppConfig(AppConfig):
    """Configuration for login_app."""
    
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'login_app'
    verbose_name = 'Login App'
    
    def ready(self):
        """Import admin when app is ready."""
        import login_app.admin  # noqa: F401

