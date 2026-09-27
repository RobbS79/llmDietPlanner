"""Approval moved from ✅ reactions to card buttons (2026-09-24). Drafts posted
before this deploy have no buttons and would sit unpublishable forever, so
they are closed out here; the owner re-drafts anything still wanted."""
from django.db import migrations

REASON = 'superseded: approval moved to Slack buttons'


def reject_drafts(apps, schema_editor):
    SocialPost = apps.get_model('social', 'SocialPost')
    SocialPost.objects.filter(status='draft').update(status='rejected', error=REASON)


class Migration(migrations.Migration):

    dependencies = [
        ('social', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(reject_drafts, migrations.RunPython.noop),
    ]
