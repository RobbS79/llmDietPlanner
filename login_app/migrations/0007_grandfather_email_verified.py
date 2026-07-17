from django.db import migrations


def grandfather_active_users(apps, schema_editor):
    """Mark existing ACTIVE users as email_verified so the new plan-generation
    verification gate does not retroactively lock them out.

    Enforcement (VerifyEmailView + DietaryGoalCreateView) then applies only to
    NEW sign-ups, which are created email_verified=False and must confirm their
    address. Inactive users are intentionally left unverified.
    """
    UserProfile = apps.get_model('login_app', 'UserProfile')
    UserProfile.objects.filter(user__is_active=True, email_verified=False).update(
        email_verified=True
    )


def noop(apps, schema_editor):
    # Irreversible by design: we can't know which users were verified before.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('login_app', '0006_accountdeletion'),
    ]

    operations = [
        migrations.RunPython(grandfather_active_users, noop),
    ]
