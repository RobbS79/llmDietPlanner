# Refine Chat: Previous Suggestions Stay Clickable — Design

**Date:** 2026-07-18
**Status:** Approved (user), pending spec review
**Builds on:** `2026-07-18-recipe-refine-chat-design.md` (shipped, LIVE in prod)

## Problem

In the refine chat, each new suggestion replaces the previous one. A user who
asks "a co to bylo předtím?" cannot get an earlier suggestion back: its id is
in the rejection list (so the picker will never re-offer it) and the UI keeps
no way to select it. Real-user transcript (2026-07-18) hit exactly this.

## Decision (user-selected: "click to re-expand")

Past suggestions collapse to their existing assistant text line, made
clickable; clicking one re-expands it as the active full card. One full card
at a time — the panel stays tidy; going back costs one extra click.

## Interaction model

- Every assistant reply keeps its suggestion (candidate) attached locally.
- At most one candidate is **active** at any moment (none after a
  no-alternatives turn or an error rollback) and renders as the
  existing full card (image, why-line, chips, "Použít tento recept") in the
  card slot below the transcript.
- Every other past suggestion renders as its assistant transcript line
  ("Co třeba: Kulajda? …") made clickable: chevron affordance + hover style,
  `aria-label="Zobrazit tento návrh"` (EN gloss: "Show this suggestion").
- Clicking a line makes that candidate active; the displaced candidate's line
  becomes clickable again (symmetric swap). Lines are disabled while a
  request is pending, like every other control in the panel.
- Accept works exactly as today: `refineAccept(mealId, id)`; the server
  re-validates slot/dietary/catalog eligibility, so a stale suggestion can
  never bypass the gates.

## Unchanged semantics (explicit)

- Typing a new message implicitly rejects only the **currently active**
  candidate (exactly today's behavior). Re-activating an old suggestion does
  NOT remove it from `rejected_ids` — the automatic picker never re-offers
  it; only a manual click can bring it back.
- Re-activating costs nothing from the 8-user-message budget and still works
  after the cap is reached and in the no-alternatives state.
- Close ("Zavřít") and accept still discard the whole conversation.
- The preview API request shape is untouched: messages sent to the backend
  remain `{role, text}` only.

## Implementation shape (pure frontend)

`frontend/src/components/recipe/RecipeRefineChat.tsx` only:

- Local message type gains an optional `candidate?: RefineCandidate` on
  assistant entries (a new local interface extending the API `ChatMessage`;
  the API type itself is unchanged).
- Before each `refinePreview` call, messages are mapped down to
  `{role, text}` — a test pins that card data never leaves the client.
- The `candidate` state remains "the active candidate"; a successful preview
  turn stores the new candidate on its assistant message AND sets it active.
- Assistant rows with a non-active candidate render as `<button>` lines
  (keyboard-focusable); rows without a candidate (none survived an error
  rollback) render as plain text like today.
- Error rollback already restores `messages`/`candidate` consistently; the
  candidate embedded in a rolled-back assistant message disappears with it.

No backend, API-client, or `RecipePage` changes. No new dependencies.

## Czech copy (EN gloss for review)

| Czech | English gloss |
|---|---|
| `Zobrazit tento návrh` | "Show this suggestion" (aria-label on past-suggestion line) |

No other new user-visible strings; the clickable line reuses the existing
assistant text.

## Testing

Component tests (`RecipeRefineChat.test.tsx`, extend existing suite):

1. After two turns, the first suggestion's line is a button; clicking it
   shows its full card (name, accept button) and the second suggestion's
   line becomes a button.
2. Accepting a re-expanded old suggestion calls `refineAccept` with the old
   candidate's id and bubbles the recipe up.
3. Typing after re-expanding rejects the re-expanded candidate (its id is
   appended to `rejected_ids` on the next preview call).
4. Past-suggestion lines remain clickable after the 8-message cap.
5. The `refinePreview` payload contains only `{role, text}` entries — no
   candidate fields.

## Out of scope

- The LLM answering meta-questions ("a co to bylo předtím?") in text — the
  visible clickable history makes this unnecessary.
- Persisting chat history across close/reopen.
- Backend awareness of which candidate is active.
