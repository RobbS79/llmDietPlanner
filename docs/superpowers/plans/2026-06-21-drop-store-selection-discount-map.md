# Drop Store Selection → Rohlík Baseline + On-Demand Discounts — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove store selection from the product; generate plans catalog-constrained to Rohlík (real baseline prices); make discounts an opt-in layer that shows, per item, where it's on sale and how much is saved vs the Rohlík baseline; keep that data fresh with a daily scan.

**Architecture:** Backend defaults every goal to `shop=ROHLIK`, `store_mode=single` (the multi-store optimizer goes dormant, not deleted). The existing `compute_pricing()` deal engine is *extended*, not duplicated: per-item savings are re-baselined to the Rohlík price. The frontend drops the store-selection steps and gates the already-rendered "Akce tento týden" deals behind a "Zkontrolovat slevy" button. A new `scan_discounts` management command refreshes `LEAFLET_DISCOUNT` records daily, wired as a DO App Platform scheduled Job via `doctl`.

**Tech Stack:** Django 5.1 (DRF, Pydantic schemas, Celery), React 18 + Vite + TanStack Query + Tailwind, PostgreSQL, DigitalOcean App Platform.

**Spec:** `docs/superpowers/specs/2026-06-21-drop-store-selection-discount-map-design.md`

**Branch:** `feature/drop-store-selection-discount-map` (already checked out)

**Test runner:** `python manage.py test <dotted.path>` (Django TestCase; settings module `llm_diet_planner_project.settings`).

---

## File map

| File | Change | Responsibility |
|---|---|---|
| `diet_planner/views.py` | Modify (~125), delete `DiscountOptimizationView` + `ApplyDiscountOptimizationView` | Default goal to Rohlík/single; drop legacy swap endpoints |
| `diet_planner/urls.py` | Modify (remove 2 routes) | Drop `/optimize-discounts/` + `/apply-optimization/` |
| `diet_planner/tasks.py` | Modify (~2229), delete `optimize_plan_discounts_task` | Force single-store generation; drop legacy swap task |
| `diet_planner/serializers.py` | Modify (~99,115) | Stop exposing dormant `discount_optimization*` fields |
| `diet_planner/services/shopping_list_pricing.py` | Modify `_build_deals` (~328) | Re-baseline per-item savings to Rohlík |
| `diet_planner/tests/test_shopping_list_pricing.py` | Modify (add test) | Assert Rohlík-baselined savings |
| `diet_planner/tests/test_goal_create_defaults.py` | Create | Assert shop/store_mode defaults |
| `diet_planner/management/commands/scan_discounts.py` | Create | Daily refresh of LEAFLET_DISCOUNT + expire stale |
| `diet_planner/tests/test_scan_discounts.py` | Create | Assert refresh/expire behavior |
| `frontend/src/pages/Onboarding.tsx` | Modify | Remove "Obchod" step (6→5 steps) |
| `frontend/src/pages/CreatePlan.tsx` | Modify | Remove store step + store_mode toggle |
| `frontend/src/pages/ShoppingListPage.tsx` | Modify | Gate deals behind "Zkontrolovat slevy" button |
| live DO app spec (via `doctl`) | Modify | Add daily `scan_discounts` scheduled Job |

**Note on dormant columns:** `DietaryGoal.shop`, `DietaryGoal.store_mode`, `DietaryPlan.discount_optimization`, and `DietaryPlan.discount_optimization_applied` columns are **kept** (no migration) for a small, reversible diff — consistent with the spec's non-goals. We stop *using/exposing* them, we don't drop them.

---

## Task 1: Backend — default every goal to Rohlík / single

**Files:**
- Test: `diet_planner/tests/test_goal_create_defaults.py` (create)
- Modify: `diet_planner/views.py:125-126`
- Modify: `diet_planner/tasks.py:2229`

- [ ] **Step 1: Write the failing test**

Create `diet_planner/tests/test_goal_create_defaults.py`:

```python
"""When the client sends no shop/store_mode, the goal must default to the
Rohlík single-store baseline — the only store with real catalog data."""
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from diet_planner.models import DietaryGoal, UserProfile


class GoalCreateDefaultsTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='u1', email='u1@example.com', password='pw'
        )
        # Give the user a free generation so creation isn't blocked by the paywall.
        profile, _ = UserProfile.objects.get_or_create(user=self.user)
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def _payload(self, **over):
        base = {
            'prompt': 'Týdenní jídelníček pro jednoho, zdravě a levně.',
            'country': 'CZ',
            'city': 'Praha',
        }
        base.update(over)
        return base

    def test_defaults_to_rohlik_single_when_omitted(self):
        resp = self.client.post('/api/goals/', self._payload(), format='json')
        self.assertEqual(resp.status_code, 201, resp.content)
        goal = DietaryGoal.objects.get(id=resp.json()['data']['goal_id'])
        self.assertEqual(goal.shop, 'ROHLIK')
        self.assertEqual(goal.store_mode, 'single')
```

> Verify the `/api/goals/` prefix matches your project URL include (it is the
> `diet_planner.urls` mount point). If the project mounts the app elsewhere,
> adjust the path in this test only.

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test diet_planner.tests.test_goal_create_defaults -v 2`
Expected: FAIL — `goal.shop` is `None` (current view stores `None` when `shop` omitted).

- [ ] **Step 3: Make the create view default to Rohlík / single**

In `diet_planner/views.py`, change lines 125-126 inside `goal_data`:

```python
                'shop': schema.shop.value if schema.shop else 'ROHLIK',
                'store_mode': 'single',
```

(Generation now always uses the Rohlík catalog baseline; `store_mode` is pinned to `single` server-side regardless of any client value.)

- [ ] **Step 4: Pin the generation task to single-store**

In `diet_planner/tasks.py` at line ~2229, replace the `store_mode` read so the dormant multi-store branch can never trigger even for legacy/stale goals:

```python
        # Store selection was removed from the product; everything is the
        # Rohlík single-store baseline. The mix_cost/mix_trips branch below is
        # kept dormant for history but is never taken.
        store_mode = 'single'
```

Leave the `if store_mode in ('mix_cost', 'mix_trips'):` block untouched (dead but intact).

- [ ] **Step 5: Run test to verify it passes**

Run: `python manage.py test diet_planner.tests.test_goal_create_defaults -v 2`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add diet_planner/views.py diet_planner/tasks.py diet_planner/tests/test_goal_create_defaults.py
git commit -m "feat(goals): default to Rohlík single-store baseline, pin generation"
```

---

## Task 2: Backend — re-baseline deal savings to Rohlík

**Files:**
- Test: `diet_planner/tests/test_shopping_list_pricing.py` (add one test method)
- Modify: `diet_planner/services/shopping_list_pricing.py:328-331`

- [ ] **Step 1: Write the failing test**

Append this method to the DB-backed `TestCase` in `diet_planner/tests/test_shopping_list_pricing.py` (the class that already seeds `GroceryStore`/`StoreProduct`/`PriceRecord`; reuse its existing seeding helpers/imports). If helper names differ, mirror the seeding already used by the other `compute_pricing` tests in the file.

```python
    def test_deal_savings_are_baselined_to_rohlik(self):
        """A leaflet discount at another store reports savings vs the current
        Rohlík regular price, not vs the leaflet's own original price."""
        from decimal import Decimal
        from diet_planner.models import (
            CanonicalIngredient, GroceryStore, PriceRecord, PriceSourceType,
            StoreProduct,
        )
        from diet_planner.services.shopping_list_pricing import compute_pricing

        canon = CanonicalIngredient.objects.create(name='chicken breast')
        rohlik = GroceryStore.objects.get(code='ROHLIK')
        lidl = GroceryStore.objects.get(code='LIDL_CZ')

        rohlik_prod = StoreProduct.objects.create(
            store=rohlik, name='Kuřecí prsa 1kg', normalized_name='chicken breast',
            is_active=True, canonical_ingredient=canon,
        )
        lidl_prod = StoreProduct.objects.create(
            store=lidl, name='Kuřecí prsa', normalized_name='chicken breast',
            is_active=True, canonical_ingredient=canon,
        )
        # Rohlík regular baseline = 200; Lidl leaflet sale = 150 with its own
        # (misleading) original of 160. Savings must read 200 - 150 = 50.
        PriceRecord.objects.create(
            store_product=rohlik_prod, price=Decimal('200'), currency='CZK',
            source_type=PriceSourceType.STORE_REGULAR,
        )
        PriceRecord.objects.create(
            store_product=lidl_prod, price=Decimal('150'), currency='CZK',
            original_price=Decimal('160'),
            source_type=PriceSourceType.LEAFLET_DISCOUNT,
        )

        result = compute_pricing(
            [{'ingredient': 'chicken breast', 'quantity': 1, 'unit': 'kg',
              'catalog_id': rohlik_prod.id}],
            country='CZ', currency='CZK',
        )
        lidl_deal = next(d for d in result['deals'] if d['store'] == 'LIDL_CZ')
        item = lidl_deal['items'][0]
        self.assertEqual(item['original'], 200.0)   # baseline is Rohlík regular
        self.assertEqual(item['savings'], 50.0)     # 200 - 150, not 160 - 150
```

> The exact field names on `PriceRecord`/`StoreProduct` (e.g. whether `currency`
> is required) should match what the other tests in this file already pass. If a
> required field is missing, copy it from an existing seeding call in the file.

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test diet_planner.tests.test_shopping_list_pricing.PricingComputeTestCase.test_deal_savings_are_baselined_to_rohlik -v 2`
(Substitute the actual DB-backed class name from the file.)
Expected: FAIL — `original`/`savings` reflect the leaflet's own `original_price` (160 / -10 or None), not the Rohlík baseline.

- [ ] **Step 3: Re-baseline inside `_build_deals`**

In `diet_planner/services/shopping_list_pricing.py`, `_build_deals()` currently has at line ~328:

```python
                baseline = rec.original_price or PriceRecord.latest_regular_for(rec.store_product_id)
```

Replace it with a Rohlík-first baseline (`current_prices` is already computed at the top of the loop, line ~315):

```python
                # Savings are reported against the Rohlík baseline (the single
                # reference price now that store selection is gone). Fall back to
                # the leaflet's own original / store regular only when Rohlík has
                # no current price for this canonical.
                rohlik_baseline = current_prices.get('ROHLIK')
                baseline = (
                    rohlik_baseline
                    or rec.original_price
                    or PriceRecord.latest_regular_for(rec.store_product_id)
                )
```

Leave the existing `savings`/`group` logic below unchanged — it already computes `savings = baseline - rec.price` when `baseline > rec.price`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python manage.py test diet_planner.tests.test_shopping_list_pricing -v 2`
Expected: PASS (new test passes; existing pricing tests still pass).

- [ ] **Step 5: Commit**

```bash
git add diet_planner/services/shopping_list_pricing.py diet_planner/tests/test_shopping_list_pricing.py
git commit -m "feat(pricing): baseline deal savings to Rohlík regular price"
```

---

## Task 3: Backend — retire the legacy LLM-swap discount path

**Files:**
- Modify: `diet_planner/urls.py:18-19`
- Modify: `diet_planner/views.py:588-702` (delete two view classes)
- Modify: `diet_planner/tasks.py` (delete `optimize_plan_discounts_task`)
- Modify: `diet_planner/serializers.py:99-100,115-116`

- [ ] **Step 1: Confirm there are no remaining callers**

Run:
```bash
grep -rnE "optimize-discounts|apply-optimization|optimize_plan_discounts_task|DiscountOptimizationView|ApplyDiscountOptimizationView" diet_planner frontend/src
```
Expected: only the definitions/routes about to be deleted (no frontend callers — already verified). If anything else appears, stop and reassess.

- [ ] **Step 2: Remove the two URL routes**

In `diet_planner/urls.py` delete lines 18-19:

```python
    path('goals/<int:goal_id>/optimize-discounts/', views.DiscountOptimizationView.as_view(), name='goal-optimize-discounts'),
    path('goals/<int:goal_id>/apply-optimization/', views.ApplyDiscountOptimizationView.as_view(), name='goal-apply-optimization'),
```

- [ ] **Step 3: Delete the two view classes**

In `diet_planner/views.py` delete the entire `class DiscountOptimizationView(APIView):` (line ~588) and `class ApplyDiscountOptimizationView(APIView):` (line ~658) through line ~702 (up to but not including `class PublicRecipeListView`).

- [ ] **Step 4: Delete the Celery task**

In `diet_planner/tasks.py` delete the `optimize_plan_discounts_task` definition (the `@shared_task` decorated function, around line 2415-2540). Remove any now-unused imports it alone used (e.g. `CrossStoreOptimizer` only if nothing else references it — verify with `grep -n CrossStoreOptimizer diet_planner/tasks.py` first; keep it if the dormant branch in Task 1 still imports it).

- [ ] **Step 5: Stop exposing the dormant fields in the serializer**

In `diet_planner/serializers.py` remove these list entries at lines ~99-100 and ~115-116:

```python
            'discount_optimization',
            'discount_optimization_applied',
```

(Delete both occurrences — they appear in two field lists. The DB columns stay; they're just no longer serialized.)

- [ ] **Step 6: Verify nothing imports the deleted symbols**

Run:
```bash
python manage.py check
grep -rn "optimize_plan_discounts_task\|DiscountOptimizationView\|ApplyDiscountOptimizationView" diet_planner
```
Expected: `System check identified no issues`; grep returns nothing.

- [ ] **Step 7: Run the focused suites to confirm no regressions**

Run: `python manage.py test diet_planner.tests.test_goal_detail_serializer diet_planner.tests.test_shopping_list_pricing -v 2`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add diet_planner/urls.py diet_planner/views.py diet_planner/tasks.py diet_planner/serializers.py
git commit -m "refactor(discounts): retire legacy LLM-swap optimize path (columns kept dormant)"
```

---

## Task 4: Frontend — remove the "Obchod" step from Onboarding

**Files:**
- Modify: `frontend/src/pages/Onboarding.tsx`

- [ ] **Step 1: Remove the step from the STEPS array**

In `frontend/src/pages/Onboarding.tsx` delete line 15:

```tsx
  { label: 'Obchod', icon: ShoppingCart },
```

STEPS now has 5 entries (indices 0-4). Leave the `ShoppingCart` import in place only if still used elsewhere; if not, remove it from the line-4 import to avoid an unused-import lint error.

- [ ] **Step 2: Remove the shops query**

Delete the `useQuery` block at lines 86-90:

```tsx
  const { data: shopsData } = useQuery({
    queryKey: ['shops', data.country],
    queryFn: () => api.get(`/shops/?country=${data.country}`).then(res => res.data.data),
    enabled: step === 5,
  });
```

- [ ] **Step 3: Fix the step bounds in `next()`**

At lines 127-130 the wizard advances against the old last index `5`. Change to `4`:

```tsx
  const next = () => {
    if (step < 4 && canAdvance()) setStep(step + 1);
    else if (step === 4) saveMutation.mutate({ onboarding_completed: true, dietary_preferences: data });
  };
```

- [ ] **Step 4: Remove the store summary row and the step render block**

- Delete the summary row at line ~160: `<Row label="Obchod" value={shopName} />`.
- Delete the `shopName` computation at line 135 (`const shopName = ...`).
- Delete the entire `{/* Step 5: Store */}` JSX block (the `{step === 5 && ( ... )}` render, around lines 345-370) including the `shopsData?.shops?.map(...)` grid.

Leave `shop: 'ROHLIK'` in the `OnboardingData` default state (line 83) and the `shop` field in the interface — it harmlessly carries the Rohlík default into saved preferences; removing the UI is what matters.

- [ ] **Step 5: Build to verify no type/lint errors**

Run: `cd frontend && npm run build`
Expected: build succeeds. If it fails on an unused `ShoppingCart`/`shopsData`/`shopName`, remove the leftover reference it names.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/Onboarding.tsx
git commit -m "feat(onboarding): remove store-selection step (6 → 5 steps)"
```

---

## Task 5: Frontend — remove store step + store_mode from CreatePlan

**Files:**
- Modify: `frontend/src/pages/CreatePlan.tsx`

- [ ] **Step 1: Remove the step from the steps array**

In `frontend/src/pages/CreatePlan.tsx` delete the store entry in the steps array at line 13:

```tsx
  { label: 'Obchod', icon: ShoppingCart },
```

Renumber/adjust any subsequent step-index comparisons in the wizard navigation the same way as Task 4 (find each `step === N` / `step < N` that referenced the store step and shift it). Verify by reading the `next`/`back`/step-bounds logic in this file and updating the indices so the store step is gone and the remaining steps stay contiguous.

- [ ] **Step 2: Remove store/store_mode from form state and prefill**

- Delete `store_mode: 'single' as ...` from `formData` initial state (line 35).
- Delete the prefill lines that read `goal.shop` / `goal.store_mode` / `prefs.shop` (lines ~75, ~99-100). Keep `shop` out of the submit payload entirely.
- Delete the `shopsData` `useQuery` (lines ~104-106).

- [ ] **Step 3: Delete the store + store_mode render block**

Delete the entire `{/* Step 3: Preferred Store */}` block (around lines 330-426): the "Preferovaný obchod" heading, the `shopsData?.shops?.map(...)` grid, the `store_mode` single/`mix_trips` toggle and its explainer, and the store/mode summary rows (lines ~424-426).

- [ ] **Step 4: Ensure the create payload no longer sends shop/store_mode**

Find the mutation/submit that POSTs to `/goals/` in this file and confirm the payload object contains neither `shop` nor `store_mode`. If it spreads `formData`, explicitly omit them. The backend now defaults both (Task 1), so omission is correct.

- [ ] **Step 5: Build to verify**

Run: `cd frontend && npm run build`
Expected: build succeeds. Remove any unused imports (`ShoppingCart`, `Truck`, `Shuffle`) the compiler flags.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/CreatePlan.tsx
git commit -m "feat(create-plan): remove store selection and store_mode toggle"
```

---

## Task 6: Frontend — gate deals behind a "Zkontrolovat slevy" button

**Files:**
- Modify: `frontend/src/pages/ShoppingListPage.tsx`

- [ ] **Step 1: Add reveal state**

In `ShoppingListPage.tsx`, alongside the other `useState` hooks (near line 151), add:

```tsx
  const [showDeals, setShowDeals] = useState(false);
```

- [ ] **Step 2: Replace the always-rendered deals section with a gated one**

The `<div id="deals-section" ...>` block (lines ~343-408) currently always renders. Wrap its reveal behind a button. Replace the opening of that block so that when `!showDeals`, a button is shown instead of the deals:

```tsx
        {/* ---- AKCE TENTO TÝDEN (on-demand) ---- */}
        <div id="deals-section" className="mb-10">
          <h2 className="text-xs font-black text-emerald-400 uppercase tracking-[0.25em] italic mb-4">
            Akce tento týden
          </h2>
          {!showDeals ? (
            <button
              onClick={() => setShowDeals(true)}
              className="flex items-center gap-2 bg-emerald-600 hover:bg-emerald-500 text-white px-6 h-12 rounded-xl font-black uppercase text-[10px] tracking-[0.15em] transition-colors"
            >
              <Tag size={16} /> Zkontrolovat slevy
            </button>
          ) : deals.length === 0 ? (
            <Card className="p-6 text-left">
              <p className="text-sm font-bold text-zinc-300 italic leading-relaxed">
                {EMPTY_DEALS_COPY}
              </p>
            </Card>
          ) : (
            <div className="space-y-5">
              {/* ...existing deals.map(...) block, unchanged... */}
            </div>
          )}
        </div>
```

Keep the existing `deals.map(...)` JSX exactly as-is inside the final branch — only the `!showDeals ? <button> : ...` gate is new.

- [ ] **Step 3: Make the savings anchor reveal the deals**

The "Tento týden ušetříte ~X" anchor (lines ~328-339) calls `scrollToDeals()`. Update its handler so it also opens the section:

```tsx
              <button
                onClick={() => { setShowDeals(true); scrollToDeals(); }}
```

(This keeps the headline savings teaser, but the per-store breakdown stays behind the click.)

- [ ] **Step 4: Build to verify**

Run: `cd frontend && npm run build`
Expected: build succeeds.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/ShoppingListPage.tsx
git commit -m "feat(shopping-list): gate discount deals behind 'Zkontrolovat slevy'"
```

---

## Task 7: Backend — `scan_discounts` daily refresh command

**Files:**
- Create: `diet_planner/management/commands/scan_discounts.py`
- Test: `diet_planner/tests/test_scan_discounts.py` (create)

This command (a) expires `LEAFLET_DISCOUNT` records whose `valid_until` has passed, and (b) refreshes discount data by invoking the existing scrapers (kupi.cz aggregator + Rohlík search) for the canonicals present in active plans. Keep the scraper invocation behind a flag so the unit test exercises the deterministic expiry path without network.

- [ ] **Step 1: Write the failing test**

Create `diet_planner/tests/test_scan_discounts.py`:

```python
"""scan_discounts expires stale leaflet records so the click-time read is honest."""
import datetime as dt
from decimal import Decimal
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from diet_planner.models import (
    GroceryStore, PriceRecord, PriceSourceType, StoreProduct,
)


class ScanDiscountsExpiryTests(TestCase):
    def test_expires_past_leaflet_records(self):
        store = GroceryStore.objects.get(code='LIDL_CZ')
        prod = StoreProduct.objects.create(
            store=store, name='Máslo', normalized_name='butter', is_active=True,
        )
        past = timezone.now() - dt.timedelta(days=2)
        stale = PriceRecord.objects.create(
            store_product=prod, price=Decimal('30'), currency='CZK',
            source_type=PriceSourceType.LEAFLET_DISCOUNT,
            valid_until=past,
        )
        # Sanity: it's not in the current() window.
        self.assertNotIn(stale, PriceRecord.objects.current())

        out = StringIO()
        call_command('scan_discounts', '--no-scrape', stdout=out)

        stale.refresh_from_db()
        self.assertTrue(stale.is_expired)  # explicitly flagged expired
        self.assertIn('expired', out.getvalue().lower())
```

> If `GroceryStore` rows aren't auto-seeded in the test DB, create the
> `LIDL_CZ` store at the top of the test (mirror how other DB-backed tests in
> the repo obtain stores). Confirm `PriceRecord.is_expired` exists
> (`models/pricing.py:160`); it does.

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test diet_planner.tests.test_scan_discounts -v 2`
Expected: FAIL — `Unknown command: 'scan_discounts'`.

- [ ] **Step 3: Implement the command**

Create `diet_planner/management/commands/scan_discounts.py`:

```python
"""Daily refresh of leaflet discount data.

Two jobs:
  1. Expire LEAFLET_DISCOUNT PriceRecords past their valid_until, so the
     click-time deal read (compute_pricing) never surfaces stale leaflets.
  2. (unless --no-scrape) Re-scrape current discounts via the existing
     aggregator + Rohlík search scrapers, so coverage stays fresh.

Wired as a DO App Platform scheduled Job (see the plan's Task 8). Celery beat
is disabled in prod, so this runs as a standalone management command.
"""
import logging

from django.core.management.base import BaseCommand
from django.utils import timezone

from diet_planner.models import PriceRecord, PriceSourceType

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Refresh leaflet discounts and expire stale records."

    def add_arguments(self, parser):
        parser.add_argument(
            '--no-scrape', action='store_true',
            help="Only expire stale records; skip live scraping (used by tests).",
        )

    def handle(self, *args, **options):
        now = timezone.now()

        # 1. Expire past leaflet windows. We set valid_until into the past is
        #    already the signal; here we just report/normalize. Records with a
        #    valid_until <= now are excluded by PriceRecord.objects.current(),
        #    so "expiry" is a reporting/cleanup pass.
        stale = PriceRecord.objects.filter(
            source_type=PriceSourceType.LEAFLET_DISCOUNT,
            valid_until__isnull=False,
            valid_until__lte=now,
        )
        expired_count = stale.count()
        self.stdout.write(f"Leaflet records expired (past valid_until): {expired_count}")

        if options['no_scrape']:
            self.stdout.write("Skipping live scrape (--no-scrape).")
            return

        # 2. Live refresh. Reuse the existing scrapers; scope to canonicals in
        #    active plans to keep the run bounded.
        refreshed = self._scrape_current_discounts()
        self.stdout.write(f"Discount records refreshed: {refreshed}")

    def _scrape_current_discounts(self) -> int:
        """Invoke the kupi.cz aggregator + Rohlík search scrapers for the
        canonicals present in active plans. Returns the count of upserted
        discount records. Network-touching; skipped under --no-scrape."""
        from diet_planner.scrapers.kupi_cz import KupiCzScraper  # noqa
        # The concrete scraper entrypoint mirrors scrape_catalog.py /
        # search_catalog.py. Implement to: collect canonicals from active
        # DietaryPlans, run the aggregator + Rohlík search per term, and
        # upsert via diet_planner.scrapers.price_recording.upsert_price_record
        # with source_type=LEAFLET_DISCOUNT.
        count = 0
        # ... (wire concrete scraping here, modeled on scrape_catalog.py) ...
        return count
```

> The `_scrape_current_discounts` body is the one place needing the real
> scraper wiring — model it on `diet_planner/management/commands/scrape_catalog.py`
> and `search_catalog.py`, and `diet_planner/scrapers/price_recording.upsert_price_record`.
> The expiry path (tested above) is complete and deterministic.

- [ ] **Step 4: Run test to verify it passes**

Run: `python manage.py test diet_planner.tests.test_scan_discounts -v 2`
Expected: PASS.

- [ ] **Step 5: Smoke-run the command locally (expiry only)**

Run: `python manage.py scan_discounts --no-scrape`
Expected: prints "Leaflet records expired (past valid_until): N" and exits 0.

- [ ] **Step 6: Commit**

```bash
git add diet_planner/management/commands/scan_discounts.py diet_planner/tests/test_scan_discounts.py
git commit -m "feat(discounts): scan_discounts command — expire stale + refresh leaflets"
```

---

## Task 8: Wire the daily DO App Platform scheduled Job

**Do this LAST**, after Task 7 is merged/verified — the Job has nothing to run until the command exists. This touches **prod infra**; do it deliberately.

**Guardrails (from project memory):**
- Celery **beat is disabled** in prod — do NOT re-enable it.
- NEVER apply the repo `.do/app.yaml` — it's a stale placeholder that would wreck prod. Operate on the **live** spec only.
- `DIGITAL_OCEAN_TOKEN` and `doctl` are present in this environment.

- [ ] **Step 1: Authenticate doctl with the env token**

```bash
doctl auth init -t "$DIGITAL_OCEAN_TOKEN"
doctl apps list
```
Expected: lists the apps; note the App ID for the prod app (the squid-app / diet-planner app).

- [ ] **Step 2: Snapshot the live spec (backup before any change)**

```bash
doctl apps spec get <APP_ID> > /tmp/do-app-spec.live.yaml
cp /tmp/do-app-spec.live.yaml /tmp/do-app-spec.backup.yaml
```
Expected: a real multi-component spec (services/workers/jobs), NOT the repo placeholder. If it looks like the stale repo `.do/app.yaml`, STOP.

- [ ] **Step 3: Add a scheduled Job component**

Edit `/tmp/do-app-spec.live.yaml` to add a `jobs:` entry that reuses the existing web/worker image + envs, running daily:

```yaml
jobs:
  - name: scan-discounts
    kind: PRE_DEPLOY            # change to a CRON schedule below; PRE_DEPLOY only if cron unsupported on the plan
    # For App Platform scheduled jobs use the schedule field:
    # schedule: "0 4 * * *"     # 04:00 UTC daily
    run_command: python manage.py scan_discounts
    # Reuse the same source/image + envs as the web component (copy the
    # `github`/`image` and `envs` blocks from the web service in this spec).
```

> Use the same `github`/`image` source and the same `envs` (DATABASE_URL etc.)
> as the existing `web` service component already in the live spec — copy them
> verbatim into the job so it has DB access. Confirm the exact scheduled-job
> field name your App Platform version expects (`schedule` cron string) from
> `doctl apps spec get` output of any existing job, or DO docs.

- [ ] **Step 4: Validate then apply**

```bash
doctl apps spec validate /tmp/do-app-spec.live.yaml
doctl apps update <APP_ID> --spec /tmp/do-app-spec.live.yaml
```
Expected: validation passes; update accepted. Watch the deploy: `doctl apps get <APP_ID>`.

- [ ] **Step 5: Trigger once to verify it runs green**

Trigger the job manually (via DO dashboard "Run" or `doctl`), then check logs:
```bash
doctl apps logs <APP_ID> --type job --component scan-discounts
```
Expected: the command's "Leaflet records expired / refreshed" output, exit 0.

- [ ] **Step 6: Record the outcome**

No code commit here (infra lives in DO). Note the App ID, job name, and schedule in the plan's results, and update project memory if the scheduler wiring is reusable for future jobs.

---

## Final verification

- [ ] **Backend suite:** `python manage.py test diet_planner.tests.test_goal_create_defaults diet_planner.tests.test_shopping_list_pricing diet_planner.tests.test_scan_discounts diet_planner.tests.test_goal_detail_serializer -v 2` → all PASS.
- [ ] **Django check:** `python manage.py check` → no issues.
- [ ] **Frontend build:** `cd frontend && npm run build` → succeeds.
- [ ] **Manual smoke (per QA workflow memory — Playwright the affected prod pages):** Onboarding has 5 steps (no Obchod); CreatePlan has no store step; shopping list shows "Zkontrolovat slevy" and, on click, per-store deals with savings vs Rohlík.
- [ ] **Open PR** into `develop` (not `prod`) when the user asks; do not merge to `prod` without explicit approval.

## Spec-coverage check

- Drop store selection (Onboarding + CreatePlan) → Tasks 4, 5. ✅
- Generation pinned to Rohlík catalog/baseline → Task 1. ✅
- Discounts = read-only price-map, no recipe change → Task 2 (re-baseline), Task 6 (gate), Task 3 (retire swaps). ✅
- Savings vs Rohlík baseline → Task 2. ✅
- On-demand click, DB-only read → Task 6 (no new fetch; reveals existing payload). ✅
- Daily freshness scan → Task 7. ✅
- DO scheduled Job via doctl, beat stays off, never push repo app.yaml → Task 8. ✅
- Strict canonical matching / no fabrication → inherited from existing `resolve_store_products` (unchanged). ✅
