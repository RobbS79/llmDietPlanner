"""
Signal handlers for diet_planner app.
Handles graceful deletion of related objects when users are deleted.
"""
from django.db.models.signals import pre_delete
from django.dispatch import receiver
from django.contrib.auth.models import User
from .models import DietaryGoal
import logging
import json
import traceback
from pathlib import Path

logger = logging.getLogger(__name__)
DEBUG_LOG_PATH = Path(__file__).parent.parent / '.cursor' / 'debug.log'


def _debug_log(hypothesis_id, location, message, data=None):
    """Write debug log entry to both file and Django logger."""
    try:
        log_entry = {
            "sessionId": "debug-session",
            "runId": "run1",
            "hypothesisId": hypothesis_id,
            "location": location,
            "message": message,
            "data": data or {},
            "timestamp": __import__('time').time() * 1000
        }
        # Write to file (for local debugging)
        try:
            with open(DEBUG_LOG_PATH, 'a') as f:
                f.write(json.dumps(log_entry) + '\n')
        except Exception:
            pass
        # Also log to Django logger (for DigitalOcean logs)
        logger.info(f"[DEBUG {hypothesis_id}] {location}: {message} | Data: {json.dumps(data or {})}")
    except Exception:
        pass  # Don't break execution if logging fails


@receiver(pre_delete, sender=User)
def handle_user_deletion(sender, instance, **kwargs):
    """
    Handle User deletion gracefully.
    Pre-deletes related DietaryGoal objects to avoid cascade issues with encrypted fields.
    """
    # #region agent log
    _debug_log("A", "signals.py:handle_user_deletion", "Signal handler entry", {
        "user_id": instance.id,
        "username": instance.username
    })
    # #endregion
    
    try:
        # #region agent log
        _debug_log("A", "signals.py:handle_user_deletion", "Before querying dietary goals")
        # #endregion
        
        # Get all dietary goals for this user
        dietary_goals = DietaryGoal.objects.filter(user=instance)
        goal_count = dietary_goals.count()
        
        # #region agent log
        _debug_log("A", "signals.py:handle_user_deletion", "After querying dietary goals", {
            "goal_count": goal_count
        })
        # #endregion
        
        if goal_count > 0:
            logger.info(
                f"Deleting {goal_count} dietary goal(s) for user {instance.username} (ID: {instance.id})"
            )
            
            # Delete each goal individually to handle encrypted fields gracefully
            for idx, goal in enumerate(dietary_goals):
                # #region agent log
                _debug_log("A", "signals.py:handle_user_deletion", f"Before deleting goal {idx+1}/{goal_count}", {
                    "goal_id": goal.id
                })
                # #endregion
                
                try:
                    goal.delete()
                    
                    # #region agent log
                    _debug_log("A", "signals.py:handle_user_deletion", f"Successfully deleted goal {goal.id}")
                    # #endregion
                except Exception as e:
                    error_msg = str(e)
                    error_trace = traceback.format_exc()
                    
                    # #region agent log
                    _debug_log("A", "signals.py:handle_user_deletion", f"Error deleting goal {goal.id}", {
                        "error": error_msg,
                        "traceback": error_trace
                    })
                    # #endregion
                    
                    logger.error(
                        f"Error deleting DietaryGoal {goal.id} for user {instance.username}: {error_msg}"
                    )
                    # Continue with other goals even if one fails
                    continue
            
            # #region agent log
            _debug_log("A", "signals.py:handle_user_deletion", "All goals processed successfully")
            # #endregion
            
            logger.info(
                f"Successfully handled deletion of dietary goals for user {instance.username}"
            )
        else:
            # #region agent log
            _debug_log("A", "signals.py:handle_user_deletion", "No dietary goals to delete")
            # #endregion
    except Exception as e:
        error_msg = str(e)
        error_trace = traceback.format_exc()
        
        # #region agent log
        _debug_log("A", "signals.py:handle_user_deletion", "Exception in signal handler", {
            "error": error_msg,
            "traceback": error_trace
        })
        # #endregion
        
        logger.error(
            f"Error in handle_user_deletion signal for user {instance.username}: {error_msg}"
        )
        # Don't raise - let the deletion continue
        # The model's delete method will handle individual goal deletions
    
    # #region agent log
    _debug_log("A", "signals.py:handle_user_deletion", "Signal handler exit")
    # #endregion

