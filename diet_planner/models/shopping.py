from django.conf import settings
from django.db import models


class SavedShoppingList(models.Model):
    """A visitor's picked recipes kept after signup (spec 2026-11-03).

    recipe_ids are CuratedRecipe ids; the list itself is recomposed on read so
    deals and rounding are always current.
    """
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                             related_name='saved_shopping_lists')
    recipe_ids = models.JSONField(default=list)
    people = models.PositiveSmallIntegerField(default=2)
    at_home = models.JSONField(default=list, help_text='canonical|unit keys marked "mám doma"')
    query = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']
