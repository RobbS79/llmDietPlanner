"""
Signal handlers for diet_planner app.
Handles graceful deletion of related objects when users are deleted.
"""
from django.db.models.signals import pre_delete
from django.dispatch import receiver
from django.contrib.auth.models import User
from .models import DietaryGoal
import logging

logger = logging.getLogger(__name__)


@receiver(pre_delete, sender=User)
def handle_user_deletion(sender, instance, **kwargs):
    """
    Handle User deletion gracefully.
    Pre-deletes related DietaryGoal objects to avoid cascade issues with encrypted fields.
    """
    try:
        # Get all dietary goals for this user
        dietary_goals = DietaryGoal.objects.filter(user=instance)
        goal_count = dietary_goals.count()
        
        if goal_count > 0:
            logger.info(
                f"Deleting {goal_count} dietary goal(s) for user {instance.username} (ID: {instance.id})"
            )
            
            # Delete each goal individually to handle encrypted fields gracefully
            for goal in dietary_goals:
                try:
                    goal.delete()
                except Exception as e:
                    logger.error(
                        f"Error deleting DietaryGoal {goal.id} for user {instance.username}: {str(e)}"
                    )
                    # Continue with other goals even if one fails
                    continue
            
            logger.info(
                f"Successfully handled deletion of dietary goals for user {instance.username}"
            )
    except Exception as e:
        logger.error(
            f"Error in handle_user_deletion signal for user {instance.username}: {str(e)}"
        )
        # Don't raise - let the deletion continue
        # The model's delete method will handle individual goal deletions

