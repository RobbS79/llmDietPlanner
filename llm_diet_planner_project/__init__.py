# This will make sure the app is always imported when
# Django starts so that shared_task will use this app.
# When Celery is not installed, this will use a mock app that allows Django to start.
try:
    from .celery import app as celery_app
    __all__ = ('celery_app',)
except Exception as e:
    # If Celery configuration fails, create a mock app so Django can still start
    import logging
    logger = logging.getLogger(__name__)
    logger.warning(f"Failed to import Celery app: {e}. Django will continue without Celery support.")
    
    # Import mock Celery app from compatibility layer
    try:
        from .celery_compat import Celery
        celery_app = Celery('llm_diet_planner_project')
        __all__ = ('celery_app',)
    except ImportError:
        # If compatibility layer is also unavailable, just export nothing
        celery_app = None
        __all__ = ()



