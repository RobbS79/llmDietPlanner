# diet_planner/migrations/0012_add_historic_nutrition_plan.py
"""
Generated manually to support Historic Nutrition Plan library and the 
selection reference in DietaryGoal.
"""

import encrypted_model_fields.fields
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("diet_planner", "0011_add_payment_pending_status_and_order_id"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="HistoricNutritionPlan",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "name",
                    models.CharField(
                        help_text="A friendly name for this plan (e.g., 'Winter 2024 Clinical Diet')",
                        max_length=255,
                    ),
                ),
                (
                    "content",
                    encrypted_model_fields.fields.EncryptedTextField(
                        help_text="The actual clinical document or past plan text (encrypted)"
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "user",
                    models.ForeignKey(
                        help_text="User who owns this historic plan record",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="historic_plans",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Historic Nutrition Plan",
                "verbose_name_plural": "Historic Nutrition Plans",
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddField(
            model_name="dietarygoal",
            name="historic_plan_reference",
            field=models.ForeignKey(
                blank=True,
                help_text="The historic plan to be used as a baseline for this new goal",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="referenced_goals",
                to="diet_planner.historicnutritionplan",
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
    ]