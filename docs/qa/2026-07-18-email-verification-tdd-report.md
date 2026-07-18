# QA Prod Report — 2026-07-18 — Email verification (TDD red/green)

**VERDICT: GO** — signup P0 fixed and verified end-to-end on prod, including real email delivery.

Method: true end-to-end TDD against https://eatalnicek.eu. RED run before deploying PR #37
(prod commit `386997e`), then merge + deploy (`50941bd`, deployment `bad66005`, ACTIVE 09:24:59),
then GREEN run. Real inbox used via Gmail (rob@kentakin.eu + plus-addressing); links taken
from the actual received emails, not constructed.

## RED — pre-fix prod (confirms the P0)

Account: `qa_verify_0718` / `rob+qaverify0718@kentakin.eu` (2nd: `qa_verify_0718b`)

| Step | Result |
|---|---|
| Register | 201, toast "Account created! Check your email to verify, then log in." |
| Verification email | **Delivered to INBOX in ~1s** (from admin@kentakin.eu, Czech copy) — SMTP itself was never the problem |
| Emailed link | `https://eatalnicek.eu//api/auth/verify-email/?...` — double slash AND endpoint absent from prod |
| Click link | Silently lands on marketing landing page; nothing verified |
| Login (correct password) | **401 Invalid credentials** — account `is_active=False` forever → dead account |

## Deploy

- PR #37 squash-merged → develop `50941bd`, pushed develop→prod.
- Build 09:19 → ACTIVE 09:24:59, no health-probe issues (post-#35 ordering held).
- Migration `login_app.0007_grandfather_email_verified` applied OK.

## GREEN — post-fix prod

Account: `qa_verify_0718c` / `rob+qaverify0718c@kentakin.eu`

| # | Check | Result |
|---|---|---|
| 1 | Login immediately after signup | PASS — JWT ok, redirected to /onboarding |
| 2 | Plan generation before verify | PASS — `POST /api/goals/` → **403**, Czech gate copy shown in /create UI |
| 3 | Email link format | PASS — single slash, `.../api/auth/verify-email/?uid=Mjc&token=...` |
| 4 | Click emailed link | PASS — 302 → `/login?verified=1` |
| 5 | Plan generation after verify | PASS — `POST /api/goals/` → **201**, full 3-day plan generated (curated recipes + images) at /plan/123 |
| 6 | Console/network | PASS — only expected errors (RED 401, gate 403); all else 200 |
| 7 | Pre-fix dead account stays locked | PASS — `qa_verify_0718` login → 401 (grandfather migration correctly limited to active users) |

## Follow-ups (non-blocking)

1. **Pre-fix zombie accounts** (`is_active=False`, created before 2026-07-18 09:25): real users who
   signed up earlier are still locked out AND cannot re-register (email-exists check blocks them).
   Decide: activate+mark-unverified, or purge so they can re-register. Check count via prod console:
   `User.objects.filter(is_active=False).count()`.
2. `/login?verified=1` shows no success banner — frontend ignores the param; user gets no
   "e-mail ověřen" confirmation.
3. Untranslated English strings in auth UI: "Account created! Check your email to verify, then
   log in." and "Invalid credentials".
4. QA artifacts left in prod DB: users `qa_verify_0718` (dead), `qa_verify_0718b` (unverified),
   `qa_verify_0718c` (verified, owns plan/goal 123). Safe to delete anytime.
