# Social pipeline — owner setup

Everything the code cannot do for itself. Do these once; the jobs then run
unattended and you only react ✅/❌ in Slack.

## 1. Slack
1. api.slack.com/apps → the existing Vařto bot → OAuth & Permissions → Bot Token
   Scopes: add `files:write`, `reactions:read`, `channels:history`
   (`chat:write` is already there); if you make the channel private, also
   `groups:history`. Reinstall the app to the workspace.
2. Create channel `#varto-social`, invite the bot (`/invite @<bot>`), copy the
   channel id (channel details → bottom of the About tab, starts with `C`).
3. DO env: `SOCIAL_SLACK_CHANNEL=<C…>` (SLACK_BOT_TOKEN is already set).

## 2. Facebook Page
1. developers.facebook.com → Create App → type "Business" → add the
   "Facebook Login for Business" product is NOT needed; just the app.
2. Tools → Graph API Explorer: pick the app, User token, permissions
   `pages_show_list`, `pages_manage_posts`, `pages_read_engagement`.
   Generate token, then GET `/me/accounts` → copy the Page `id` and its
   `access_token` (this is a Page token).
3. Make it long-lived: GET
   `/oauth/access_token?grant_type=fb_exchange_token&client_id=<app id>&client_secret=<app secret>&fb_exchange_token=<user token>`
   then repeat `/me/accounts` with the long-lived user token — the Page token
   it returns does not expire.
4. DO env: `FB_PAGE_ID`, `FB_PAGE_ACCESS_TOKEN`. The app can stay in
   Development mode: you admin the Page, so publishing works without review.

## 3. Pinterest
1. developers.pinterest.com → My apps → create app, request **Trial access**
   (a sentence like "post my own recipes to my own board").
2. Once granted: generate an access token with scopes `boards:read`,
   `pins:write` (the app page has a "Generate token" button in trial mode).
3. GET `https://api.pinterest.com/v5/boards` with the token → copy the board
   id for "Recepty" (create the board in Pinterest first).
4. DO env: `PINTEREST_ACCESS_TOKEN`, `PINTEREST_BOARD_ID`.
   Until these exist the recipe post still publishes to Facebook and reports
   `pinterest: … not configured` in its thread.

## 4. DigitalOcean jobs
Use doctl ≥ 1.163 (`doctl apps spec get f1ffa865-7f6d-4aa0-9e74-2b37dac2f0e8 > spec.yaml`,
edit, `doctl apps update … --spec spec.yaml`). Never push `.do/app.yaml` from
the repo. Add the five env vars as secrets, then add two jobs next to
`llm-health-canary`:

    - name: social-generate
      kind: SCHEDULED
      run_command: python manage.py generate_social_drafts
      schedule:
        cron: "0 18 * * 0"
        time_zone: Europe/Prague
      (same github/dockerfile/instance/env block as llm-health-canary)
    - name: social-publish
      kind: SCHEDULED
      run_command: python manage.py publish_social_posts
      schedule:
        cron: "0 9 * * 1,3,5"
        time_zone: Europe/Prague

A red job = something failed; the reason is in the Slack thread of the post.
A red `social-generate` job with a line like `draft without caption (…)`, or
a kind reported as `skipped (…)`, is expected occasionally — it means a post
could not be drafted honestly this week (no facts, or the honesty gate
rejected every caption attempt), not that the pipeline is broken. Only treat
it as an outage if the reason in the thread doesn't explain itself.

## 5. Week one
- Sunday evening: three drafts appear in `#varto-social`. Read them as a
  stranger would. ✅ the good ones. Reply `caption: …` to fix wording.
- If the Sunday job fails or is skipped, run
  `python manage.py generate_social_drafts --week 2026-Wnn` by hand for the
  intended week — a run that slips past Monday would otherwise target the
  following week instead of the one you meant to fix.
- Monday 09:00: the deals post goes to the Page. Copy the "Pro skupiny" reply
  from its thread and paste it into the groups by hand.
- Check attribution after two weeks: signups with utm_source facebook /
  pinterest and utm_campaign `auto-<kind>-<week>` in the analytics
  MarketingAttribution table.

## 6. How the honesty gate works
Every caption is checked against the same facts the card was built from
before either reaches Slack: shop names, recipe names, and any number in the
caption must all trace back to the database facts, or the caption is
rejected. A red caption (or a post that lands in Slack "without caption")
does not mean the model wrote something false — it means the model could not
produce a caption the validator would accept, so none was posted. In that
case, reply `caption: …` in the thread with your own wording — your override
goes through the same validator, so it still can't claim a shop or number
that isn't in the facts.
