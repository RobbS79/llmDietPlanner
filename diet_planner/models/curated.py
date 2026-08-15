# diet_planner/models/curated.py
"""
Curated recipe corpus (Direction B — real-recipe grounded meal planning).

A `CuratedRecipe` is a real, attributed dish — sourced worldwide, rewritten
into novice-clear Czech steps, with ingredients pre-mapped to the store
catalog at curation time. The planner *retrieves + scales* these instead of
asking the LLM to invent every meal from scratch.

Distinct from the per-plan `Recipe` (core.py), which is `meal_identifier`-keyed
and generated fresh per goal. A plan's meal references a `CuratedRecipe` via
`curated_recipe_id` and stores the scaled ingredient quantities for that plan.

See docs/recipe-grounding-plan.md §3.
"""
from __future__ import annotations

from django.conf import settings as django_settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils.text import slugify

from diet_planner.models.catalog import Availability


class CuratedRecipe(models.Model):
    """A vetted, attributed real dish in the curated corpus."""

    class Difficulty(models.TextChoices):
        EASY = 'easy', 'Easy'
        MEDIUM = 'medium', 'Medium'

    class Status(models.TextChoices):
        DRAFT = 'draft', 'Draft'
        VETTED = 'vetted', 'Vetted'
        PUBLISHED = 'published', 'Published'

    class Origin(models.TextChoices):
        CURATED = 'curated', 'Curated batch'
        CHAT_WEB = 'chat_web', 'Chat web research'

    class DishRole(models.TextChoices):
        MAIN = 'main', 'Main — can carry an oběd/večeře'
        LIGHT = 'light', 'Light — breakfast/quick-supper dish'
        SOUP = 'soup', 'Soup — brothy, accompanies rather than carries'
        SIDE = 'side', 'Side — salad/dip/accompaniment'
        DESSERT = 'dessert', 'Dessert / sweet'

    # --- Identity / presentation -------------------------------------------
    slug = models.SlugField(max_length=255, unique=True, db_index=True)
    name_cs = models.CharField(max_length=255, help_text="Czech dish name (real, named dish)")
    name_en = models.CharField(max_length=255, blank=True, help_text="Optional English gloss")
    description = models.TextField(
        blank=True,
        help_text="1-2 appetizing sentences in Czech",
    )

    # --- Classification / retrieval keys -----------------------------------
    meal_types = models.JSONField(
        default=list,
        help_text="Slots this can fill: breakfast/lunch/dinner/snack/small_meal",
    )
    cuisine = models.CharField(
        max_length=40,
        blank=True,
        db_index=True,
        help_text="czech/italian/asian/mediterranean/... — for variety + soft ranking, not a filter",
    )
    dish_role = models.CharField(
        max_length=10,
        choices=DishRole.choices,
        blank=True,
        default='',
        db_index=True,
        help_text=(
            "What the dish can CARRY (meal_types says when it may appear; this "
            "says whether it can be the meal). '' = untagged legacy — passes "
            "every slot until retag_dish_roles has run."
        ),
    )
    difficulty = models.CharField(
        max_length=10,
        choices=Difficulty.choices,
        default=Difficulty.EASY,
        db_index=True,
    )
    dietary_tags = models.JSONField(
        default=list,
        help_text="vegetarian, vegan, gluten_free, dairy_free, high_protein, low_carb, ...",
    )

    # --- Content -----------------------------------------------------------
    ingredients = models.JSONField(
        default=list,
        help_text="[{name, quantity, unit, catalog_id?, canonical?, optional?}] — catalog-mapped at curation",
    )
    instructions = models.JSONField(
        default=list,
        help_text="Novice step schema: [{text, time_min?, tip?}]",
    )
    base_servings = models.IntegerField(
        default=1,
        validators=[MinValueValidator(1)],
        help_text="Portions the base quantities/nutrition describe",
    )
    base_nutrition = models.JSONField(
        default=dict,
        blank=True,
        help_text="Per base_servings: {calories, protein, carbs, fat}",
    )
    prep_time = models.IntegerField(null=True, blank=True, validators=[MinValueValidator(0)])
    cook_time = models.IntegerField(null=True, blank=True, validators=[MinValueValidator(0)])

    # --- Provenance / attribution ------------------------------------------
    source_url = models.URLField(max_length=500, help_text="The concrete linked source recipe (credit)")
    source_name = models.CharField(max_length=200, help_text="Site/creator name shown to users")
    source_author = models.CharField(max_length=200, blank=True, help_text="Original author if known")
    license_note = models.CharField(
        max_length=300,
        blank=True,
        help_text='e.g. "paraphrased, linked with attribution"',
    )

    # --- Lifecycle / quality -----------------------------------------------
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.DRAFT,
        db_index=True,
    )
    origin = models.CharField(
        max_length=10,
        choices=Origin.choices,
        default=Origin.CURATED,
        db_index=True,
        help_text="curated = batch pipeline; chat_web = user-triggered web research",
    )
    created_for_user = models.ForeignKey(
        django_settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='chat_recipes',
        help_text="Requester of a chat_web draft; only their plan may use it pre-publish",
    )
    quality_score = models.JSONField(
        null=True,
        blank=True,
        help_text="clarity / cultural-fit / coherence judge output",
    )
    shopping_difficulty = models.CharField(
        max_length=10,
        choices=Availability.choices,
        default=Availability.UNRATED,
        db_index=True,
        help_text=(
            "Worst non-optional ingredient's availability. Denormalised — "
            "recompute_shopping_difficulty is the writer. INVARIANT: the "
            "rollup never writes 'unrated' (it maps an unrated ingredient to "
            "'findable'), so 'unrated' here means ONLY 'not yet computed'."
        ),
    )
    shopping_blockers = models.JSONField(
        default=list,
        blank=True,
        help_text="Canonical slugs rated worse than common that set shopping_difficulty",
    )
    adaptation_note = models.CharField(
        max_length=300,
        blank=True,
        help_text='Disclosed change vs the credited source, e.g. "Upraveno pro dostupnost v českých obchodech"',
    )
    original_ingredients = models.JSONField(
        null=True,
        blank=True,
        help_text="Pre-rewrite snapshot of `ingredients`; makes a substitution revertible",
    )
    usage_count = models.IntegerField(default=0, help_text="For variety/popularity ranking")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Curated Recipe"
        indexes = [
            models.Index(fields=['status', 'cuisine']),
            models.Index(fields=['status', 'difficulty']),
        ]

    def __str__(self) -> str:
        return f"{self.name_cs} [{self.status}]"

    def save(self, *args, **kwargs):
        if not self.slug and self.name_cs:
            self.slug = slugify(self.name_cs)[:255]
        super().save(*args, **kwargs)

    # --- Helpers -----------------------------------------------------------
    @property
    def total_time(self) -> int:
        return (self.prep_time or 0) + (self.cook_time or 0)

    def is_catalog_mapped(self) -> bool:
        """Every non-optional ingredient resolves to a catalog_id or canonical."""
        for ing in self.ingredients or []:
            if ing.get('optional'):
                continue
            if not ing.get('catalog_id') and not ing.get('canonical'):
                return False
        return True


class RecipeResearchJob(models.Model):
    """One user-triggered web recipe research run, polled by the refine chat."""

    class Status(models.TextChoices):
        QUEUED = 'queued', 'Queued'
        SEARCHING = 'searching', 'Searching'
        CURATING = 'curating', 'Curating'
        READY = 'ready', 'Ready'
        FAILED = 'failed', 'Failed'

    user = models.ForeignKey(
        django_settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='research_jobs',
    )
    meal_identifier = models.CharField(max_length=64)
    query = models.CharField(max_length=300)
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.QUEUED, db_index=True,
    )
    result_recipe = models.ForeignKey(
        CuratedRecipe, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='research_jobs',
    )
    fail_reason = models.CharField(
        max_length=60, blank=True,
        help_text="machine code: no_sources / all_sources_failed / gates_failed / error",
    )
    reply_text = models.TextField(
        blank=True, help_text="Czech chat line shown when the job finishes",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self) -> str:
        return f"research #{self.pk} [{self.status}] {self.query[:40]}"
