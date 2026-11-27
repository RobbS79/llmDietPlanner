# Umami visitor analytics for Uvařto — setup plan

**Status:** DRAFT, 2026-11-27. Nothing deployed. Needs owner decisions in the table below before any step runs.
**Goal:** Start collecting cookieless, aggregate page-view data for eatalnicek.eu today, self-hosted, with the consent banner gating the tracker, so the growth and MCP analytics work has a data source.

## Where we stand (measured 2026-11-27)

- Prod runs on DigitalOcean App Platform, app `squid-app` (id `f1ffa865-7f6d-4aa0-9e74-2b37dac2f0e8`), 2 web instances at 1 GB, plus 5 scheduled jobs. There is no room for Umami inside the app.
- Droplets in fra1: `157.230.123.199` (4 GB, the dev box), `165.227.165.202` (2 GB), `165.232.69.115` (1 GB). Which one, if any, is free is not verified.
- Consent: `frontend/src/lib/analytics.ts:1-6` gates the Meta Pixel on `mkt_consent_v1` and `VITE_FB_PIXEL_ID`. `frontend/src/components/ConsentBanner.tsx` is the banner. Umami can reuse the same consent flag.
- Domain move to uvarto.eu is decided but not registered (see `docs/analytics/2026-07-14-handoff.md` and the memory note on the domain move).
- becomeLocal reference pattern: `docs/ANALYTICS.md` in `/opt/real-estate-researcher`. Umami 3.4.1 plus `postgres:15-alpine` in compose, with Caddy serving the tracker first-party.

## Decisions for the owner

| # | Decision | Recommendation | Why |
|---|---|---|---|
| D1 | Where Umami runs | **New 2 GB droplet, fra1**, Docker compose (Umami + Postgres) + Caddy for TLS | Keeps analytics off the dev box, which has run out of memory and disk before. Matches becomeLocal. Costs a monthly droplet fee. |
| D2 | Hostname | `stats.eatalnicek.eu` now | Works today. The site-id can be kept when the domain moves; see D5. |
| D3 | DNS | Owner adds an A record for `stats.` → the new droplet IP | Claude has no registrar access. |
| D4 | Consent gate | **Load the tracker only after consent = true** (same flag as the Pixel) | Stricter than Umami needs (it is cookieless), and it matches the Meta setup users already see. Trade-off: fewer visits counted. |
| D5 | Domain move | Keep one Umami website record; add the uvarto.eu hostname to it when the domain is live | Avoids splitting history. **Unverified** for Umami 3.4.1, to check before the move. |
| D6 | First-party script path | **Open question.** becomeLocal proxies `/u/script.js` through Caddy. On App Platform the site is not behind a Caddy we control, so the proxy path may not be possible without a route change. | If not possible, load the script from `stats.eatalnicek.eu` directly. That is more exposed to ad blockers. |

## Steps (after decisions D1–D4 are answered)

1. **Droplet:** create a 2 GB fra1 droplet with Docker. Harden SSH (key only, ufw allows 22/80/443). Do not reuse the dev box.
2. **Compose:** `umami` (ghcr.io/umami-software/umami, pinned to 3.4.1) and `postgres:15-alpine` with a named volume. Secrets (`UMAMI_APP_SECRET`, `UMAMI_DB_PASSWORD`, admin password) in a root-owned `.env`, never committed.
3. **Caddy:** TLS for `stats.eatalnicek.eu` only. Dashboard and API on that host. Tracker path per D6.
4. **Umami admin:** create the website record for `eatalnicek.eu`. Keep the website id; it goes into the frontend build.
5. **Frontend:** add a `VITE_UMAMI_WEBSITE_ID` and `VITE_UMAMI_SCRIPT_URL` build var. Load the script in `analytics.ts` only when `getConsent() === true`. Any new `VITE_*` var needs a rebuild, so the App Platform build must receive it (see the note at `docs/analytics/2026-07-14-handoff.md` line ~61).
6. **Tests:** a vitest case that no Umami script is added without consent, and one that it is added after consent. Run the frontend vitest and tsc gates.
7. **Deploy:** through the normal develop → prod flow, with CI green.
8. **Verify:** load eatalnicek.eu with consent granted, confirm a page view appears in the Umami dashboard. Check with and without consent that nothing is sent.
9. **Backups:** nightly `pg_dump` of the Umami database to storage outside the droplet. Not yet decided where.

## Risks

- **Ad blockers** will drop a third-party tracker host. D6 is the main mitigation and is still open.
- **The domain move** may split the stats if D5 does not hold.
- **Droplet cost and upkeep** fall on the owner. No one is on call for it.
- **Consent gate** under-counts visits by design.

## Open questions for the owner

1. D1: approve a new 2 GB droplet, or pick Umami Cloud or the dev box instead?
2. D2: is `stats.eatalnicek.eu` the hostname?
3. D3: can you add the DNS record?
4. D4: gate on consent, yes or no?
5. D6: do you want the first-party path if it needs an App Platform routing change, or the direct host?
