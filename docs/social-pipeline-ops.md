# Social pipeline — owner setup

Everything the code cannot do for itself. Do these once; the jobs then run
unattended and you only click *Schválit* / *Zamítnout* on a card in Slack.

## 1. Slack
1. api.slack.com/apps → the existing Vařto bot → OAuth & Permissions → Bot Token
   Scopes: `chat:write`, `channels:history` (public channel; `groups:history`
   if private). Reinstall the app to the workspace if you added any.
2. Create channel `#varto-social`, invite the bot (`/invite @<bot>`), copy the
   channel id (channel details → bottom of the About tab, starts with `C`).
3. DO env: `SOCIAL_SLACK_CHANNEL=<C…>` (SLACK_BOT_TOKEN is already set).
4. **Buttons.** Same app → *Interactivity & Shortcuts* → switch Interactivity
   on → Request URL `https://eatalnicek.eu/api/social/slack/interact/` →
   Save. Then *Basic Information* → App Credentials → copy the **Signing
   Secret**. DO env: `SLACK_SIGNING_SECRET=<it>` (secret) and
   `SOCIAL_SLACK_MENTION=<your Slack user id, U…>` so every waiting card
   @mentions you. Until the secret is set, a click shows a Slack warning and
   changes nothing; the endpoint answers 503.

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
the repo. Add the env vars as secrets, then add two jobs next to
`llm-health-canary`:

    - name: social-generate
      kind: SCHEDULED
      run_command: python manage.py generate_social_drafts
      schedule:
        cron: "0 18 * * 0,2,4"
        time_zone: Europe/Prague
      (same github/dockerfile/instance/env block as llm-health-canary)
    - name: social-publish
      kind: SCHEDULED
      run_command: python manage.py publish_social_posts
      schedule:
        cron: "0 9 * * 1,3,5"
        time_zone: Europe/Prague

`social-generate` runs the evening before each publish day (Sun → Monday
deals, Tue → Wednesday recipe, Thu → Friday showcase) and drafts exactly that
one post. A red job = the post could not be drafted; the same reason is posted
in `#varto-social` with you @mentioned, so you never have to open DO to find
out. `draft without caption (…)` or `skipped (…)` is expected occasionally —
it means there was nothing honest to say (no facts, or the honesty gate
rejected every caption attempt), not that the pipeline is broken.

## 5. The weekly rhythm
- Sunday, Tuesday, Thursday around 18:00 one card appears in `#varto-social`:
  header (kind · day · channels), the image, the caption, a status line with
  the deadline, and two buttons. Read it as a stranger would and click
  **✅ Schválit** or **❌ Zamítnout**. The card updates itself: `✅ Schváleno
  · jde ven pondělí 21. 9. 9:00`, later `🚀 Publikováno · <link>`.
- Want different wording? Reply `caption: …` in the card's thread *before*
  clicking Schválit (or before the 09:00 run). It goes through the honesty
  validator; a rejected override is answered in the thread and the original
  text is used.
- Monday/Wednesday/Friday 09:00: the approved post goes to the Page. For the
  deals post, copy the "Pro skupiny" reply from its thread and paste it into
  the groups by hand.
- Missed the 09:00? The card says `⏳ Nestihlo se · schval a půjde ven při
  dalším běhu`. Click Schválit and it goes out at the next run (Mon/Wed/Fri),
  unless it is a deals post whose offers have mostly ended by then — see §8.
  A card left undecided for 7 days is closed as `🚫 Nepublikováno — stale`.
- If a job failed or was skipped and you still want that post, run
  `python manage.py generate_social_drafts --week 2026-Wnn --kind recipe` by
  hand in the DO console; it re-drafts that one card.
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
case, reply `caption: …` in the thread with your own wording and then click
Schválit — your override goes through the same validator, so it still can't
claim a shop or number that isn't in the facts.

## 7. End-to-end test (real Slack, real Page)

```bash
python manage.py social_e2e            # waits 15 min for the click; --timeout / --poll to change
```

Run it in the DO console of the web component. It drafts a genuine recipe post
(facts → caption → honesty gate → card), sends it to the drafts channel with a
🧪 note, and polls the row for your click. **Schválit** publishes it to
Facebook **immediately** through `publish_social_posts --only <id>`, then
reads the post back from the Graph API and prints the permalink (also on the
card). **Zamítnout** or no click in time rejects the draft and nothing is
published. This is also the check that Interactivity (§1.4) is wired: if the
button does nothing, the request URL or signing secret is wrong.

The post is real and stays on the Page — delete it there if you do not want it.
Its row stays `published`, so that recipe is skipped by the Wednesday job for
the usual repost window. Pinterest is not exercised. The row's `iso_week` is an
`E<day><hour><minute>` tag rather than a week, so it cannot collide with a
weekly draft and its UTM campaign is `auto-recipe-E…`.

## 8. Late click — publish a due post by hand

The publish job runs Mon/Wed/Fri 09:00 Prague. A Schválit clicked after the
run sits until the next run, and a deals post whose offers have mostly ended
by then is rejected for good by the expiry gate. To publish it anyway:

1. Make sure the card in `#varto-social` says `✅ Schváleno`. If it still
   shows buttons, click Schválit first. Without that nothing is published.
2. cloud.digitalocean.com → Apps → the app → component **llmdietplanner**
   (web) → **Console** tab.
3. Run:

       python manage.py publish_social_posts --force

   `--force` skips only the stale-draft and expired-offers gates. It still
   requires the approval, still validates any `caption:` override, and only
   touches posts whose scheduled day is today or earlier. Add `--only <id>` to limit
   it to one SocialPost id (admin → Social posts).
4. Expected output: `deals 2026-Wnn: published`, and the card changes to
   `🚀 Publikováno · <link>`. The post is on the Page immediately.
5. If you see `unrecognized arguments: --force`, the deploy carrying the flag
   is not live yet — wait and retry. If it prints `pending`, the card was
   never approved — click Schválit and rerun. A card that says `🚫
   Nepublikováno` or `❌ Zamítnuto` is closed; re-draft it with
   `generate_social_drafts --week … --kind …` if you still want it.

The caption keeps its original dates ("do 21. září"), so readers see it as a
late post. Rewrite it first with a `caption: …` reply in the thread if that
matters; the override goes through the honesty validator like any caption.
