"""Read-mostly admin for SocialPost: approval and publication happen in Slack
and the scheduled jobs, not here."""
from django.contrib import admin

from .models import SocialPost


@admin.register(SocialPost)
class SocialPostAdmin(admin.ModelAdmin):
    list_display = ('iso_week', 'kind', 'scheduled_for', 'status',
                    'facebook_post_id', 'pinterest_pin_id', 'approved_by')
    list_filter = ('kind', 'status')
    readonly_fields = ('facts', 'channels', 'slack_channel', 'slack_ts', 'approved_by',
                       'facebook_post_id', 'pinterest_pin_id', 'error',
                       'created_at', 'published_at')
    search_fields = ('iso_week', 'caption')

    def get_queryset(self, request):
        return super().get_queryset(request).defer('image')
