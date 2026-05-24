"""Run the Slack <-> Claude Code bridge.

Usage:
    python manage.py run_slackbot

Required env vars:
    SLACK_APP_TOKEN          xapp-... (Socket Mode app-level token)
    SLACK_BOT_TOKEN          xoxb-... (Bot User OAuth Token)

Optional env vars:
    ANTHROPIC_API_KEY        sk-ant-... (Claude API key). If unset, the inner
                             Claude Code falls back to subscription auth from
                             ~/.claude/.credentials.json (mounted from host).
    SLACK_ALLOWED_CHANNELS   comma-separated Slack channel IDs (e.g. C01,G02).
                             If empty, *all* channels are allowed — strongly
                             discouraged.
    SLACK_ALLOWED_USERS      comma-separated Slack user IDs (e.g. U01,U02).
                             If empty, *all* users are allowed — strongly
                             discouraged.
    SLACKBOT_IDLE_TIMEOUT    seconds before an idle thread session is closed
                             (default 1800).
    SLACKBOT_WORKING_DIR     repo path the inner Claude Code operates in
                             (default /app).
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys

from django.core.management.base import BaseCommand, CommandError

from slack_bot.bot import SlackClaudeBot


def _split_csv(value: str | None) -> set[str]:
    if not value:
        return set()
    return {x.strip() for x in value.split(",") if x.strip()}


class Command(BaseCommand):
    help = "Run the Slack Socket Mode listener that bridges to Claude Code."

    def handle(self, *args, **options):
        logging.basicConfig(
            level=os.environ.get("SLACKBOT_LOG_LEVEL", "INFO"),
            format="%(asctime)s %(levelname)s %(name)s :: %(message)s",
            stream=sys.stdout,
        )

        app_token = os.environ.get("SLACK_APP_TOKEN")
        bot_token = os.environ.get("SLACK_BOT_TOKEN")
        if not app_token or not bot_token:
            raise CommandError(
                "SLACK_APP_TOKEN and SLACK_BOT_TOKEN must both be set."
            )
        if not os.environ.get("ANTHROPIC_API_KEY"):
            self.stderr.write(
                "ANTHROPIC_API_KEY is not set — falling back to subscription auth "
                "in ~/.claude/.credentials.json (mounted from host)."
            )

        allowed_channels = _split_csv(os.environ.get("SLACK_ALLOWED_CHANNELS"))
        allowed_users = _split_csv(os.environ.get("SLACK_ALLOWED_USERS"))
        if not allowed_channels:
            self.stderr.write(
                "WARNING: SLACK_ALLOWED_CHANNELS is empty — bot will respond in any channel it's invited to."
            )
        if not allowed_users:
            self.stderr.write(
                "WARNING: SLACK_ALLOWED_USERS is empty — bot will respond to any user who mentions it."
            )

        bot = SlackClaudeBot(
            app_token=app_token,
            bot_token=bot_token,
            allowed_channels=allowed_channels,
            allowed_users=allowed_users,
        )

        try:
            asyncio.run(bot.start())
        except KeyboardInterrupt:
            self.stdout.write("shutting down")
