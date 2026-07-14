# UX review — prod screenshots (eatalnicek.eu, P0+P1 live)

Captured 2026-06-25 against prod after P0 + P1 deploys. Open the PNGs in your IDE.

| File | What it shows | What to look for |
|------|---------------|------------------|
| `01-landing-desktop.png` | Landing, full page, 1440px | Hero stat row: "97 % přesnost cen" is **gone**, replaced by "Reálné / Ceny z e-shopů". Brighter emerald CTAs. |
| `02-recepty-desktop.png` | Recipe index, full page | Grid of recipe cards (now real links). Food photos. |
| `03-recipe-detail.png` | Kuřecí parmigiana detail | Hero photo is now **grilled chicken**, not scrambled eggs (image backfill). |
| `04-pricing-desktop.png` | Pricing, full page | 3 tiers; "Doporučeno" badge now emerald-500 (passes contrast). |
| `05-landing-mobile-closed.png` | Landing @ 390px | Header: logo + hamburger, **nothing clipped** (was the broken state). |
| `06-landing-mobile-menu.png` | Mobile menu open | Drawer: Recepty / Ceník / Přihlásit se + full-width "Začít zdarma" + X. |
| `07-keyboard-focus-ring.png` | Landing, "Recepty" link focused via Tab | Visible **emerald focus outline** (was invisible before). |

Note: this folder is a review artifact (git-untracked). Delete it whenever — `rm -rf ux-review/`.
