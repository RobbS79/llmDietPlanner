"""
Celery Compatibility Utility

Provides a compatibility layer that allows Django to work with or without Celery installed.
When Celery is available, exports the real Celery components. When not available,
provides no-op implementations that allow the code to run without Celery.

Usage:
    from llm_diet_planner_project.celery_compat import shared_task, AsyncResult, is_celery_available

    @shared_task(bind=True, max_retries=3)
    def my_task(self, arg1, arg2):
        # Task implementation
        pass

    # Check if Celery is available
    if is_celery_available():
        task.delay(args)
    else:
        task(args)  # Call synchronously
"""
import logging

logger = logging.getLogger(__name__)

# Try to import Celery components
try:
    from celery import shared_task, Celery
    from celery.result import AsyncResult as CeleryAsyncResult
    CELERY_AVAILABLE = True
    logger.info("Celery is available - using real Celery components")
except ImportError:
    CELERY_AVAILABLE = False
    logger.info("Celery is not installed - using compatibility shims")
    
    # Create no-op shared_task decorator
    def shared_task(*args, **kwargs):
        """
        No-op decorator when Celery is not available.
        
        Returns a decorator that adds a `.delay()` method to the function,
        allowing it to be called synchronously when Celery is unavailable.
        The function can still be called synchronously.
        """
        def decorator(func):
            # If bind=True, add self parameter handling
            bind = kwargs.get('bind', False)
            
            if bind:
                # Create a wrapper that handles 'self' parameter
                def wrapper(self_or_first, *args, **kwargs):
                    if hasattr(self_or_first, 'retry'):
                        # Called as bound task (self is first arg)
                        return func(self_or_first, *args, **kwargs)
                    else:
                        # Called directly, self is None
                        # Create a mock self object with retry method
                        class MockSelf:
                            def retry(self, exc=None, countdown=60):
                                raise NotImplementedError(
                                    "Celery is not installed. Tasks cannot be retried. "
                                    "Install Celery to enable async task processing with retries."
                                )
                        return func(MockSelf(), self_or_first, *args, **kwargs)
                wrapper.__name__ = func.__name__
                wrapper.__doc__ = func.__doc__
                
                # Add .delay() method that calls synchronously
                def delay(*args, **kwargs):
                    """Call the task synchronously when Celery is unavailable."""
                    logger.warning(f"Celery not available - executing task {func.__name__} synchronously")
                    # Create mock self for bound tasks
                    class MockSelf:
                        def retry(self, exc=None, countdown=60):
                            raise NotImplementedError(
                                "Celery is not installed. Tasks cannot be retried. "
                                "Install Celery to enable async task processing with retries."
                            )
                    
                    # Execute task synchronously
                    result = wrapper(MockSelf(), *args, **kwargs)
                    
                    # Create mock AsyncResult-like object for delay() return value
                    import uuid
                    class MockTaskResult:
                        def __init__(self, task_id):
                            self.id = task_id
                    
                    task_id = f"mock-{func.__name__}-{uuid.uuid4().hex[:8]}"
                    return MockTaskResult(task_id)
                
                wrapper.delay = delay
                
                # Also support apply_async
                def apply_async(*args, **kwargs):
                    """Call the task synchronously when Celery is unavailable."""
                    return delay(*args, **kwargs)
                wrapper.apply_async = apply_async
                
                return wrapper
            else:
                # Not bound - simpler case
                # Add .delay() method that calls synchronously
                def delay(*args, **kwargs):
                    """Call the task synchronously when Celery is unavailable."""
                    logger.warning(f"Celery not available - executing task {func.__name__} synchronously")
                    # Execute task synchronously
                    result = func(*args, **kwargs)
                    
                    # Create mock AsyncResult-like object for delay() return value
                    import uuid
                    class MockTaskResult:
                        def __init__(self, task_id):
                            self.id = task_id
                    
                    task_id = f"mock-{func.__name__}-{uuid.uuid4().hex[:8]}"
                    return MockTaskResult(task_id)
                
                func.delay = delay
                
                # Also support apply_async
                def apply_async(*args, **kwargs):
                    """Call the task synchronously when Celery is unavailable."""
                    return delay(*args, **kwargs)
                func.apply_async = apply_async
                
                return func
        return decorator
    
    # Create mock Celery app
    class MockCeleryApp:
        """Mock Celery app when Celery is not available."""
        
        def config_from_object(self, obj, namespace=None):
            """No-op configuration."""
            pass
        
        def autodiscover_tasks(self, packages=None, related_name='tasks', force=False):
            """No-op task discovery."""
            pass
    
    # Create mock AsyncResult
    class AsyncResult:
        """
        Mock AsyncResult when Celery is not available.
        
        Provides a compatible interface but always returns 'NOT_STARTED' status.
        """
        
        def __init__(self, task_id, app=None):
            """
            Initialize mock AsyncResult.
            
            Args:
                task_id: Task ID (ignored when Celery unavailable)
                app: Celery app (ignored when Celery unavailable)
            """
            self.id = task_id
            self._state = 'NOT_STARTED'
            self._result = None
            self._info = None
        
        @property
        def state(self):
            """Always returns 'NOT_STARTED' when Celery is unavailable."""
            return self._state
        
        @property
        def ready(self):
            """Always returns False when Celery is unavailable."""
            return False
        
        @property
        def successful(self):
            """Always returns False when Celery is unavailable."""
            return False
        
        @property
        def failed(self):
            """Always returns False when Celery is unavailable."""
            return False
        
        @property
        def result(self):
            """Returns None when Celery is unavailable."""
            return self._result
        
        @property
        def info(self):
            """Returns error message when Celery is unavailable."""
            return "Celery is not available - task status cannot be determined"
        
        def get(self, timeout=None, propagate=True, interval=0.5, no_ack=True, follow_parents=True):
            """Raises NotImplementedError when Celery is unavailable."""
            raise NotImplementedError(
                "Celery is not installed. Task results cannot be retrieved. "
                "Install Celery to enable async task processing."
            )
        
        def ready(self):
            """Always returns False when Celery is unavailable."""
            return False
    
    Celery = MockCeleryApp
    CeleryAsyncResult = AsyncResult


def is_celery_available() -> bool:
    """
    Check if Celery is available and installed.
    
    Returns:
        True if Celery is installed and available, False otherwise
    """
    return CELERY_AVAILABLE


# Export the compatibility layer
__all__ = ['shared_task', 'AsyncResult', 'Celery', 'is_celery_available', 'CELERY_AVAILABLE']

