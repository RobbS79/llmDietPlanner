"""Social content pipeline: weekly Facebook/Pinterest posts built from
database facts, approved in Slack, published by scheduled jobs.
See docs/superpowers/specs/2026-09-04-social-content-pipeline-design.md."""
from django.apps import AppConfig


class SocialConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'social'
    verbose_name = 'Social posts'
