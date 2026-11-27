---
name: storefront-ux-review
description: Review a Uvařto (eatalnicek.eu) screen for retail-style discovery, information density, deal and savings honesty, and mobile usability. Use this whenever the user asks to review, critique, audit, or improve a view or page of the meal planner, including the prompt home, results cards, dish or recipe detail, and shopping list, or mentions UX, layout, hierarchy, "too busy", "where do I look", conversion, discounts, deals display, or how a screen feels to a customer, even if they don't say "storefront" or "UX review". Also use it before a new view ships.
---

# Storefront UX review (Uvařto)

Uvařto is a Czech, prompt-first meal planner. A user types what they want to eat, gets dish cards, and is sent to buy the ingredients. So every screen has two jobs: help the user find a dish they want, and show the retail cues (deals, what's on sale, what to buy) that move them to the basket. Judge each screen against both jobs, and against how much information it shows at once.

## Constraints you must not break

- **No absolute recipe prices.** `PRICE_DISPLAY_ENABLED = false` in `frontend/src/lib/pricing.ts:68` (rolled back). Any CZK total or per-recipe price on a screen is a blocker unless the user has re-enabled it. Check the flag before flagging or approving a price.
- **The live retail cue is the deals headline**, in the form "N z M surovin ve slevě" (N of M ingredients on sale). Good screens lead with it.
- **Never invent savings.** No "ušetříte X Kč", no totals, no percentages unless the number is computed from real data on that screen. A made-up number is a blocker.
- **No unverifiable social proof.** Counts like "500+ receptů" or testimonials need a source the database can derive them from.
- **UI copy is Czech**, with correct diacritics. Review copy in Czech and give an English gloss so the owner can check meaning.

## Map the view to code

Read the component files for the view before judging it. If the user gives a screenshot instead, review the screenshot, and say which code you could not confirm.

| View | Purpose | Main files |
|---|---|---|
| 1. Prompt home | Get the user to type what they want | `frontend/src/pages/CreatePlan.tsx`, `frontend/src/components/discover/DealsStrip.tsx` |
| 2. Results cards | Pick a dish | `frontend/src/components/discover/RecipeCard.tsx`, `RecipeSheet.tsx`, `frontend/src/pages/RecipeIndexPage.tsx` |
| 3. Dish detail | Decide to cook it and buy it | `frontend/src/pages/RecipePage.tsx`, `frontend/src/components/recipe/RecipeIngredients.tsx`, `frontend/src/pages/PublicRecipePage.tsx` |
| 4. Shopping list | Buy the ingredients | `frontend/src/pages/ShoppingList.tsx`, `frontend/src/components/discover/BasketTray.tsx` |

If the user names a view not in this table, find its files by searching for the page name, and add it to the table in your report.

## Procedure

1. **State the view's job** in one sentence, from the user's point of view ("Get a user to type a meal request and see a deal they can act on").
2. **Read the view's code** and, when available, a screenshot. Note what is visible without scrolling, what is behind a tap, and what is in the DOM but hidden.
3. **Run the checklist below.** Record each finding with its file and line, the view, and the fix.
4. **Report** using the output format. Do not change code unless the user asks. This skill reviews; it does not redesign.

## Checklist

### A. Discovery and retail cues
- One primary action per view. A second competing action is a should-fix; two equal primary buttons is a blocker.
- The value proposition and the main action are visible without scrolling on a phone.
- The deal is the visual anchor on cards and the list, not the cooking time, nutrition, or the recipe author.
- Prompt examples on the home screen use phrasings people really type, such as "co uvařit z X", "domácí krabičková", "keto", "cukrovka". Abstract examples like "jídelníček na míru" are a should-fix.
- Every route from a card to buying goes through a visible, labelled step ("Přidat do nákupu"), not a hidden gesture.

### B. Information density
- Results cards show at most three facts: image, title, and one reason line (for example "3 z 5 surovin ve slevě"). More than three is a should-fix; more than four is a blocker.
- Show about six results before collapsing the rest behind "Zobrazit další". Infinite walls of cards are a should-fix.
- Filters sit behind one control on mobile. Filter bars with more than about three visible rows are a should-fix.
- Dish detail leads with the deal, then ingredients with on-sale items marked. Preparation steps sit below the fold or in a collapsed section.
- The shopping list is grouped (by category or store section), with the deal count at the top.

### C. Deal and savings honesty
- The deal headline uses only the "N z M surovin ve slevě" form, and N and M come from data on that screen. Check the source of N and M.
- No CZK totals or per-recipe absolute prices while the price flag is off. The `priced` wording in `RecipeIngredients.tsx:173` ("N z M surovin oceněno") implies pricing. Flag it as should-fix and say what it would read as to a user, until the owner confirms the intended wording.
- Discount and "sleva" badges name the store or the source when they make a claim.
- Any savings figure must be computed from data and labelled as an estimate.

### D. Mobile usability
- 16px side gutter, and no horizontal page scroll.
- Tap targets at least 44px high.
- A sticky bottom CTA must not cover the last item of a list.
- Text under 14px on a phone is a should-fix. Text under 12px is a blocker.

### E. Copy and language
- Czech with correct diacritics (ě, š, č, ř, ž, ů).
- One verb-led primary button label per view.
- Give the English gloss next to each copy line you quote in the report.

### F. Visual quality
- Text contrast meets WCAG AA (4.5:1 for body text). Low-contrast captions on coloured cards are a should-fix.
- Icons are consistent in style. Mixing hand-drawn doodles with photos looks unfinished and is a should-fix.
- One accent colour family per screen. More than two competing accents is a should-fix.

## Output format

Start with a one-line verdict per view reviewed: `Ready`, `Ready with should-fixes`, or `Blocked`.

Then a table, most severe first:

| Severity | View | Where | Finding | Fix |
|---|---|---|---|---|
| Blocker / Should-fix / Nice | 1–4 | file:line | what is wrong, and why it hurts the user or the money path | the smallest change that fixes it |

Keep a `Notes` section for things you could not confirm (for example, a screenshot with no matching code, or a flag you could not read).

## Why these rules

The product's money comes from a user who understands what to buy and trusts the number they see. Density failures make a screen hard to scan, so the user leaves. Savings figures that the data can't back make the user distrust everything else on the page, which costs more than a weaker headline. The rules are ordered by how much they hurt that path, so use the severity levels as written rather than rating everything as a blocker.
