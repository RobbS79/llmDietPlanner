"""
Celery configuration for async task processing.

This module provides Celery app configuration. When Celery is not installed,
it provides a mock Celery app that allows Django to start without errors.
"""
import os
import logging

logger = logging.getLogger(__name__)

# Set the default Django settings module for the 'celery' program.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'llm_diet_planner_project.settings')

# Import from compatibility layer
try:
    from .celery_compat import Celery, is_celery_available
    
    if is_celery_available():
        # Create real Celery app when available
        app = Celery('llm_diet_planner_project')
        
        # Using a string here means the worker doesn't have to serialize
        # the configuration object to child processes.
        app.config_from_object('django.conf:settings', namespace='CELERY')
        
        # Load task modules from all registered Django apps.
        try:
            app.autodiscover_tasks()
        except Exception as e:
            # Log but don't fail if task discovery fails
            logger.warning(f"Failed to autodiscover Celery tasks: {e}")
        
        logger.info("Celery app configured successfully")
    else:
        # Create mock Celery app when Celery is not available
        app = Celery('llm_diet_planner_project')
        logger.info("Celery not installed - using mock Celery app")
        
except ImportError:
    # Fallback if compatibility layer can't be imported
    from .celery_compat import Celery
    app = Celery('llm_diet_planner_project')
    logger.warning("Celery compatibility layer not available - using mock Celery app")




