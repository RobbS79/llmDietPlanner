from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('login_app', '0003_userprofile_auth_provider_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='userprofile',
            name='onboarding_completed',
            field=models.BooleanField(default=False, help_text='Whether user has completed the onboarding quiz'),
        ),
        migrations.AddField(
            model_name='userprofile',
            name='dietary_preferences',
            field=models.JSONField(blank=True, default=dict, help_text='Onboarding quiz answers (goal, dietary_styles, allergies, household, budget, cooking, shop)'),
        ),
    ]
