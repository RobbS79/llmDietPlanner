from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('diet_planner', '0020_historic_plan_pdf_fields'),
    ]

    operations = [
        migrations.AlterField(
            model_name='scraperun',
            name='method',
            field=models.CharField(
                choices=[
                    ('LLM', 'Gemini LLM extraction'),
                    ('STRUCTURED', 'BeautifulSoup/CSS'),
                    ('HYBRID', 'Structured + LLM fallback'),
                    ('CATALOG', 'Full catalog (sitemap-driven)'),
                ],
                default='HYBRID',
                max_length=15,
            ),
        ),
    ]
