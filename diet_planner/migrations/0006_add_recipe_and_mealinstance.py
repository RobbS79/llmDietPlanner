# Generated migration for Recipe and MealInstance models

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.core.validators


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("diet_planner", "0005_replace_main_courses_with_meal_flags"),
    ]

    operations = [
        migrations.CreateModel(
            name="Recipe",
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
                    "meal_identifier",
                    models.CharField(
                        db_index=True,
                        help_text="Unique identifier for the meal (format: goal_id:day_number:meal_type:meal_index)",
                        max_length=255,
                        unique=True,
                    ),
                ),
                (
                    "name",
                    models.CharField(help_text="Recipe name", max_length=255),
                ),
                (
                    "description",
                    models.TextField(
                        blank=True,
                        help_text="Recipe description",
                        null=True,
                    ),
                ),
                (
                    "instructions",
                    models.JSONField(
                        default=list,
                        help_text="Step-by-step cooking instructions (list of strings)",
                    ),
                ),
                (
                    "ingredients",
                    models.JSONField(
                        default=list,
                        help_text="List of ingredients with quantities",
                    ),
                ),
                (
                    "preparation_time",
                    models.IntegerField(
                        blank=True,
                        help_text="Preparation time in minutes",
                        null=True,
                        validators=[django.core.validators.MinValueValidator(0)],
                    ),
                ),
                (
                    "cooking_time",
                    models.IntegerField(
                        blank=True,
                        help_text="Cooking time in minutes",
                        null=True,
                        validators=[django.core.validators.MinValueValidator(0)],
                    ),
                ),
                (
                    "servings",
                    models.IntegerField(
                        default=1,
                        help_text="Number of servings",
                        validators=[django.core.validators.MinValueValidator(1)],
                    ),
                ),
                (
                    "nutritional_info",
                    models.JSONField(
                        blank=True,
                        default=dict,
                        help_text="Nutritional information (calories, protein, carbs, fat, etc.)",
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(
                        auto_now_add=True,
                        help_text="When the recipe was created (ISO-8601)",
                    ),
                ),
                (
                    "updated_at",
                    models.DateTimeField(
                        auto_now=True,
                        help_text="When the recipe was last updated (ISO-8601)",
                    ),
                ),
                (
                    "dietary_goal",
                    models.ForeignKey(
                        help_text="The dietary goal this recipe belongs to",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="recipes",
                        to="diet_planner.dietarygoal",
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="MealInstance",
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
                    "meal_identifier",
                    models.CharField(
                        db_index=True,
                        help_text="Unique identifier for the meal (format: goal_id:day_number:meal_type:meal_index)",
                        max_length=255,
                    ),
                ),
                (
                    "meal_name",
                    models.CharField(help_text="Name of the meal", max_length=255),
                ),
                (
                    "day_number",
                    models.IntegerField(help_text="Day number in the meal plan"),
                ),
                (
                    "meal_type",
                    models.CharField(
                        help_text="Type of meal (breakfast, lunch, dinner, small_meal, snack)",
                        max_length=50,
                    ),
                ),
                (
                    "is_cooked",
                    models.BooleanField(
                        default=False,
                        help_text="Whether this meal has been cooked",
                    ),
                ),
                (
                    "cooked_at",
                    models.DateTimeField(
                        blank=True,
                        help_text="When the meal was marked as cooked (ISO-8601)",
                        null=True,
                    ),
                ),
                (
                    "notes",
                    models.TextField(
                        blank=True,
                        help_text="User notes about cooking this meal",
                        null=True,
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(
                        auto_now_add=True,
                        help_text="When the meal instance was created (ISO-8601)",
                    ),
                ),
                (
                    "updated_at",
                    models.DateTimeField(
                        auto_now=True,
                        help_text="When the meal instance was last updated (ISO-8601)",
                    ),
                ),
                (
                    "dietary_goal",
                    models.ForeignKey(
                        help_text="The dietary goal this meal belongs to",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="meal_instances",
                        to="diet_planner.dietarygoal",
                    ),
                ),
                (
                    "recipe",
                    models.ForeignKey(
                        blank=True,
                        help_text="The recipe for this meal (optional, can be null if recipe not yet created)",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="instances",
                        to="diet_planner.recipe",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        help_text="User who cooked this meal",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="meal_instances",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-cooked_at", "-created_at"],
                "unique_together": {("user", "meal_identifier")},
            },
        ),
        migrations.AddIndex(
            model_name="recipe",
            index=models.Index(
                fields=["dietary_goal", "-created_at"],
                name="diet_plann_recipe_goal_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="recipe",
            index=models.Index(
                fields=["meal_identifier"], name="diet_plann_recipe_meal_id_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="mealinstance",
            index=models.Index(
                fields=["user", "-cooked_at"], name="diet_plann_mealinst_user_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="mealinstance",
            index=models.Index(
                fields=["dietary_goal", "day_number"],
                name="diet_plann_mealinst_goal_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="mealinstance",
            index=models.Index(
                fields=["meal_identifier"], name="diet_plann_mealinst_meal_id_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="mealinstance",
            index=models.Index(
                fields=["is_cooked"], name="diet_plann_mealinst_cook_idx"
            ),
        ),
    ]

