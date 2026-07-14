# QA Tester (post-deploy prod verification) — Design

**Date:** 2026-07-14
**Status:** Design (awaiting review)
**Author:** Robert Soroka (with Claude - Thanks!)

## Problem

We deploy Vařto (eatalnicek.eu) to production by pushing to the `prod` branch;
DigitalOcean App Platform rolls the single Docker service. After each deploy we
have no fast, holistic "did this break anything a user would notice?" check. The
existing `e2e/` Playwright suite asserts a fixed set of invariants, but it can't
judge the open-ended "this looks/behaves wrong" class of regressions, and it is
not routinely run against prod after a deploy.

This is acute now: we are about to run a paid FB/IG ad campaign, so a broken
landing page, consent banner, onboarding, or checkout on prod costs real money.

## Goal

An **on-demand, post-deploy** verification agent that drives a real browser
through the key production flows, reasons about whether each is correct, and
writes a pass/fail report with a single top-line **GO / NO-GO** verdict. It
**complements** — does not replace — the deterministic `e2e/` suite.

Non-goals: not a CI gate, not per-commit, not a load test, not a replacement for
the e2e assertions. It runs when the human asks, after a deploy.

## Model

Runs on **Claude Fable 5** (`model: fable`), Anthropic's most capable model for
long-horizon agentic work — the right fit for browser navigation + correctness
judgment + self-verification.

Two consequences baked into the design:
- **Cost:** Fable 5 is the priciest tier (~2× Opus). Acceptable for a once-per-
  deploy, human-triggered run; explicitly why this is **not** a loop or CI gate.
- **Latency:** thinking is always on and hard agentic turns can run many minutes.
  The skill and agent must expect long runs and not bail early.

## Form factor

Two committed, version-controlled files:

### 1. `.claude/agents/qa-tester.md`
The subagent definition.
- Frontmatter: `model: fable`; tools = Playwright MCP `browser_*` + `Read` +
  `Bash` (for `curl` health checks) + `Write` (the report).
- Body: the fixed, versioned **per-flow checklist** of "what good looks like"
  (below), the hard safety prohibitions, and the report format. Working a fixed
  checklist (plus freedom to flag extra anomalies) keeps verdicts semi-
  repeatable and auditable rather than pure vibes.

### 2. `.claude/skills/qa-prod/SKILL.md`
The `/qa-prod` launcher skill.
- Resolves the prod base URL (default `https://eatalnicek.eu`) and reads QA creds
  from env (`QA_TEST_USERNAME` / `QA_TEST_PASSWORD`; `QA_TEST_EMAIL` optional).
  Login authenticates on username (`login_app.views.LoginView`), so username is
  the key credential.
- Dispatches the qa-tester agent with a scoped task string (base URL, whether
  authed flow is enabled, report path).
- On completion, echoes the **GO / NO-GO verdict + report path** inline so a
  green run needs no file-opening.

## Scope of what gets tested

### Flow A — Public surface (no auth, always runs)
Pages: landing `/`, `/recepty`, one recipe detail, `/pricing`, legal page(s).
Per page, the agent verifies:
- HTTP 200 / page renders (no error/blank state).
- No console errors (dump any that appear).
- Key expected content present (headline, recipe cards, price tiers, etc.).
- Consent banner appears; **both** Přijmout and Odmítnout work.
- Primary CTAs route to the correct destination.
- Mobile viewport: hamburger header opens/navigates.

### Flow B — Authed (seeded QA account; runs only if creds present)
- Log in as the seeded QA account.
- Walk onboarding → **generate a fresh plan** → view the plan; confirm it
  renders coherently.
- Click checkout; confirm it **reaches** Stripe Checkout (pk_live), then **STOP**
  — never enter payment details, never complete a purchase.

If `QA_TEST_USERNAME`/`QA_TEST_PASSWORD` are unset, Flow B is **skipped** and the
run is public-only (report marks Flow B as SKIP with the reason).

## QA account provisioning

New idempotent management command **`seed_qa_account`**:
- Creates (or leaves intact) a known QA user from `QA_TEST_USERNAME` /
  `QA_TEST_PASSWORD` (`QA_TEST_EMAIL` optional).
- Optionally seeds a **pre-generated plan** on that account as a fallback so the
  "view plan" check still passes if live generation is slow/flaky.
- Idempotent: safe to run on every deploy.
- Gated on the env vars — **no-ops if they are unset**.

Wired into `start.sh` at deploy, same pattern as the existing superuser
bootstrap. Credentials are **DO secrets, never committed** — consistent with the
project's secret-handling rules (see the dbminer incident). They reach the agent
only via env at invocation, never written into the committed agent/skill files.

## Decisions (resolved)

- **Generate a fresh plan each run** (not view-only): verifying prod includes the
  LLM generation pipeline. Pre-seeded plan is the fallback, not the primary path.
- **`seed_qa_account` + DO-secret creds** (not committed creds, not a
  hand-created account): only approach that keeps the QA password out of git.

## Safety rails (prod is pk_live)

Stated as hard prohibitions in the agent def; the agent must not cross them:
- Never submit payment or complete a Stripe checkout.
- Never delete or mutate real data.
- Only ever use the seeded QA account.
- Read-only except the single per-run plan generation.

## Report

`docs/qa/<YYYY-MM-DD>-report.md`:
- Top line: **GO / NO-GO**.
- Per-flow table: PASS / FAIL / SKIP, with severity on failures.
- Console-error dump.
- Screenshots-on-failure saved to the local `.playwright-mcp/` run dir
  (gitignored, not committed — authed-run captures may hold session data); the
  report references those local paths.

The skill surfaces the verdict + path inline.

## Components & boundaries

| Unit | Purpose | Depends on |
|---|---|---|
| `seed_qa_account` mgmt command | Idempotently provision the QA user (+ fallback plan) | Django user model, plan model, env creds |
| `start.sh` hook | Run `seed_qa_account` at deploy | the command, DO env |
| `.claude/agents/qa-tester.md` | Drive browser, judge flows, write report | Playwright MCP, prod URL, env creds |
| `.claude/skills/qa-prod/SKILL.md` | Launch agent, surface verdict | the agent, env |

Each is independently understandable and swappable: the command doesn't know
about the agent; the agent doesn't know how the account was seeded (only that it
can log in); the skill only orchestrates.

## Testing the tester

- `seed_qa_account` gets a Django TestCase: idempotency, no-op-when-unset,
  creates-user-and-plan-when-set.
- The agent + skill are validated by a live public-only dry run against prod
  (Flow B skipped) before wiring creds.

## Out of scope / follow-ups

- Any change to the paid checkout path itself.
- Scheduling/automation (this stays human-triggered).
- Reusing the report format for the existing `e2e/` suite.
