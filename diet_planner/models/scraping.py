# diet_planner/models/scraping.py
"""
Scraping audit models: track each scraping execution for monitoring and debugging.
"""
from decimal import Decimal

from django.db import models

from .catalog import GroceryStore


class ScrapeRun(models.Model):
    """Audit record for each scraping execution."""

    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        RUNNING = 'RUNNING', 'Running'
        COMPLETED = 'COMPLETED', 'Completed'
        PARTIAL = 'PARTIAL', 'Partial (some errors)'
        FAILED = 'FAILED', 'Failed'

    class Method(models.TextChoices):
        LLM = 'LLM', 'Gemini LLM extraction'
        STRUCTURED = 'STRUCTURED', 'BeautifulSoup/CSS'
        HYBRID = 'HYBRID', 'Structured + LLM fallback'
        CATALOG = 'CATALOG', 'Full catalog (sitemap-driven)'

    store = models.ForeignKey(
        GroceryStore,
        on_delete=models.CASCADE,
        related_name='scrape_runs',
    )
    status = models.CharField(
        max_length=15,
        choices=Status.choices,
        default=Status.PENDING,
    )
    method = models.CharField(
        max_length=15,
        choices=Method.choices,
        default=Method.HYBRID,
    )

    # Metrics
    products_found = models.IntegerField(default=0)
    products_created = models.IntegerField(default=0)
    products_updated = models.IntegerField(default=0)
    prices_recorded = models.IntegerField(default=0)
    errors_count = models.IntegerField(default=0)

    # LLM cost tracking
    llm_input_tokens = models.IntegerField(default=0)
    llm_output_tokens = models.IntegerField(default=0)
    llm_cost_usd = models.DecimalField(
        max_digits=10, decimal_places=6, default=Decimal('0'),
    )

    source_urls = models.JSONField(default=list)
    error_log = models.TextField(blank=True)

    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    duration_seconds = models.FloatField(null=True, blank=True)

    class Meta:
        ordering = ['-started_at']
        indexes = [
            models.Index(fields=['store', '-started_at']),
            models.Index(fields=['status']),
        ]

    def __str__(self):
        return f"Scrape {self.store.code} @ {self.started_at:%Y-%m-%d %H:%M} [{self.status}]"
