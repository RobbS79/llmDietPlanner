from llm_diet_planner_project.celery_compat import shared_task
from analytics import capi


@shared_task
def send_capi_event_task(**kwargs) -> bool:
    """Fire-and-forget CAPI send. kwargs match capi.send_event signature."""
    return capi.send_event(**kwargs)
