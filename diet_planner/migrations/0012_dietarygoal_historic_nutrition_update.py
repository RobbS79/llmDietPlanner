# Generated manually to support Historic Nutrition Context and default updates

import encrypted_model_fields.fields
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("diet_planner", "0011_add_payment_pending_status_and_order_id"),
    ]

    operations = [
        migrations.AddField(
            model_name="dietarygoal",
            name="historic_plan_context",
            field=encrypted_model_fields.fields.EncryptedTextField(
                blank=True,
                help_text="Full baseline nutrition history provided by the user for AI analysis (encrypted)",
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name="dietarygoal",
            name="currency",
            field=models.CharField(
                choices=[
                    ("PLN", "Polish Złoty"),
                    ("CZK", "Czech Koruna"),
                    ("HUF", "Hungarian Forint"),
                    ("EUR", "Euro"),
                    ("RON", "Romanian Leu"),
                    ("BGN", "Bulgarian Lev"),
                ],
                default="CZK",
                help_text="Currency for price calculations (auto-determined from country)",
                max_length=3,
            ),
        ),
        migrations.AlterField(
            model_name="dietarygoal",
            name="language_code",
            field=models.CharField(
                default="cs",
                help_text="Language code (ISO 639-1) for i18n support",
                max_length=5,
            ),
        ),
        migrations.AlterField(
            model_name="dietarygoal",
            name="prompt",
            field=encrypted_model_fields.fields.EncryptedTextField(
                help_text="User's dietary prompt, instructions, or main historic plan (encrypted)"
            ),
        ),
    ]