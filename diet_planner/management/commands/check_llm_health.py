"""Canary: can prod actually reach the LLM right now?

Four Gemini outages (credits, account denial, retired model, billing dunning)
were each found by accident — days late, through unrelated work — because
nothing asked. Run this on a schedule; it exits non-zero when the answer is no,
so a scheduled job goes red.

Usage:
    python manage.py check_llm_health
"""
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from diet_planner.services.llm_health import (
    default_generate, default_post, notify_slack, probe_llm,
)


class Command(BaseCommand):
    help = 'Probe the LLM and alert if it is unreachable'
    #: Seams for the tests; not argparse flags, so they stay off the CLI.
    stealth_options = ('generate', 'post')

    def handle(self, *args, **options):
        # Injectable for tests; production always takes the defaults.
        generate = options.get('generate') or default_generate
        post = options.get('post') or default_post

        model = getattr(settings, 'GEMINI_MODEL', '(unset)')
        result = probe_llm(generate)

        if result.ok:
            self.stdout.write(self.style.SUCCESS(
                f'[llm_health] OK model={model} reply={result.detail!r}'))
            return

        text = (f':rotating_light: Vařto prod: LLM probe FAILED\n'
                f'model=`{model}` error=`{result.error_type}`\n'
                f'```{result.detail[:800]}```')
        delivered = notify_slack(
            text,
            webhook_url=getattr(settings, 'LLM_HEALTH_SLACK_WEBHOOK_URL', ''),
            post=post,
        )
        if not delivered:
            self.stderr.write('[llm_health] alert NOT delivered '
                              '(no webhook configured, or Slack failed)')
        # Non-zero exit is what makes a scheduled job visibly red.
        raise CommandError(
            f'[llm_health] LLM unreachable: {result.error_type}: {result.detail}')
