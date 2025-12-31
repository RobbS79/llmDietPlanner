"""
Admin interface for diet_planner models.
"""
import sys
import traceback
from django.contrib import admin
from django.contrib import messages
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.core.exceptions import PermissionDenied
from .models import DietaryGoal, DietaryPlan

# Log that admin module is being loaded
print("[DEBUG STARTUP] diet_planner/admin.py: Module is being imported", file=sys.stderr, flush=True)

try:
    print("[DEBUG STARTUP] diet_planner/admin.py: Attempting to import models", file=sys.stderr, flush=True)
    # Models are already imported above, but let's verify
    print(f"[DEBUG STARTUP] diet_planner/admin.py: DietaryGoal = {DietaryGoal}", file=sys.stderr, flush=True)
    print(f"[DEBUG STARTUP] diet_planner/admin.py: DietaryPlan = {DietaryPlan}", file=sys.stderr, flush=True)
except Exception as e:
    print(f"[DEBUG STARTUP ERROR] diet_planner/admin.py: Error importing models: {str(e)}", file=sys.stderr, flush=True)
    print(f"[DEBUG STARTUP ERROR] Traceback: {traceback.format_exc()}", file=sys.stderr, flush=True)


try:
    @admin.register(DietaryGoal)
    class DietaryGoalAdmin(admin.ModelAdmin):
        """Admin interface for DietaryGoal model."""
        print("[DEBUG STARTUP] diet_planner/admin.py: Registering DietaryGoalAdmin", file=sys.stderr, flush=True)
        
        def changelist_view(self, request, extra_context=None):
            """Override to add debug logging."""
            import sys
            print(f"[DEBUG ADMIN] DietaryGoalAdmin.changelist_view: User {request.user.username} accessing changelist", file=sys.stderr, flush=True)
            try:
                return super().changelist_view(request, extra_context)
            except Exception as e:
                error_msg = str(e)
                error_trace = traceback.format_exc()
                print(f"[DEBUG ADMIN ERROR] DietaryGoalAdmin.changelist_view: {error_msg}", file=sys.stderr, flush=True)
                print(f"[DEBUG ADMIN ERROR] Traceback: {error_trace}", file=sys.stderr, flush=True)
                raise
        
        def changeform_view(self, request, object_id=None, form_url='', extra_context=None):
            """Override to add debug logging."""
            import sys
            print(f"[DEBUG ADMIN] DietaryGoalAdmin.changeform_view: User {request.user.username} accessing object {object_id}", file=sys.stderr, flush=True)
            try:
                return super().changeform_view(request, object_id, form_url, extra_context)
            except Exception as e:
                error_msg = str(e)
                error_trace = traceback.format_exc()
                print(f"[DEBUG ADMIN ERROR] DietaryGoalAdmin.changeform_view: {error_msg}", file=sys.stderr, flush=True)
                print(f"[DEBUG ADMIN ERROR] Traceback: {error_trace}", file=sys.stderr, flush=True)
                raise
        
        list_display = [
        'id',
        'user',
        'status',
        'country',
        'city',
        'currency',
        'language_code',
        'created_at',
        'completed_at',
    ]
    list_filter = [
        'status',
        'country',
        'currency',
        'language_code',
        'created_at',
    ]
    search_fields = [
        'user__username',
        'user__email',
    ]
    readonly_fields = [
        'created_at',
        'updated_at',
        'completed_at',
        'celery_task_id',
    ]
    date_hierarchy = 'created_at'
    
    def get_readonly_fields(self, request, obj=None):
        """Make encrypted fields readonly to prevent decryption errors in admin."""
        readonly = list(self.readonly_fields)
        if obj:  # Editing existing object
            readonly.extend(['prompt', 'dietary_restrictions'])
        return readonly
    
    def has_delete_permission(self, request, obj=None):
        """Allow deletion - errors are handled in model's delete method."""
        return True
    
    def delete_model(self, request, obj):
        """Override delete to handle errors gracefully."""
        try:
            obj.delete()
            messages.success(request, f"Dietary Goal {obj.id} deleted successfully.")
        except Exception as e:
            messages.error(
                request,
                f"Error deleting Dietary Goal {obj.id}: {str(e)}. "
                "The goal may have been partially deleted. Please check the database."
            )
            # Re-raise to show error in admin
            raise
    
    def delete_queryset(self, request, queryset):
        """Handle bulk deletion with error handling."""
        deleted_count = 0
        errors = []
        
        for obj in queryset:
            try:
                obj.delete()
                deleted_count += 1
            except Exception as e:
                errors.append(f"Goal {obj.id}: {str(e)}")
        
        if deleted_count > 0:
            messages.success(request, f"Successfully deleted {deleted_count} dietary goal(s).")
        
        if errors:
            messages.error(request, f"Errors deleting some goals: {'; '.join(errors)}")
    
    fieldsets = (
        ('User Information', {
            'fields': ('user',)
        }),
        ('Dietary Information', {
            'fields': ('prompt', 'dietary_restrictions')
        }),
        ('Status & Processing', {
            'fields': ('status', 'celery_task_id', 'completed_at')
        }),
        ('Location', {
            'fields': ('country', 'city', 'currency', 'language_code'),
            'description': 'Currency is auto-determined from country'
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at')
        }),
    )
    print("[DEBUG STARTUP] diet_planner/admin.py: DietaryGoalAdmin registered successfully", file=sys.stderr, flush=True)
except Exception as e:
    error_msg = str(e)
    error_trace = traceback.format_exc()
    print(f"[DEBUG STARTUP ERROR] diet_planner/admin.py: Failed to register DietaryGoalAdmin: {error_msg}", file=sys.stderr, flush=True)
    print(f"[DEBUG STARTUP ERROR] Traceback: {error_trace}", file=sys.stderr, flush=True)
    raise  # Re-raise to prevent silent failures


try:
    @admin.register(DietaryPlan)
    class DietaryPlanAdmin(admin.ModelAdmin):
        print("[DEBUG STARTUP] diet_planner/admin.py: Registering DietaryPlanAdmin", file=sys.stderr, flush=True)
        
        def changelist_view(self, request, extra_context=None):
            """Override to add debug logging."""
            import sys
            print(f"[DEBUG ADMIN] DietaryPlanAdmin.changelist_view: User {request.user.username} accessing changelist", file=sys.stderr, flush=True)
            try:
                return super().changelist_view(request, extra_context)
            except Exception as e:
                error_msg = str(e)
                error_trace = traceback.format_exc()
                print(f"[DEBUG ADMIN ERROR] DietaryPlanAdmin.changelist_view: {error_msg}", file=sys.stderr, flush=True)
                print(f"[DEBUG ADMIN ERROR] Traceback: {error_trace}", file=sys.stderr, flush=True)
                raise
        
        def changeform_view(self, request, object_id=None, form_url='', extra_context=None):
            """Override to add debug logging."""
            import sys
            print(f"[DEBUG ADMIN] DietaryPlanAdmin.changeform_view: User {request.user.username} accessing object {object_id}", file=sys.stderr, flush=True)
            try:
                return super().changeform_view(request, object_id, form_url, extra_context)
            except Exception as e:
                error_msg = str(e)
                error_trace = traceback.format_exc()
                print(f"[DEBUG ADMIN ERROR] DietaryPlanAdmin.changeform_view: {error_msg}", file=sys.stderr, flush=True)
                print(f"[DEBUG ADMIN ERROR] Traceback: {error_trace}", file=sys.stderr, flush=True)
                raise
    """Admin interface for DietaryPlan model."""
    list_display = [
        'id',
        'dietary_goal',
        'total_price',
        'currency',
        'created_at',
    ]
    list_filter = [
        'currency',
        'created_at',
    ]
    readonly_fields = [
        'created_at',
        'updated_at',
    ]
    date_hierarchy = 'created_at'
    
    fieldsets = (
        ('Goal Reference', {
            'fields': ('dietary_goal',)
        }),
        ('LLM Generated Content', {
            'fields': ('meal_ideas', 'shopping_list'),
            'description': 'Content generated by LLM (meal ideas and shopping list)'
        }),
        ('Price Information', {
            'fields': ('total_price', 'currency'),
            'description': 'Calculated by Django from database (not LLM)'
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at')
        }),
    )
    print("[DEBUG STARTUP] diet_planner/admin.py: DietaryPlanAdmin registered successfully", file=sys.stderr, flush=True)
    
    # Log all registered models
    print(f"[DEBUG STARTUP] diet_planner/admin.py: All registered models in admin: {list(admin.site._registry.keys())}", file=sys.stderr, flush=True)
    print(f"[DEBUG STARTUP] diet_planner/admin.py: DietaryGoal in registry: {DietaryGoal in admin.site._registry}", file=sys.stderr, flush=True)
    print(f"[DEBUG STARTUP] diet_planner/admin.py: DietaryPlan in registry: {DietaryPlan in admin.site._registry}", file=sys.stderr, flush=True)
except Exception as e:
    error_msg = str(e)
    error_trace = traceback.format_exc()
    print(f"[DEBUG STARTUP ERROR] diet_planner/admin.py: Failed to register DietaryPlanAdmin: {error_msg}", file=sys.stderr, flush=True)
    print(f"[DEBUG STARTUP ERROR] Traceback: {error_trace}", file=sys.stderr, flush=True)
    raise  # Re-raise to prevent silent failures
