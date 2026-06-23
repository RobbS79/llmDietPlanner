# Persona Test Prompts — Meal Planner Evaluation

Five realistic free-text dietary-goal prompts, one per target persona, for manually
testing the meal planner end-to-end: plan generation → recipe coherence → shopping list
→ real prices. Each prompt deliberately bundles the four onboarding axes
(goal + household + cooking time + budget/store) the way real users phrase them, so they
double as stress tests for natural-language parsing.

Personas reference: see auto-memory `target-personas`. Czech versions included because
real CZ/SK users type in Czech — use them as demo seeds or test inputs.

---

## 1. Mum / Budget Family Feeder

**EN**
> Weekly dinners for 2 adults and 2 kids (5 and 8), one of them is a picky eater. Keep it under 2000 CZK for the week, nothing too fancy, max 30 min to cook. We shop at Lidl and Kaufland. Bonus if I can reuse leftovers.

**CZ**
> Týdenní večeře pro 2 dospělé a 2 děti (5 a 8 let), jedno je vybíravé. Do 2000 Kč na týden, nic složitého, vaření max 30 minut. Nakupujeme v Lidlu a Kauflandu. Ideálně ať můžu využít zbytky.

**What to evaluate**
- [ ] Plan respects the ~2000 CZK/week budget (check total basket price)
- [ ] Cooking time stays ≤30 min per recipe
- [ ] Recipes are kid-friendly / simple (no exotic ingredients)
- [ ] Store constraint honored (Lidl + Kaufland items only)
- [ ] Leftover reuse / batch logic present
- [ ] Shopping list items are real & priced (no fabricated ingredients)

---

## 2. Partner / Time-Pressed Urban Couple

**EN**
> Dinner for two after work, we both hate cooking long. 15–20 minutes max, healthy-ish, order everything from Rohlík in one go. We're not on a budget, just want it sorted fast.

**CZ**
> Večeře pro dva po práci, oba nesnášíme dlouhé vaření. Max 15–20 minut, ať je to zdravé, všechno objednat z Rohlíku najednou. Cena neřešíme, hlavně ať to mám rychle hotové.

**What to evaluate**
- [ ] All recipes ≤20 min
- [ ] Single-store mode honored (Rohlík only, one-click order story)
- [ ] Minimal/short ingredient lists
- [ ] Healthy framing without over-optimizing for price
- [ ] Shopping list maps cleanly to Rohlík catalog with real prices

---

## 3. Single / Fitness Macro-Tracker

**EN**
> I train 5x a week. Need a high-protein plan, around 180g protein and 2400 kcal a day, from stuff I can buy at Rohlík. Meal-prep friendly — I cook once on Sunday. Chicken/fish is fine, not too expensive.

**CZ**
> Trénuju 5x týdně. Potřebuju plán s vysokým obsahem bílkovin, cca 180 g bílkovin a 2400 kcal denně, z věcí dostupných na Rohlíku. Ať se to dá připravit dopředu — vařím jednou v neděli. Kuře/ryba v pohodě, ne moc drahé.

**What to evaluate**
- [ ] Daily macros land near target (180g protein / 2400 kcal, within ~5%)
- [ ] Per-meal macro display present and plausible
- [ ] Meal-prep / batch-cook structure (cook-once-Sunday)
- [ ] High-protein ingredients available at Rohlík with real prices
- [ ] Nutritional numbers are consistent recipe ↔ plan total

---

## 4. Single / Medical Diet Patient

**EN**
> Just got diagnosed with celiac. I need a fully gluten-free week, simple meals for one person, and I need to be 100% sure every ingredient is safe. I usually shop at Albert.

**CZ**
> Zjistili mi celiakii. Potřebuju celý týden bezlepkově, jednoduchá jídla pro jednoho, a musím mít jistotu, že každá surovina je bezpečná. Nakupuju většinou v Albertu.

**What to evaluate**
- [ ] ZERO gluten-containing ingredients anywhere in the plan or list
- [ ] Allergen filtering is strict (no "usually safe" hedging)
- [ ] Portions scaled to a single person
- [ ] Ingredient transparency (can the user see what's in each item?)
- [ ] Store constraint (Albert) honored
- [ ] **Highest-risk test** — any violation here is a trust-breaking bug

---

## 5. Single / Wellness Explorer

**EN**
> I love cooking and want to try something new this week — Mediterranean or Asian, varied, with real nutrition info. Cooking time doesn't matter. I shop at Rohlík and don't mind paying for good ingredients.

**CZ**
> Rád/a vařím a chci tento týden zkusit něco nového — středomořskou nebo asijskou kuchyni, pestré, s reálnými nutričními hodnotami. Na čase nezáleží. Nakupuju na Rohlíku a nevadí mi připlatit si za kvalitní suroviny.

**What to evaluate**
- [ ] Recipe variety / cuisine diversity (Mediterranean / Asian honored)
- [ ] Premium ingredients allowed (not over-simplified to 5-ingredient meals)
- [ ] Nutritional detail present per recipe
- [ ] No artificial budget capping
- [ ] Shopping list real & priced at Rohlík

---

## Cross-prompt evaluation checklist

Run for every prompt, regardless of persona:

- [ ] **No fabricated ingredients** — every shopping-list item exists in the selected store (core P0 — see `product-vision`)
- [ ] **Real prices** — items priced via catalog, not LLM estimate (see `prod-pricing-fabrication-surface`)
- [ ] **Recipe ↔ shopping-list coherence** — every recipe ingredient appears on the list; no orphan list items
- [ ] **Store/mode constraint honored** — single vs mix_trips behaves as the prompt implies
- [ ] **Plan completeness** — correct number of days/meals generated
- [ ] **Czech input parity** — CZ prompt produces an equivalent plan to the EN prompt

## Results log

| # | Persona | Date tested | Plan OK? | Recipes OK? | Shopping list OK? | Prices real? | Notes |
|---|---------|-------------|----------|-------------|-------------------|--------------|-------|
| 1 | Budget Family | | | | | | |
| 2 | Time-Pressed Couple | | | | | | |
| 3 | Fitness | | | | | | |
| 4 | Medical Diet | | | | | | |
| 5 | Wellness Explorer | | | | | | |
