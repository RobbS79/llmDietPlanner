# Generated manually for adding PAYMENT_PENDING status and shopify_order_id field

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("diet_planner", "0010_fix_index_names"),
    ]

    operations = [
        migrations.AddField(
            model_name="dietarygoal",
            name="shopify_order_id",
            field=models.CharField(
                blank=True,
                help_text="Shopify order ID after payment (for fulfillment tracking)",
                max_length=255,
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name="dietarygoal",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending", "Pending"),
                    ("awaiting_payment", "Awaiting Payment"),
                    ("payment_pending", "Payment Pending"),
                    ("payment_confirmed", "Payment Confirmed"),
                    ("processing", "Processing"),
                    ("processing_meal_plan", "Generating Meal Plan"),
                    ("processing_shopping_list", "Creating Shopping List"),
                    ("validating", "Validating"),
                    ("completed", "Completed"),
                    ("failed", "Failed"),
                    ("refund_eligible", "Refund Eligible"),
                ],
                default="pending",
                help_text="Processing status of the dietary goal",
                max_length=30,
            ),
        ),
    ]

