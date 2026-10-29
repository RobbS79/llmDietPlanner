"""Which public Recipe row is THE page for a recipe.

Every plan stores its own Recipe rows and Recipe.save() auto-publishes them, so
the same corpus recipe is public many times over. A recipe is identified by
(normalized name, source_url); the oldest row of each group is the public page
and the others redirect to it. Computed per call because rows can be renamed in
place (a regenerated meal), which moves them between groups. The public set is
small (tens to hundreds), so one values_list scan is fine.
"""
from diet_planner.models import Recipe


def _key(name, source_url):
    return ((name or '').strip().lower(), (source_url or '').strip())


def canonical_map():
    """{public recipe pk: pk of the row that is its public page}."""
    first_by_key = {}
    mapping = {}
    rows = (Recipe.objects.filter(is_public=True)
            .order_by('pk').values_list('pk', 'name', 'source_url'))
    for pk, name, source_url in rows:
        mapping[pk] = first_by_key.setdefault(_key(name, source_url), pk)
    return mapping


def canonical_public_recipes():
    """Public Recipe queryset with one row per recipe."""
    ids = {canonical for canonical in canonical_map().values()}
    return Recipe.objects.filter(pk__in=ids)
