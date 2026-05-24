# slack_bot — Slack ↔ Claude Code bridge

A Django management command that opens a Slack Socket Mode connection,
listens for `app_mention` events, and routes each Slack thread to its own
persistent Claude Code session inside the same container as Django.

> **Security**: the bot grants full Claude Code (read, write, shell, git)
> over `/app` to anyone on the allowlist. Treat allowlisted users as having
> root shell on this container. **Never** widen the allowlist or run
> without one in a shared workspace.

## What it does

- One Slack thread = one `ClaudeSDKClient` session (in-memory, per process)
- Subsequent mentions in the same thread continue the same Claude session,
  preserving context
- Idle sessions are torn down after `SLACKBOT_IDLE_TIMEOUT` seconds
  (default 1800)
- Channel + user allowlists are enforced; non-allowlisted users get a polite
  ":no_entry:" reply

## Setup

### 1. Slack app
Follow the walkthrough in your bring-up notes:
1. Create app at https://api.slack.com/apps (From scratch)
2. Enable Socket Mode, create app-level token with `connections:write`
3. Add bot scopes: `app_mentions:read`, `chat:write`, `channels:history`,
   `groups:history`, `im:history`, `mpim:history`, `users:read`,
   `reactions:write`, `reactions:read`
4. Subscribe to bot event: `app_mention`
5. Install to workspace
6. Create a private channel, invite the bot
7. Grab the channel ID and your user ID

### 2. Credentials

```bash
cp .env.slackbot.example .env.slackbot
# Fill in SLACK_APP_TOKEN, SLACK_BOT_TOKEN, ANTHROPIC_API_KEY,
# SLACK_ALLOWED_CHANNELS, SLACK_ALLOWED_USERS
```

`.env.slackbot` is gitignored.

### 3. Run

```bash
docker-compose --profile slack up -d --build slackbot
docker-compose logs -f slackbot
```

You should see something like:

```
bot identity: user_id=U... team=... allowed_channels={'C...'} allowed_users={'U...'}
```

Then go to your Slack channel and `@DietPlanner Bot hello, can you list files in /app?`

## Stopping

```bash
docker-compose --profile slack stop slackbot
```

## Files

- `bot.py` — Socket Mode listener, allowlist enforcement, session map,
  Claude Code SDK glue
- `management/commands/run_slackbot.py` — Django entrypoint; reads env,
  configures logging, starts the bot

## Operational notes

- **State is in-process.** Restarting the slackbot container drops all
  active thread sessions. The next mention in a thread starts a fresh
  Claude session.
- **The bot writes to your real repo.** It bind-mounts `/opt/llmDietPlanner`
  into `/app`. Diffs land in your working tree; review with `git status`
  / `git diff` before committing.
- **It does not push to git automatically.** The system prompt explicitly
  forbids destructive git ops without confirmation, but this is a soft
  control. A motivated user can talk Claude past it.
- **No DB writes by Claude itself.** Claude can read/write files but does
  not have a Django ORM tool. If you want it to query the DB, prompt it
  to use `python manage.py shell` via Bash.

## Troubleshooting

| Symptom | Cause |
| --- | --- |
| Bot never replies | Check `docker-compose logs slackbot` — usually allowlist denial or missing scope |
| `not_in_channel` error | The bot isn't in the channel. Run `/invite @<bot>` |
| `missing_scope` error | Reinstall the Slack app after adding the scope |
| `invalid_auth` | Wrong `SLACK_BOT_TOKEN` |
| Claude returns empty | Check `ANTHROPIC_API_KEY` validity and your console billing |
| Session never ends | Adjust `SLACKBOT_IDLE_TIMEOUT` or `docker-compose restart slackbot` |
