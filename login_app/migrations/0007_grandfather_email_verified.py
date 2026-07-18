from django.db import migrations


def grandfather_active_users(apps, schema_editor):
    """Mark existing ACTIVE users as email_verified so the new plan-generation
    verification gate does not retroactively lock them out.

    Enforcement (VerifyEmailView + DietaryGoalCreateView) then applies only to
    NEW sign-ups, which are created email_verified=False and must confirm their
    address. Inactive users are intentionally left unverified.
    """
    User = apps.get_model('auth', 'User')
    UserProfile = apps.get_model('login_app', 'UserProfile')

    # Existing profiles for active users -> verified.
    UserProfile.objects.filter(user__is_active=True, email_verified=False).update(
        email_verified=True
    )

    # Active users with NO profile row at all (edge case — the post_save signal
    # normally creates one) would otherwise be created email_verified=False by
    # the gate's get_or_create and get locked out. Backfill them as verified.
    have_profiles = set(UserProfile.objects.values_list('user_id', flat=True))
    missing_ids = (
        User.objects.filter(is_active=True)
        .exclude(id__in=have_profiles)
        .values_list('id', flat=True)
    )
    UserProfile.objects.bulk_create(
        [UserProfile(user_id=uid, email_verified=True) for uid in missing_ids]
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
