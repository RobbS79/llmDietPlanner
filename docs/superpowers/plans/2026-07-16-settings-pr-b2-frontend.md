# Settings PR B — Phase 2 (Frontend) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Build the `/nastaveni` Settings page (five sections) + a Navbar account dropdown, consuming the Phase-1 backend.

**Architecture:** New `src/pages/Settings.tsx` (light "Market Paper" theme via `MainLayout`), a typed API layer `src/lib/settings.ts`, and an account dropdown in `Navbar.tsx`. Each section is an independent sub-component with its own save/loading/error state (no giant form). Preferences reuse the already-shipped `src/lib/preferences.ts`. Subscription reuses `billing.ts`; consent reuses `analytics.ts`.

**Tech Stack:** React 18 + TS, react-router v6, @tanstack/react-query, axios (`@/lib/api`), Tailwind (Market Paper tokens), Vitest. No component library — controls are hand-styled inline (matching existing pages). Toasts via the custom `useToast()` (`@/components/ui/Toast`).

**Branch:** `feat/settings-page` (already checked out, Phase-1 backend committed). One deploy after this phase.

---

## Scope decision — Google-user account deletion (READ FIRST)

The backend supports deleting a Google-provider account via a fresh `google_access_token`, but the app's Google login is a **redirect-based allauth flow** — no Google Identity Services token client is loaded, so acquiring that token in a modal needs new GIS integration (disproportionate for the pilot's small Google segment). **This phase ships:**
- **Email users:** full self-serve delete (re-enter password).
- **Google users:** the delete card shows a GDPR-compliant "request deletion" message (mailto to support) instead of an in-app delete. The backend Google path stays built + unit-tested, ready to wire to GIS in a follow-up.

This is a deliberate, flagged deviation from the spec's "Google users complete fresh OAuth re-auth." If the reviewer/owner wants full Google self-delete now, that's a separate GIS-integration task.

---

## Conventions (verified against the codebase)

- **Theme:** authed pages use light Market Paper. Wrap the page in `<MainLayout>`. Build cards as `bg-card border border-line rounded-3xl` (or `<Card variant="paper">`) — NEVER Card's dark default. Tokens: `paper`, `card`, `kraft`, `line`, `ink`, `muted`, `green`(+`.mid`,`.soft`), `paprika`(+`.strong`,`.soft`).
- **Profile query:** `useQuery({ queryKey: ['profile'], queryFn: () => api.get('/auth/profile/').then(r => r.data.data) })`. Envelope is `.data.data`. Fields now include `email, username, free_generations_remaining, total_generations, onboarding_completed, dietary_preferences, primary_auth_provider, email_verified, marketing_consent, consent_version` (Phase-1 B4).
- **Mutations:** `useMutation`, on success `queryClient.invalidateQueries({ queryKey: ['profile'] })` + `toast.success(...)`; on error set inline error from `err.response?.data?.error`.
- **Errors:** per-section inline `role="alert"` box (ForgotPassword pattern) OR toast. Use inline for save errors so the failing section is obvious.
- **Toast:** `const toast = useToast();` from `@/components/ui/Toast` (provider already mounted in App.tsx).
- **Czech copy:** finalized below with EN gloss. User cannot author Czech — do not invent new strings; use these.
- **Verify build:** `npx tsc --noEmit` + `npx vitest run` locally (box OOMs on `vite build`; full build runs on deploy). Grep built CSS is deferred to deploy QA.

---

## File Structure

- **Create** `src/lib/settings.ts` — typed API wrappers + `downloadBlob` helper (Task 1).
- **Create** `src/lib/settings.test.ts` — unit tests for the lib (Task 1).
- **Modify** `src/components/layout/Navbar.tsx` — account dropdown (Task 2).
- **Create** `src/pages/Settings.tsx` — page shell + 5 sections (Tasks 3–8). If it grows past ~400 lines, split each section into `src/components/settings/<Section>.tsx`.
- **Modify** `src/App.tsx` — add `/nastaveni` route (Task 3).

---

## Czech copy (final, with EN gloss)

- Page title: **Nastavení** (Settings). Subtitle: **Spravujte svůj účet a předvolby** (Manage your account and preferences).
- Section headers: **Předvolby** (Preferences) · **Účet** (Account) · **Předplatné** (Subscription) · **Soukromí** (Privacy) · **Moje data** (My data).
- Preferences: save btn **Uložit předvolby** (Save preferences); success toast **Předvolby uloženy** (Preferences saved); labels reuse `preferences.ts` option `.label`s. Household label **Počet osob**; budget **Týdenní rozpočet**; days **Počet dní jídelníčku** (default plan length). Country/lang: **Země** (CZ/SK).
- Account: **Přihlašovací metoda** (Login method) → **E-mail** / **Google**. Verified: **Ověřeno** (Verified) / **Neověřeno** (Unverified). Change-password (email only): heading **Změnit heslo**, fields **Současné heslo** (current), **Nové heslo** (new), **Nové heslo znovu** (repeat), btn **Uložit nové heslo**, success **Heslo změněno**. Errors map from server.
- Delete (email user): btn **Smazat účet** (danger). Modal title **Opravdu smazat účet?** Body **Tato akce je nevratná. Trvale smažeme váš profil, jídelníčky a všechna data. Pokud máte aktivní předplatné, bude okamžitě zrušeno — zbývající období propadá bez vrácení peněz.** Field label **Pro potvrzení zadejte heslo** (enter password to confirm). Buttons **Zrušit** (Cancel) / **Trvale smazat** (Permanently delete). Post-delete: clear tokens, redirect `/`.
- Delete (Google user): body **Účet vytvořený přes Google smažeme na vaši žádost. Napište nám na** + `mailto:` support link. (We delete Google-created accounts on request — email us.)
- Subscription: **Aktuální tarif** (Current plan) → **Zdarma** (Free) / **Standard** / **Premium**. Usage line: **Zbývá {n} generování zdarma** (n free generations left) when Free; **Využito {used} z {quota} tento měsíc** when subscribed. Btn (subscribed) **Spravovat předplatné** (Manage subscription) → portal. Free CTA **Zobrazit tarify** (See plans) → `/pricing`.
- Privacy: heading **Marketingové cookies**, help **Používáme Meta Pixel k měření účinnosti reklam. Změna se plně projeví po znovunačtení stránky.** Toggle states **Povoleno** (On) / **Zakázáno** (Off).
- Data: btn **Stáhnout moje data** (Download my data), help **Stáhněte si kopii svých dat ve formátu JSON.** Loading label **Připravuji…** (Preparing…).
- Navbar dropdown: **Nastavení** (Settings), **Odhlásit se** (Log out).

---

## Task 1: Settings API layer + download helper (TDD)

**Files:** Create `src/lib/settings.ts`, `src/lib/settings.test.ts`.

- [ ] **Step 1: Write the failing test** — `src/lib/settings.test.ts`:

```ts
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { savePreferences, deleteAccountWithPassword, triggerDataExport } from './settings';
import { api } from './api';

vi.mock('./api', () => ({ api: { patch: vi.fn(), delete: vi.fn(), get: vi.fn() } }));

describe('savePreferences', () => {
  beforeEach(() => vi.clearAllMocks());
  it('PATCHes only the dietary_preferences payload', async () => {
    (api.patch as any).mockResolvedValue({ data: { status: 'success' } });
    await savePreferences({ goal: 'eat_healthy', num_days: 5 } as any);
    expect(api.patch).toHaveBeenCalledWith('/auth/profile/', { dietary_preferences: { goal: 'eat_healthy', num_days: 5 } });
  });
});

describe('deleteAccountWithPassword', () => {
  beforeEach(() => vi.clearAllMocks());
  it('DELETEs /auth/account/ with the password in the body', async () => {
    (api.delete as any).mockResolvedValue({ data: { status: 'success' } });
    await deleteAccountWithPassword('hunter2');
    expect(api.delete).toHaveBeenCalledWith('/auth/account/', { data: { password: 'hunter2' } });
  });
});

describe('triggerDataExport', () => {
  beforeEach(() => vi.clearAllMocks());
  it('requests the export as a blob', async () => {
    const blob = new Blob(['{}'], { type: 'application/json' });
    (api.get as any).mockResolvedValue({ data: blob });
    // downloadBlob touches DOM URL APIs — stub them
    (globalThis.URL as any).createObjectURL = vi.fn(() => 'blob:x');
    (globalThis.URL as any).revokeObjectURL = vi.fn();
    await triggerDataExport();
    expect(api.get).toHaveBeenCalledWith('/auth/export/', { responseType: 'blob' });
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd frontend && npx vitest run src/lib/settings.test.ts`
Expected: FAIL (module missing).

- [ ] **Step 3: Implement** — `src/lib/settings.ts`:

```ts
import { api } from '@/lib/api';
import type { Preferences } from '@/lib/preferences';

/** Persist edited preferences. Backend merges keys (Phase-1 B3), so send only what changed. */
export async function savePreferences(prefs: Partial<Preferences> & Record<string, unknown>): Promise<void> {
  await api.patch('/auth/profile/', { dietary_preferences: prefs });
}

/** Change password for email users (dj_rest_auth). */
export async function changePassword(oldPw: string, newPw: string): Promise<void> {
  await api.post('/auth/password/change/', {
    old_password: oldPw, new_password1: newPw, new_password2: newPw,
  });
}

/** Hard-delete the account (email users). Password goes in the DELETE body. */
export async function deleteAccountWithPassword(password: string): Promise<void> {
  await api.delete('/auth/account/', { data: { password } });
}

/** Download the user's data export as a JSON file (authenticated blob). */
export async function triggerDataExport(): Promise<void> {
  const res = await api.get('/auth/export/', { responseType: 'blob' });
  downloadBlob(res.data as Blob, 'moje-data.json');
}

export function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}
```

- [ ] **Step 4: Run to verify it passes** — `npx vitest run src/lib/settings.test.ts` → PASS.

- [ ] **Step 5: Commit**
```bash
git add frontend/src/lib/settings.ts frontend/src/lib/settings.test.ts
git commit -m "feat(settings): API layer (save prefs, change pw, delete, export) + blob download"
```

---

## Task 2: Navbar account dropdown

**Files:** Modify `src/components/layout/Navbar.tsx`.

- [ ] **Step 1: Implement.** Add a `useQuery(['profile'])` (hits cache), an `accountOpen` boolean, and a dropdown button (user email) on desktop that contains a **Nastavení** link (`/nastaveni`) and the existing **Odhlásit se** action. Move the bare logout icon into the dropdown. In the mobile menu, add a **Nastavení** link above the existing logout row. Follow the exact toggle + absolute-panel pattern already used for `mobileOpen` (no click-outside lib exists; close the panel on item click). Keep all Market Paper classes. Concrete additions:

```tsx
// add imports
import { Link, useNavigate, useLocation } from 'react-router-dom';
import { LayoutDashboard, Sparkles, Crown, LogOut, Menu, X, Settings as SettingsIcon, ChevronDown } from 'lucide-react';
import { useQuery } from '@tanstack/react-query';
import { api } from '@/lib/api';
// inside component:
const { data: profile } = useQuery({ queryKey: ['profile'], queryFn: () => api.get('/auth/profile/').then(r => r.data.data) });
const [accountOpen, setAccountOpen] = useState(false);
```

Desktop: replace the bare logout `<button>` with a dropdown trigger showing `profile?.email` + `<ChevronDown>`, toggling `accountOpen`; the panel (absolute, `bg-card border border-line rounded-xl shadow-2xl`) contains:
```tsx
<Link to="/nastaveni" onClick={() => setAccountOpen(false)} className="...">
  <SettingsIcon size={14} /> Nastavení
</Link>
<button onClick={handleLogout} className="...text-paprika-strong...">
  <LogOut size={14} /> Odhlásit se
</button>
```
Mobile menu: add `<Link to="/nastaveni" ...><SettingsIcon/> Nastavení</Link>` above the logout button; close `mobileOpen` on click.

- [ ] **Step 2: Verify** — `npx tsc --noEmit && npx vitest run && npm run lint` (lint: no NEW problems; repo already has pre-existing `no-explicit-any` errors — confirm count unchanged via a stash-compare if unsure).

- [ ] **Step 3: Commit**
```bash
git add frontend/src/components/layout/Navbar.tsx
git commit -m "feat(nav): account dropdown with Nastavení link + email"
```

---

## Task 3: Route + Settings page shell

**Files:** Modify `src/App.tsx`; create `src/pages/Settings.tsx`.

- [ ] **Step 1: Add the route.** In `src/App.tsx`, import `import { Settings } from '@/pages/Settings';` and add inside `<Routes>` (next to `/create`):
```tsx
<Route path="/nastaveni" element={<ProtectedRoute><Settings /></ProtectedRoute>} />
```

- [ ] **Step 2: Create the shell** — `src/pages/Settings.tsx`. Wrap in `<MainLayout>`, load `['profile']` + `['billing-me']` (via `fetchBillingMe`), render a centered column (`max-w-2xl mx-auto px-6 py-12 space-y-8`) with a page header (**Nastavení** / subtitle) and five section `<Card variant="paper" className="p-8">` placeholders, each with its Czech header. Use `LoadingScreen` while `['profile']` is loading. Each section will be filled in Tasks 4–8. Scaffold:

```tsx
import { useQuery } from '@tanstack/react-query';
import { api } from '@/lib/api';
import { MainLayout } from '@/components/layout/MainLayout';
import { Card } from '@/components/ui/Card';
import { LoadingScreen } from '@/components/ui/LoadingScreen';
import { fetchBillingMe } from '@/lib/billing';

export const Settings = () => {
  const { data: profile, isLoading } = useQuery({ queryKey: ['profile'], queryFn: () => api.get('/auth/profile/').then(r => r.data.data) });
  const { data: billing } = useQuery({ queryKey: ['billing-me'], queryFn: fetchBillingMe });
  if (isLoading || !profile) return <LoadingScreen message="Načítání…" />;
  return (
    <MainLayout>
      <div className="max-w-2xl mx-auto px-6 py-12 w-full space-y-8">
        <header>
          <h1 className="font-display text-3xl font-black text-ink tracking-tighter uppercase italic">Nastavení<span className="text-paprika not-italic">.</span></h1>
          <p className="text-muted text-sm font-bold mt-2">Spravujte svůj účet a předvolby</p>
        </header>
        {/* Task 4 */} <PreferencesSection profile={profile} />
        {/* Task 5 */} <AccountSection profile={profile} />
        {/* Task 6 */} <SubscriptionSection billing={billing} />
        {/* Task 7 */} <PrivacySection profile={profile} />
        {/* Task 8 */} <DataSection />
      </div>
    </MainLayout>
  );
};
```
Create empty stub components for the five sections in the same file so it compiles (each returns a titled `<Card>`), to be filled next.

- [ ] **Step 3: Verify** `npx tsc --noEmit` clean; route renders (defer visual to deploy QA).

- [ ] **Step 4: Commit**
```bash
git add frontend/src/App.tsx frontend/src/pages/Settings.tsx
git commit -m "feat(settings): /nastaveni route + page shell with 5 section stubs"
```

---

## Task 4: Preferences section

Reuse `preferences.ts` (`GOALS, DIETARY_STYLES, ALLERGIES, COOKING_SKILLS, COOKING_TIMES, toggleMultiValue, Preferences`) and the Onboarding JSX patterns (single-select card grid, multi-select pills, household buttons, budget range). Local state seeded from `profile.dietary_preferences` (fall back to `DEFAULT_PREFERENCES` fields). Add a **Počet dní jídelníčku** control (numeric 1–30, default 7 — this is the `num_days` default that ties to backlog Ticket 2; store under key `num_days`). Save button `savePreferences(state)` → on success `invalidateQueries(['profile'])` + `toast.success('Předvolby uloženy')`; on error inline box. Use `savePreferences` from Task 1.

- [ ] Step 1: Implement `PreferencesSection` following `Onboarding.tsx:161-172` (single-select) and `:180-189` (multi-select) patterns verbatim in style; save via `useMutation`.
- [ ] Step 2: `npx tsc --noEmit && npx vitest run` clean.
- [ ] Step 3: Commit `feat(settings): editable preferences section`.

**Acceptance:** editing goal/styles/allergies/household/budget/skill/time/country/num_days and saving persists (PATCH merges — `shop` and other keys survive); reload shows saved values.

---

## Task 5: Account section (login method, verified badge, change password, delete)

- Show **Přihlašovací metoda** from `profile.primary_auth_provider`; verified badge from `profile.email_verified` (passive — NO resend action, SMTP is a known blocker).
- **Change password** form shown ONLY when `primary_auth_provider === 'email'`: three fields → `changePassword(old,new)` (Task 1). Client check new1===new2 and length ≥ 8; map server errors (`err.response?.data`) to inline text; success toast **Heslo změněno**.
- **Delete account:**
  - Email user: **Smazat účet** button opens a confirm modal (hand-rolled — no Modal component; a fixed overlay `fixed inset-0 bg-ink/40 flex items-center justify-center z-[200]` + a `bg-card rounded-3xl p-8 max-w-md` panel). Modal has the danger copy, a password field, **Zrušit** / **Trvale smazat**. On confirm → `deleteAccountWithPassword(pw)`; on success clear tokens (`clearAuthTokens()` from `@/lib/auth`) + `window.location.href = '/'`; on error inline in the modal (wrong password → 403 message).
  - Google user: render the "request deletion" mailto message instead of the button (see Scope decision + Czech copy).

- [ ] Step 1: Implement `AccountSection` + the modal.
- [ ] Step 2: `npx tsc --noEmit && npx vitest run` clean.
- [ ] Step 3: Commit `feat(settings): account section — login method, change password, delete`.

**Acceptance:** email user can change password; delete modal requires the password, deletes, logs out; wrong password shows an error and does not delete; Google user sees the request-deletion message, no delete button.

---

## Task 6: Subscription section

Consume `billing` prop (`fetchBillingMe` result: `{ subscription, free_generations_remaining }`). If `subscription` (entitled): show tier (**Standard**/**Premium**), **Využito {plans_used_this_period} z {remaining_quota+used}**… (show `plans_used_this_period` and, if available, quota), and a **Spravovat předplatné** button → `openBillingPortal()` (reuse the `portalLoading` guard pattern from `BillingSuccess.tsx`). If no subscription: show **Zdarma**, **Zbývá {free_generations_remaining} generování zdarma**, and a **Zobrazit tarify** link → `/pricing`.

- [ ] Step 1: Implement `SubscriptionSection` (mirror `BillingSuccess.tsx:handlePortal`).
- [ ] Step 2: `npx tsc --noEmit` clean.
- [ ] Step 3: Commit `feat(settings): subscription section with Stripe portal link`.

**Acceptance:** Free user sees Free + remaining generations + See-plans link; subscribed user sees tier + a working Manage-subscription button (opens Stripe portal).

---

## Task 7: Privacy / consent section

Toggle hydrated from **server** state `profile.marketing_consent` (Phase-1 B4), reconciled with `getConsent()` (localStorage). Flipping calls `setConsent(next)` then POSTs `/api/analytics/consent/` with `{ consent: next, version: CONSENT_VERSION }` (use the shared `api` — user is authed). Show the honest help text (pixel fully stops next page load). On success toast; on failure revert the toggle + inline error.

- [ ] Step 1: Implement `PrivacySection` (import `getConsent, setConsent, CONSENT_VERSION` from `@/lib/analytics`; POST via `api.post('/analytics/consent/', {...})`).
- [ ] Step 2: `npx tsc --noEmit` clean.
- [ ] Step 3: Commit `feat(settings): marketing-consent toggle`.

**Acceptance:** toggle reflects the server consent on load; flipping it persists (localStorage + server); reload shows the new state.

---

## Task 8: Data export section

Button **Stáhnout moje data** → `triggerDataExport()` (Task 1) with a `loading` state (**Připravuji…**); on error toast. Help text under it.

- [ ] Step 1: Implement `DataSection`.
- [ ] Step 2: `npx tsc --noEmit && npx vitest run` clean.
- [ ] Step 3: Commit `feat(settings): data export download`.

**Acceptance:** clicking downloads `moje-data.json` containing the user's account/prefs/subscription/consent/meal-plans.

---

## Task 9: Final verification

- [ ] Step 1: `cd frontend && npx tsc --noEmit && npx vitest run && npm run lint` — type-clean, all vitest green, no NEW lint problems (repo has pre-existing `no-explicit-any`; count must be unchanged).
- [ ] Step 2: Confirm the page file isn't unwieldy — if `Settings.tsx` > ~400 lines, split each section into `src/components/settings/<Section>.tsx` and re-verify.
- [ ] Step 3: Commit any split/cleanup.
- [ ] Post-deploy (not in this plan): full `/nastaveni` walkthrough on prod — edit prefs, change password, consent toggle, export download, and (throwaway email account) delete. Grep built CSS for the Market Paper tokens (Tailwind drops unknown classes silently).

---

## Self-Review

- **Spec coverage:** Preferences (edit+persist, num_days), Account (provider, verified passive, change password, delete), Subscription (tier/usage/portal), Privacy (consent hydrated from server), Data (export) — all five sections + Navbar entry + route. Google-delete deliberately scoped down (flagged up top).
- **Placeholder scan:** lib layer has complete code + tests; sections cite exact existing patterns (Onboarding lines, BillingSuccess handlePortal) with full Czech copy + acceptance criteria rather than re-pasting large JSX blocks that already exist to copy from — an intentional choice for a large UI where the patterns are established and cited. No TBD.
- **Consistency:** `savePreferences`/`deleteAccountWithPassword`/`changePassword`/`triggerDataExport`/`downloadBlob` names match Task 1 across all consumers; `['profile']` query key and `.data.data` envelope consistent; Market Paper theme + `MainLayout` used throughout.
- **Ambiguity:** delete post-success flow explicit (clear tokens + hard redirect); consent uses shared `api` (authed) not bare axios; num_days stored under `num_days` key.
