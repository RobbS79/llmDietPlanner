# Generated manually to add missing auth provider fields

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("login_app", "0002_alter_userprofile_free_generations_remaining"),
    ]

    operations = [
        migrations.AddField(
            model_name="userprofile",
            name="primary_auth_provider",
            field=models.CharField(
                max_length=20,
                choices=[
                    ("email", "Email"),
                    ("google", "Google"),
                    ("facebook", "Facebook"),
                ],
                default="email",
                help_text="Primary authentication provider used for registration",
            ),
        ),
        migrations.AddField(
            model_name="userprofile",
            name="email_verified",
            field=models.BooleanField(
                default=False,
                help_text="Whether email has been verified (via email link or trusted OAuth provider)",
            ),
        ),
    ]
