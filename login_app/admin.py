"""
Admin configuration for login_app.
Custom User admin to handle deletion gracefully.
"""
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User
from django.contrib import messages
import json
import traceback
from pathlib import Path

DEBUG_LOG_PATH = Path(__file__).parent.parent / '.cursor' / 'debug.log'


def _debug_log(hypothesis_id, location, message, data=None):
    """Write debug log entry to both file and Django logger."""
    import logging
    logger = logging.getLogger(__name__)
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


# Unregister default User admin and register custom one
admin.site.unregister(User)


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """Custom User admin with improved deletion handling."""
    
    def delete_model(self, request, obj):
        """Override delete to handle errors gracefully."""
        # #region agent log
        _debug_log("D", "login_app/admin.py:UserAdmin.delete_model", "Admin delete_model entry", {
            "user_id": obj.id,
            "username": obj.username
        })
        # #endregion
        
        try:
            # #region agent log
            _debug_log("D", "login_app/admin.py:UserAdmin.delete_model", "Before calling obj.delete()")
            # #endregion
            
            obj.delete()
            
            # #region agent log
            _debug_log("D", "login_app/admin.py:UserAdmin.delete_model", "obj.delete() completed successfully")
            # #endregion
            
            messages.success(request, f"User {obj.username} deleted successfully.")
        except Exception as e:
            error_msg = str(e)
            error_trace = traceback.format_exc()
            
            # #region agent log
            _debug_log("D", "login_app/admin.py:UserAdmin.delete_model", "Exception in delete_model", {
                "error": error_msg,
                "traceback": error_trace
            })
            # #endregion
            
            messages.error(
                request,
                f"Error deleting user {obj.username}: {error_msg}"
            )
            # Re-raise to show error in admin
            raise
    
    def delete_queryset(self, request, queryset):
        """Handle bulk deletion with error handling."""
        # #region agent log
        _debug_log("D", "login_app/admin.py:UserAdmin.delete_queryset", "Bulk delete entry", {
            "count": queryset.count()
        })
        # #endregion
        
        deleted_count = 0
        errors = []
        
        for obj in queryset:
            # #region agent log
            _debug_log("D", "login_app/admin.py:UserAdmin.delete_queryset", f"Deleting user {obj.id}", {
                "username": obj.username
            })
            # #endregion
            
            try:
                obj.delete()
                deleted_count += 1
                
                # #region agent log
                _debug_log("D", "login_app/admin.py:UserAdmin.delete_queryset", f"Successfully deleted user {obj.id}")
                # #endregion
            except Exception as e:
                error_msg = str(e)
                error_trace = traceback.format_exc()
                
                # #region agent log
                _debug_log("D", "login_app/admin.py:UserAdmin.delete_queryset", f"Error deleting user {obj.id}", {
                    "error": error_msg,
                    "traceback": error_trace
                })
                # #endregion
                
                errors.append(f"User {obj.username} (ID: {obj.id}): {error_msg}")
        
        if deleted_count > 0:
            messages.success(request, f"Successfully deleted {deleted_count} user(s).")
        
        if errors:
            messages.error(request, f"Errors deleting some users: {'; '.join(errors)}")
