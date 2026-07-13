"""
Admin configuration for login_app.
Custom User admin to handle deletion gracefully.
"""
import sys
import json
import traceback
from pathlib import Path

# Log that this module is being loaded
print("[DEBUG STARTUP] login_app/admin.py: Module is being imported", file=sys.stderr, flush=True)

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User
from django.contrib import messages
from django.db.models import F
from django.utils import timezone

from login_app.models import UserProfile

DEBUG_LOG_PATH = Path(__file__).parent.parent / '.cursor' / 'debug.log'


def _debug_log(hypothesis_id, location, message, data=None):
    """Write debug log entry to both file and Django logger."""
    import logging
    import sys
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
        # Log to Django logger at ERROR level (always visible)
        log_msg = f"[DEBUG {hypothesis_id}] {location}: {message} | Data: {json.dumps(data or {})}"
        logger.error(log_msg)  # Use ERROR level so it's always visible
        # Also print to stderr (captured by Gunicorn/DigitalOcean)
        print(f"[DEBUG {hypothesis_id}] {location}: {message} | Data: {json.dumps(data or {})}", file=sys.stderr, flush=True)
    except Exception:
        pass  # Don't break execution if logging fails


# Unregister default User admin and register custom one
try:
    admin.site.unregister(User)
    print("[DEBUG STARTUP] login_app/admin.py: Unregistered default User admin", file=sys.stderr, flush=True)
    _debug_log("STARTUP", "login_app/admin.py", "Unregistered default User admin")
except Exception as e:
    print(f"[DEBUG STARTUP] login_app/admin.py: Error unregistering User admin: {str(e)}", file=sys.stderr, flush=True)
    _debug_log("STARTUP", "login_app/admin.py", f"Error unregistering User admin (may not be registered): {str(e)}")

try:
    @admin.register(User)
    class UserAdmin(BaseUserAdmin):
        """Custom User admin with improved deletion handling."""
        
        def __init__(self, *args, **kwargs):
            """Log when admin is initialized."""
            super().__init__(*args, **kwargs)
            print("[DEBUG STARTUP] login_app/admin.py: Custom UserAdmin initialized", file=sys.stderr, flush=True)
            _debug_log("STARTUP", "login_app/admin.py:UserAdmin.__init__", "Custom UserAdmin registered successfully")
    
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
except Exception as e:
    # If admin registration fails, log it but don't break the app
    error_msg = str(e)
    error_trace = traceback.format_exc()
    print(f"[DEBUG STARTUP ERROR] login_app/admin.py: Failed to register UserAdmin: {error_msg}", file=sys.stderr, flush=True)
    print(f"[DEBUG STARTUP ERROR] Traceback: {error_trace}", file=sys.stderr, flush=True)


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    """Admin for editing free generation credits and profile fields."""

    list_display = (
        'user',
        'user_email',
        'free_generations_remaining',
        'total_generations',
        'primary_auth_provider',
        'email_verified',
        'onboarding_completed',
        'updated_at',
    )
    list_filter = (
        'primary_auth_provider',
        'email_verified',
        'onboarding_completed',
    )
    search_fields = ('user__username', 'user__email')
    list_editable = ('free_generations_remaining',)
    readonly_fields = ('created_at', 'updated_at', 'total_generations')
    autocomplete_fields = ('user',)
    ordering = ('-updated_at',)
    actions = ('grant_1_credit', 'grant_5_credits', 'grant_10_credits')

    def _grant_credits(self, request, queryset, amount):
        updated = queryset.update(
            free_generations_remaining=F('free_generations_remaining') + amount,
            updated_at=timezone.now(),
        )
        self.message_user(
            request,
            f"Granted {amount} free credit(s) to {updated} profile(s).",
            messages.SUCCESS,
        )

    @admin.action(description="Grant 1 free credit to selected profiles")
    def grant_1_credit(self, request, queryset):
        self._grant_credits(request, queryset, 1)

    @admin.action(description="Grant 5 free credits to selected profiles")
    def grant_5_credits(self, request, queryset):
        self._grant_credits(request, queryset, 5)

    @admin.action(description="Grant 10 free credits to selected profiles")
    def grant_10_credits(self, request, queryset):
        self._grant_credits(request, queryset, 10)

    fieldsets = (
        (None, {
            'fields': ('user',),
        }),
        ('Credits', {
            'fields': ('free_generations_remaining', 'total_generations'),
            'description': 'Grant free meal-plan generations by increasing '
                           '<b>free_generations_remaining</b>.',
        }),
        ('Auth / onboarding', {
            'fields': (
                'primary_auth_provider',
                'email_verified',
                'onboarding_completed',
                'dietary_preferences',
            ),
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
        }),
    )

    def user_email(self, obj):
        return obj.user.email
    user_email.short_description = 'Email'
    user_email.admin_order_field = 'user__email'
