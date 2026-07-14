---
name: qa-prod
description: Post-deploy production verification. Run after deploying Vařto to prod — dispatches the Fable-5 qa-tester agent to browser-test eatalnicek.eu and returns a GO/NO-GO report.
---

# /qa-prod — post-deploy production verification

Use this after a production deploy to verify eatalnicek.eu (Vařto) still works.
It dispatches the committed `qa-tester` subagent (Fable 5) to drive a real
browser through public + authed flows and write a GO/NO-GO report.

This is on-demand and human-triggered — NOT a CI gate. Fable 5 is the priciest
tier and runs long; that is expected.

## Steps

1. Resolve the base URL: default `https://eatalnicek.eu` unless the user gave one.

2. Resolve QA credentials from the environment:
   - `QA_TEST_USERNAME` and `QA_TEST_PASSWORD`.
   - If BOTH are present, Flow B (authed) is enabled. If either is missing, run
     public-only and tell the user Flow B will be skipped (and why).
   - Read them with: `printf '%s' "${QA_TEST_USERNAME:-}"` and
     `printf '%s' "${QA_TEST_PASSWORD:+SET}"` (never echo the password value).

3. Determine the report path: `docs/qa/<YYYY-MM-DD>-report.md`. Create `docs/qa/`
   if it does not exist (`mkdir -p docs/qa`).

4. Dispatch the `qa-tester` agent (subagent_type: `qa-tester`) with a task prompt
   containing: the base URL, whether Flow B is enabled, the QA username + password
   IF enabled (passed in the prompt, never written to a committed file), and the
   exact report path.

5. When the agent returns, surface its verdict line and the report path inline to
   the user. On NO-GO, also surface the failing rows so the user sees them without
   opening the file.

## Notes

- Never commit the report if it would contain secrets — it should not (the agent
  writes results, not credentials). The `docs/qa/` reports are safe to commit.
- If Playwright MCP is unavailable, tell the user rather than guessing at results.
