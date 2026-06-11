# Security Incident Postmortem — `2026-06-02-dbminer`

**Status:** Remediation in progress (in-repo changes uncommitted; droplet-side
actions NOT yet performed).
**Owner:** Robert Soroka
**Affected host:** Dev droplet `157.230.123.199` (DigitalOcean). Also runs an
unrelated `real-estate-researcher` project.
**Not believed affected:** Production (DO App Platform `eatalnicek.eu`) — see
"Production exposure" below for one credential that still requires rotation.

---

## 1. Summary

On 2026-06-02 a cryptominer process (`dbminer`) was discovered running on the
shared dev droplet. The droplet hosts this project's `docker-compose` stack
(Django + React + Postgres + Redis + Celery + a Slack/Claude bridge that spawns
headless Chrome).

The most probable entry vector is an **internet-exposed datastore with a
trivial credential**: the dev `docker-compose.yml` published Postgres (`5432`)
and Redis (`6379`) to `0.0.0.0` on the droplet, with `POSTGRES_PASSWORD=postgres`
hard-coded and Redis completely unauthenticated. Either is a well-known, widely
auto-exploited miner foothold (unauthenticated Redis in particular allows
writing arbitrary files / achieving RCE).

---

## 2. Timeline

| Time (UTC)        | Event |
|-------------------|-------|
| TODO              | Initial compromise / first miner execution. **Needs droplet logs.** |
| 2026-06-02        | `dbminer` discovered on droplet. |
| 2026-06-02        | In-repo remediation started on branch `fix/reap-slackbot-chrome-zombies` (compose hardening). |
| 2026-06-02        | Second-pass review (this document); additional fixes applied in-repo. |
| TODO              | Miner eradicated on droplet. **Not yet done.** |
| TODO              | Credentials rotated. **Not yet done.** |

Unknowns marked TODO require SSH access to the droplet (auth logs, container
logs, process/cron/systemd inspection, Docker image history). We do not have
that access from this repo.

---

## 3. Suspected root cause

1. **Exposed Postgres on `0.0.0.0:5432` with `POSTGRES_PASSWORD=postgres`.**
   Trivial credential, internet-reachable.
2. **Exposed Redis on `0.0.0.0:6379`, unauthenticated.** Classic miner RCE
   vector (CONFIG SET dir / dbfilename to write a cron job or SSH key).
3. **Contributing factor:** the droplet appears to have had no host firewall
   restricting these ports (unconfirmed — TODO verify `ufw` / DO cloud
   firewall).

Either #1 or #2 alone is sufficient to explain the foothold.

---

## 4. What was remediated (in-repo)

All changes are repo-local and currently **uncommitted** in the working tree for
human review. They do not, by themselves, clean the droplet.

### Original remediation (already present when this review started)
`docker-compose.yml` / `docker-compose.override.yml`:
- Removed the host `ports:` mapping for **db** (Postgres) — now internal-only
  (`db:5432` on the compose network).
- Removed the host `ports:` mapping for **redis** — now internal-only
  (`redis:6379`).
- Bound the Django dev server to **`127.0.0.1:8000`** instead of `0.0.0.0:8000`.
- Replaced hard-coded `POSTGRES_PASSWORD=postgres` with
  `${POSTGRES_PASSWORD:?...}` sourced from the gitignored `.env` (fail-closed if
  unset) — in `db`, `web`, `celery`, and `slackbot`.
- Added `security_opt: [no-new-privileges:true]` to `db`, `redis`, `slackbot`.

### Added by this review
- `docker-compose.yml`: added `no-new-privileges:true` to **web** and
  **celery** (they execute app/scraper/LLM/headless-browser workloads and are
  plausible privesc targets).
- `docker-compose.override.yml`: added `no-new-privileges:true` to **frontend**,
  plus a prominent WARNING comment — the Vite dev server is still published to
  the droplet's public IP on `:5173` (intentional cross-host dev access via
  `157.230.123.199.nip.io:5173`). A dev server is not hardened for the public
  internet; the droplet must gate `:5173` behind a firewall or SSH tunnel.
- `start.sh` (production entrypoint): **removed a hard-coded production admin
  password** (`DJANGO_SUPERUSER_PASSWORD` literal, redacted). It now reads the
  password from a DO App Platform SECRET env var and skips superuser creation if
  the secret is absent (no default fallback).
- `.do/app.yaml`: registered `DJANGO_SUPERUSER_PASSWORD` as a `RUN_TIME` SECRET
  so the prod deploy still bootstraps the admin once the secret is set.

---

## 5. Production exposure found during review (separate from the droplet)

**Hard-coded production Django admin password in `start.sh`.**
- File: `start.sh:36` (pre-fix). The literal (redacted) was the prod superuser
  password for `eatalnicek.eu`, committed to git and present in history.
- Severity: **HIGH.** This is a real leaked credential for the production admin
  account, independent of the dev-droplet miner.
- In-repo fix applied (see §4). **The credential itself MUST still be rotated**
  — removing it from the file does not invalidate the already-leaked value, and
  it remains in git history.

### Repo hygiene checks performed (clean)
- `git ls-files` shows **no tracked `.env`** — only `.env.slackbot.example`
  (properly placeholdered: `xapp-...`, `xoxb-...`, `sk-ant-...`).
- `.gitignore` correctly covers `.env`, `.env.slackbot`, `.env.local`,
  `.env.*.local`. The on-disk `.env` is untracked and ignored (verified).
- `llm_diet_planner_project/settings.py` reads all secrets via
  `config()`/env; no literals. `DEBUG` defaults to `False`; production security
  headers (HSTS, secure cookies, SSL redirect) gated on `not DEBUG`.
- `.do/app.yaml` uses `type: SECRET` for `SECRET_KEY`, `FIELD_ENCRYPTION_KEY`,
  `DATABASE_URL`, Google OAuth, `GEMINI_API_KEY`, `EMAIL_HOST_PASSWORD`.
  `ALLOWED_HOSTS`/`CORS_ALLOWED_ORIGINS` are scoped to the two real prod hosts.

### Lower-severity notes (not blocking)
- The dev `SECRET_KEY`/`FIELD_ENCRYPTION_KEY` literals in the compose files are
  clearly labeled dev/e2e-only (`dev-only-insecure-key-do-not-use-in-production`,
  `e2e-only-not-a-real-secret-key-do-not-ship`). Fine for dev — **must never be
  reused in prod.** Confirm prod uses distinct values (it does via DO SECRETs).
- `create_superuser.py:43` defaults to password `admin123` when invoked with no
  CLI args. It is a manual helper, not wired into any entrypoint, so low risk —
  but do not run it against any internet-reachable instance.

---

## 6. What is NOT yet verified

- Whether the miner achieved persistence (cron, systemd unit, modified
  `~/.ssh/authorized_keys`, malicious Docker image/container, LD_PRELOAD).
- Whether lateral movement reached the co-hosted `real-estate-researcher` stack.
- Whether the Postgres data or `.env` secrets on the droplet were exfiltrated
  (assume yes for credential-rotation purposes).
- Whether `:5173` (and any other port) was firewalled at the host/DO level.
- The actual initial-access timestamp and vector (Postgres vs Redis vs other).

---

## 7. Prioritized action list

### A. In-repo — DONE (pending human commit/review)
- [x] db/redis no longer publish host ports (internal-only).
- [x] Django dev server bound to `127.0.0.1:8000`.
- [x] `POSTGRES_PASSWORD` sourced from gitignored `.env`, fail-closed.
- [x] `no-new-privileges:true` on db, redis, web, celery, frontend, slackbot.
- [x] Removed hard-coded prod superuser password from `start.sh`; now SECRET-based.
- [x] Registered `DJANGO_SUPERUSER_PASSWORD` SECRET in `.do/app.yaml`.
- [x] Added explicit warning that dev `:5173` is publicly bound and needs a firewall.

### B. On the droplet — NEEDS OPERATOR / SSH (not done)
**Eradication**
1. Identify and kill the miner: `ps aux | grep -i dbminer`, inspect
   `/proc/<pid>/exe`, `/proc/<pid>/cwd`; note parent PID and binary path before
   killing. Capture artifacts for analysis first.
2. Hunt persistence: `crontab -l` for every user + `/etc/cron*`,
   `systemctl list-units --type=service` for unknown units, `~/.ssh/authorized_keys`
   for all users, `/etc/ld.so.preload`, suspicious `/tmp`, `/dev/shm`, `/var/tmp`
   binaries, and any rogue Docker containers/images (`docker ps -a`,
   `docker images`).
3. Given an unauthenticated-Redis foothold cannot be cleanly proven clean, the
   safest path is to **rebuild the droplet from a known-good image** and redeploy
   the stack with the hardened compose. Treat the current host as compromised.

**Network**
4. Configure a host/DO cloud firewall: allow only SSH (ideally key-only,
   IP-allowlisted) and any ports you genuinely need; deny `5432`, `6379`,
   `8000`, `5173` from the public internet. Use SSH tunnels for dev access.

**Credential rotation (assume all droplet secrets leaked)**
5. Rotate the **production Django admin password** (the `start.sh` leak) and set
   `DJANGO_SUPERUSER_PASSWORD` as a DO SECRET; also rotate the prod
   `SECRET_KEY` if it ever lived on the droplet.
6. Rotate every secret in the droplet's `.env`: `POSTGRES_PASSWORD`, Redis (add
   a password / `requirepass` going forward), `GEMINI_API_KEY`, Google OAuth
   client secret, Slack `SLACK_APP_TOKEN`/`SLACK_BOT_TOKEN`, `ANTHROPIC_API_KEY`,
   `EMAIL_HOST_PASSWORD`, and `FIELD_ENCRYPTION_KEY` (note: rotating the
   encryption key requires re-encrypting any `EncryptedCharField` data — see
   `shopifyin/models.py`).
7. Because `/root/.claude` is bind-mounted into the slackbot container, treat the
   host's Claude credentials as exposed and re-authenticate.
8. Review the Supabase Postgres (prod DB) access logs for anomalous connections;
   rotate its credentials if the droplet ever held prod `DATABASE_URL`.

**Verification**
9. After rebuild + redeploy, confirm `5432`/`6379` are not externally reachable
   (`nmap` from an outside host), confirm Redis requires auth, and re-run the
   stack with the new `.env`.

---

## 8. Secret Rotation — Reachability Determination

**Method.** For every secret the stack uses, we located *where the value
physically lives* and asked one question: **could the dbminer (which had code
execution on the dev droplet) read it?** A value is reachable if it sits in a
file/env/bind-mount on the droplet, or in container memory, or committed in git.
A value that lives ONLY in DO App Platform prod SECRETs (never copied to the
droplet) is NOT reachable from this compromise.

**Key structural fact (the crux).** `docker-compose.override.yml` loads the
droplet's gitignored `.env` into the **web**, **celery**, and **slackbot**
containers (`env_file: - .env`, override lines 23-24, 54, 60). So *everything in
the droplet `.env` is reachable.* We inspected the dev checkout's `.env` (same
file the droplet uses) **names + value *shapes* only, never the literals**:

- `.env` is unambiguously a **DEV** env: `DEBUG=True`,
  `ALLOWED_HOSTS=...157.230.123.199.nip.io`, `FRONTEND_URL=http://...nip.io:5173`.
- `SECRET_KEY` in `.env` = the **dev literal** (`...do-not-use-in-production`).
  `FIELD_ENCRYPTION_KEY` in `.env` = the **e2e/dev literal**
  (`F4Va…6n8=`, same as the override). → **prod SECRET_KEY / prod
  FIELD_ENCRYPTION_KEY were NEVER on the droplet.**
- `.env` has **no `DATABASE_URL`** and **no** `supabase`/`pooler`/`eatalnicek`/
  `ondigitalocean` string. → **the prod Supabase `DATABASE_URL` was NOT on the
  droplet.** (Dev DB is the in-compose Postgres reached as `db:5432`.)
- `ANTHROPIC_API_KEY` in `.env` is **empty** (slackbot uses the host
  `/root/.claude` subscription, not an API key).
- But `.env` DOES contain live, high-value tokens by shape: `DIGITAL_OCEAN_TOKEN`
  (`dop_v1_…`, 71 ch), `GITHUB_PERSONAL_ACCESS_TOKEN` (`ghp_…`, 40 ch),
  `GEMINI_API_KEY` (`AIza…`, 39 ch), `GOOGLE_CLIENT_SECRET` (`GOCSPX-…`),
  `EMAIL_HOST_PASSWORD` (16 ch Gmail app-password) for the **same**
  `admin@kentain.eu` mailbox prod uses, `SLACK_APP_TOKEN` (`xapp-…`),
  `SLACK_BOT_TOKEN` (`xoxb-…`), and `POSTGRES_PASSWORD`.

**Git-history scan (counts only).** The only *real* secret literals ever
committed are: `POSTGRES_PASSWORD=postgres` (initial commit, `docker-compose.yml`,
already removed) and the `start.sh` prod admin password (§5). The `sk-ant-` /
`xoxb-` / `xapp-` history hits are **only the `.env.slackbot.example`
placeholders and an f-string in `run_slackbot.py`** — no live values. No
`AIza`, `dop_v1`, `ghp_`, `github_pat` literal was ever committed.

### Rotation table

| # | Secret | Where the value lives (evidence) | Reachable from droplet? | Verdict |
|---|--------|----------------------------------|-------------------------|---------|
| 1 | **DIGITAL_OCEAN_TOKEN** | droplet `.env` (`dop_v1_…`); loaded into web/celery/slackbot via `docker-compose.override.yml:23-24,54`. Not in app.yaml, not in git. | **YES** | **MUST ROTATE** |
| 2 | **GITHUB_PERSONAL_ACCESS_TOKEN** | droplet `.env` (`ghp_…`). Loaded into containers. Not in git. | **YES** | **MUST ROTATE** |
| 3 | **Prod Django admin password** (`DJANGO_SUPERUSER_PASSWORD`) | `start.sh:36` pre-fix literal, committed → **in git history forever** (§5). | **YES** (git) | **MUST ROTATE** |
| 4 | **GEMINI_API_KEY** | droplet `.env` (`AIza…`); same single Google key class prod uses (app.yaml:48 SECRET). Loaded into containers. | **YES** | **MUST ROTATE** |
| 5 | **GOOGLE_CLIENT_SECRET** | droplet `.env` (`GOCSPX-…`); `GOOGLE_CLIENT_ID` in `.env` = prod client id (`1058421808506-…`) → **same OAuth app as prod** (app.yaml:42 SECRET). | **YES** | **MUST ROTATE** |
| 6 | **EMAIL_HOST_PASSWORD** | droplet `.env` (16-ch Gmail app pw) for `admin@kentain.eu` — **identical mailbox to prod** (app.yaml:61). | **YES** | **MUST ROTATE** |
| 7 | **SLACK_BOT_TOKEN** (`xoxb-…`) | droplet `.env`; loaded into slackbot. Not in git. | **YES** | **MUST ROTATE** |
| 8 | **SLACK_APP_TOKEN** (`xapp-…`) | droplet `.env`; loaded into slackbot. Not in git. | **YES** | **MUST ROTATE** |
| 9 | **POSTGRES_PASSWORD** (dev DB) | droplet `.env`; also `=postgres` literal in initial-commit history. | **YES** | **MUST ROTATE** (dev DB only) |
| 10 | **Host Claude credentials** (`/root/.claude`) | bind-mounted into slackbot (`override:53`). Token files readable by the container = readable by the miner. | **YES** | **MUST ROTATE** (`claude logout` / re-auth) |
| 11 | **Redis** auth | droplet `redis` had **no password** (unauthenticated) — the likely entry vector. | n/a | **ADD a password** (`requirepass`) — there is nothing to "rotate"; set one. |
| 12 | **ANTHROPIC_API_KEY** | droplet `.env` key is **empty** (verified); only placeholder `sk-ant-…` in `.example`. No live key anywhere. | No live value | **SAFE** (nothing to rotate). If you ever put a real `sk-ant-` in `.env`, rotate it. |
| 13 | **Prod `SECRET_KEY`** | DO App Platform SECRET only (app.yaml:16-18). Droplet `.env`/override hold the **dev literal**, not this. | **NO** | **SAFE** |
| 14 | **Prod `FIELD_ENCRYPTION_KEY`** | DO App Platform SECRET only (app.yaml:25-27). Droplet `.env`/override hold the **dev e2e literal** (`F4Va…6n8=`). | **NO** | **SAFE** — see special case below |
| 15 | **Prod `DATABASE_URL`** (Supabase) | DO App Platform SECRET only (app.yaml:30-32). **Not present in droplet `.env`** (verified: no `DATABASE_URL`/`supabase`/`pooler` string). | **NO** | **CHECK** (one-liner below) |
| 16 | Shopify creds (`storefront_access_token`, `admin_api_key`, `admin_api_secret`, `webhook_secret` in `shopifyin/models.py`) | Stored **in the database**, encrypted with `FIELD_ENCRYPTION_KEY`. Dev DB = the droplet Postgres (reachable); prod DB = Supabase (not reachable). | dev-DB rows: YES; prod-DB rows: NO | **CHECK** — if dev DB held any real Shopify store creds, rotate those in the Shopify admin. If dev DB only had test/empty rows → SAFE. |

### The only CHECK items — RESOLVED 2026-06-02 by Claude Code

**CHECK-15 → RESOLVED: SAFE (no rotation).** Ran the grep against `/opt/llmDietPlanner/.env`:
no `DATABASE_URL` / supabase / pooler / prod host present. The prod Supabase DB URL was
never on the droplet → Supabase DB password does NOT need rotation.

**CHECK-16 → RESOLVED: 0 rows (no rotation), with one caveat.** Correct table is
`shopifyin_shopifystore` (token fields: `storefront_access_token`, `admin_api_key`,
`admin_api_secret`, `webhook_secret`). Queried the **local checkout's `db.sqlite3`** →
**0 ShopifyStore rows**, so no store credentials exist to leak. CAVEAT: this was the local
sqlite DB; the droplet's containers use a separate Postgres I could not reach from the repo.
Strong signal (integration unconfigured), but to be airtight run ONCE on the droplet:
`docker compose exec -T db psql -U postgres -d llm_diet_planner -c "select count(*) from shopifyin_shopifystore;"`
— if that is also 0, CHECK-16 is fully closed.

Original check commands (for reference):

```bash
# CHECK-15  (settles prod DATABASE_URL reachability)
grep -E 'DATABASE_URL|supabase|pooler|@db\.[a-z]|ondigitalocean' /opt/llmDietPlanner/.env
#   → nothing / only @db:5432 dev URL → Supabase creds SAFE.   [observed: NOTHING → SAFE]
#   → supabase/pooler/prod host → ROTATE Supabase DB password now.

# CHECK-16  (real Shopify store creds in the reachable dev DB?)  table = shopifyin_shopifystore
docker compose exec -T db psql -U postgres -d llm_diet_planner -c \
  "select count(*) from shopifyin_shopifystore;"
#   → 0 rows → SAFE.   [observed in local sqlite: 0 → SAFE; confirm on droplet postgres]
#   → >0 rows → rotate those tokens in the Shopify store admin.
```

### Why we did NOT (and should not) query the PRODUCTION database

A reasonable question came up: "can't you just run CHECK-16 against prod to be sure?"
The answer is no, for two distinct reasons — recorded here so the scope is unambiguous:

1. **Prod was never in the blast radius.** The miner ran on the **dev droplet**. CHECK-15
   proved the prod Supabase `DATABASE_URL` was *not present* on that droplet, so the
   production database was unreachable from the compromise. Querying prod tells you what
   prod *contains*, not what *leaked* — it cannot change the rotation list. The only DB the
   attacker could read is the droplet's own Postgres container (`db:5432`), which is exactly
   what the CHECK-16 one-liner targets and the only DB still worth confirming.

2. **No prod credentials are available from the repo, by design.** Prod's `DATABASE_URL` /
   Supabase connection string lives only as a DO App Platform `type: SECRET` and is *not* in
   the local `.env` (confirmed by CHECK-15). There is no path to reach prod from this checkout
   without someone supplying that connection string.

**Rule going forward:** scope every "should I rotate / check X" decision to *what the
attacker could reach* (dev droplet + its `.env` + its Postgres + git history), NOT to the
whole estate. Production lived on a separate platform with separate secrets and stays out of
scope for this incident. A read-only count against the live prod DB would only ever be run
with explicit human authorization and a human-supplied connection string, and even then it
would be for general awareness — not part of this incident's remediation.

### MUST-ROTATE — prioritized execution list

Priority = (can it reach **prod / money / supply-chain**?) × (ease of abuse).

1. **DIGITAL_OCEAN_TOKEN** — *highest blast radius: this token can read/modify
   your prod App Platform, droplets, DNS, billing.*
   DO console → **API** → **Tokens/Keys** → revoke the leaked Personal Access
   Token → **Generate New Token** (scope it minimally) → put the new value in the
   droplet `.env` only if a tool there actually needs it (prefer not to store a
   full-access DO token on a dev box at all).

2. **GITHUB_PERSONAL_ACCESS_TOKEN** — *supply-chain: repo write → can poison the
   `prod` branch that auto-deploys (app.yaml `deploy_on_push: true`).*
   GitHub → **Settings → Developer settings → Personal access tokens** → revoke
   the leaked `ghp_…` token → create a new fine-grained token (least privilege).

3. **Prod Django admin password** (`DJANGO_SUPERUSER_PASSWORD`) — *direct prod
   admin login; leaked in git history.*
   Log into `https://eatalnicek.eu/admin/` (or `python manage.py changepassword`
   via DO console) → set a new strong password → DO App Platform → app →
   **Settings → App-Level Env Vars** → set `DJANGO_SUPERUSER_PASSWORD` as an
   encrypted **SECRET** to the new value.

4. **GEMINI_API_KEY** — *spend/abuse: an exposed `AIza…` key gets scraped and
   burned within hours.*
   Google AI Studio / Cloud console → **API Keys** → delete the leaked key →
   create a new one (restrict it) → update droplet `.env` **and** the DO prod
   SECRET `GEMINI_API_KEY` (app.yaml:48).

5. **GOOGLE_CLIENT_SECRET** — *account takeover via your Google OAuth login flow
   (same client id as prod).*
   Google Cloud console → **APIs & Services → Credentials** → your OAuth client →
   **Reset secret** → update droplet `.env` and the DO prod SECRET
   `GOOGLE_CLIENT_SECRET` (app.yaml:42). (The `client_id` itself is public; no
   rotation needed.)

6. **EMAIL_HOST_PASSWORD** — *same Gmail mailbox `admin@kentain.eu` as prod →
   send mail as you / read if it's a full app password.*
   Google Account → **Security → App passwords** → revoke the leaked app password
   → generate a new one → update droplet `.env` and DO prod SECRET
   `EMAIL_HOST_PASSWORD` (app.yaml:63).

7. **SLACK_BOT_TOKEN + SLACK_APP_TOKEN** — *can post as the bot / open a socket to
   your workspace.* Slack app config (api.slack.com/apps → your app):
   **OAuth & Permissions → Reinstall/rotate** the bot token (`xoxb-…`); **Basic
   Information → App-Level Tokens** → revoke + recreate the `xapp-…` token →
   update droplet `.env.slackbot` / `.env`.

8. **Host Claude credentials** (`/root/.claude`) — on the droplet:
   `claude logout` then `claude login` to mint fresh tokens; the bind-mounted old
   ones are compromised.

9. **POSTGRES_PASSWORD** (dev DB only — no prod impact, but it was trivial and
   exposed) — set a strong value in droplet `.env`; recreate the `db` volume or
   `ALTER USER postgres PASSWORD …`. Also add Redis `requirepass` (#11).

### FIELD_ENCRYPTION_KEY special case — resolved as SAFE

Rotating `FIELD_ENCRYPTION_KEY` is the expensive one because it would require
**re-encrypting every `EncryptedCharField` row** in `shopifyin/models.py`
(`storefront_access_token`, `admin_api_key`, `admin_api_secret`,
`webhook_secret`). **You do NOT need to do this for the prod key.** Evidence: the
value present on the droplet (`.env` and both compose files) is the **dev/e2e
literal** `F4Va…6n8=`, explicitly labeled `do-not-ship`; the **prod
`FIELD_ENCRYPTION_KEY` lives only as a DO App Platform SECRET (app.yaml:25-27)
and was never on the droplet.** So the prod key is **SAFE** and no
re-encryption is required. (Only caveat: the underlying *Shopify tokens* that key
protects — see CHECK-16 — should be rotated **in Shopify** if any real ones lived
in the reachable dev database; that's independent of the encryption key.)

### Bottom line (plain English)

The miner could read the droplet's `.env`, which it was fed straight into the
containers — so treat **everything in that `.env` as leaked**. The genuinely
scary ones are the **DigitalOcean token** and the **GitHub token** (they reach
prod and your repo), followed by the **prod admin password** (in git history) and
the **Gemini / Google-OAuth / Gmail / Slack** credentials (shared with prod or
costly to abuse) — rotate those nine items in the order above. You do **not**
need to touch the **prod `SECRET_KEY`, prod `FIELD_ENCRYPTION_KEY`, or the
Supabase prod `DATABASE_URL`** — none were on the droplet (dev literals / absent),
so no painful encrypted-data migration is needed. Two things still need a
one-line confirm on the droplet: run **CHECK-15** to be 100% sure the prod DB URL
never sat in `.env`, and **CHECK-16** to see if any real Shopify store tokens were
in the dev database (rotate those in Shopify only if present).

---

## 9. Lessons / preventive follow-ups
- Never publish datastore ports to `0.0.0.0` on a multi-tenant droplet; keep
  them on the internal compose network and tunnel for access.
- Never hard-code passwords/keys in committed files (`start.sh`,
  `create_superuser.py`), even "dev" ones that might get copied to prod.
- Add a pre-commit secret scanner (gitleaks / trufflehog) to catch literals like
  the `start.sh` password before they land.
- Default Redis to `requirepass` even in dev.
