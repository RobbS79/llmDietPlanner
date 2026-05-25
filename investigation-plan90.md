# Investigation Report: Plan/Goal ID 90 - Production Failure

**Date:** 2025-05-25
**Investigator:** Claude Code (automated deep investigation)
**App:** llmDietPlanner on DigitalOcean App Platform
**App ID:** f1ffa865-7f6d-4aa0-9e74-2b37dac2f0e8

---

## Executive Summary

**Root Cause: Gemini 2.5-flash is generating JSON responses that exceed the hardcoded `max_output_tokens: 8192` limit, causing truncated/invalid JSON that fails parsing on ALL 4 attempts (1 initial + 3 retries).**

Goal 90 failed with 4 consecutive `json.decoder.JSONDecodeError` exceptions, each showing a different truncation point in the response:
1. `line 417, char 16751` - "Expecting property name enclosed in double quotes" (trailing comma at truncation)
2. `line 23, char 822` - "Unterminated string" (mid-string truncation)
3. `line 359, char 16406` - "Expecting property name" (trailing comma at truncation)
4. `line 438, char 18236` - "Expecting value" (truncation at end of JSON)

This is NOT a quota/billing issue (the API key works and returns responses). This is NOT a model-not-found issue. The model responds but its output is being cut off because 7-day meal plans with recipes consistently exceed 8192 output tokens.

---

## 1. Production Logs Analysis

### Timeline of Goal 90 Processing

| Time (UTC) | Event | Context ID |
|---|---|---|
| 23:11:50 | Task received by Celery | e8739aaa |
| 23:11:51 | Processing started, 7-day plan | dc581604 |
| 23:12:26 | **FAIL #1**: JSON parse error at char 16751 | dc581604 |
| 23:12:27 | Retry scheduled in 30s | - |
| 23:12:57 | Retry #1 started | 55b3c2fc |
| 23:13:30 | **FAIL #2**: Unterminated string at char 822 | 55b3c2fc |
| 23:13:30 | Retry scheduled in 30s | - |
| 23:14:00 | Retry #2 started | 759575d9 |
| 23:14:35 | **FAIL #3**: JSON parse error at char 16406 | 759575d9 |
| 23:14:35 | Retry scheduled in 30s | - |
| 23:15:05 | Retry #3 started | d170cad2 |
| 23:15:38 | **FAIL #4**: JSON truncated at char 18236 | d170cad2 |
| 23:15:38 | MaxRetriesExceeded - task raised | - |

### Key Log Evidence

```
ERROR diet_planner.llm_service Failed to parse meal plan JSON: 
  Expecting property name enclosed in double quotes: line 417 column 9 (char 16751)
ERROR diet_planner.tasks Task failed for goal 90: 
  Invalid JSON from meal plan generation: ...
```

All 4 failures are JSON parse errors from `generate_meal_plan_only()` - Step 1 of the 2-step process. The response is being truncated at the `max_output_tokens` limit.

### Additional Production Warnings

```
FutureWarning: All support for the `google.generativeai` package has ended. 
  Please switch to the `google.genai` package as soon as possible.
```

The deprecated `google.generativeai` SDK is still being used. While it still functions, it will stop receiving updates and may break at any time.

---

## 2. Code Flow Analysis

### Full Request Path

1. **Frontend** (`PlanView.tsx:20-24`): Polls `GET /api/goals/{id}/task-status/` every 2500ms
2. **View** (`views.py:49-144`): `DietaryGoalCreateView.post()` validates input, creates `DietaryGoal`, dispatches Celery task
3. **Task dispatch** (`views.py:124-127`): `process_dietary_goal_task.delay(dietary_goal.id)`
4. **Celery task** (`tasks.py:1373-1596`): `process_dietary_goal_task()` orchestrates:
   - Sets status to PROCESSING (`tasks.py:1394-1395`)
   - Gets shop URL (`tasks.py:1399-1405`)
   - Calls `GeminiService.generate_complete_plan_with_shopping_list()` (`tasks.py:1412-1416`)
5. **LLM Service** (`llm_service.py:536-588`): Two-step process:
   - **Step 1** (`llm_service.py:323-430`): `generate_meal_plan_only()` - **THIS IS WHERE IT FAILS**
   - **Step 2** (`llm_service.py:432-534`): `generate_shopping_list_with_prices()` - never reached

### The Truncation Problem

In `llm_service.py:391-398`:
```python
MAX_OUTPUT_TOKENS = 8192

response = gemini_model.generate_content(
    full_prompt,
    generation_config={
        "response_mime_type": "application/json",
        "temperature": 0.7,
        "max_output_tokens": MAX_OUTPUT_TOKENS,  # <-- THE PROBLEM
    },
    request_options={"timeout": 300}
)
```

A 7-day meal plan with breakfast, lunch, dinner, small_meals, and snacks generates roughly 400-450 lines of JSON (~16,000-18,000 characters). Gemini 2.5-flash produces more verbose output than 2.0-flash due to:
- More detailed ingredient descriptions
- Longer nutritional info fields
- More elaborate recipe names/descriptions in Czech language
- Instructions field (3 steps per meal) adds significant token count

**gemini-2.5-flash has a max output of 65,536 tokens** (up from 8,192 in older models). The hardcoded 8192 limit is artificially constraining it.

### Error Types Observed

The truncation manifests as different JSON errors because the cut happens at different points each time:
- **"Expecting property name"**: JSON ends with a trailing comma after a complete property (e.g., `"calories": 450,` then EOF)
- **"Unterminated string"**: JSON cuts in the middle of a string value
- **"Expecting value"**: JSON cuts after a colon (e.g., `"name":` then EOF)

---

## 3. Configuration Analysis

### Settings (`settings.py:192-193`)
```python
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', config('GEMINI_API_KEY', default=None))
GEMINI_MODEL = config('GEMINI_MODEL', default='gemini-2.5-flash')
```
- Model correctly set to `gemini-2.5-flash`
- API key is loaded (confirmed by production logs showing successful API calls that return data)

### SDK Version Issue
- **requirements.txt**: `google-generativeai>=0.3.0` (deprecated package)
- **Should be**: `google-genai` (new package)
- Production logs show FutureWarning about this on every startup

### Model Parameter Differences (2.0-flash vs 2.5-flash)

| Parameter | gemini-2.0-flash | gemini-2.5-flash | Current Code |
|---|---|---|---|
| Max output tokens | 8,192 | 65,536 | **8,192 (hardcoded)** |
| `response_mime_type` | Supported | Supported | OK |
| `system_instruction` | Supported | Supported | OK |
| Safety settings | Optional | Optional | Not set (OK) |
| Temperature | 0-2.0 | 0-2.0 | 0.7 (OK) |

The `response_mime_type: "application/json"` should guarantee valid JSON output, BUT only if the response is not truncated by `max_output_tokens`. When truncation occurs, the API returns the partial response as-is, breaking the JSON structure.

---

## 4. Error Handling Gaps

### Gap 1: `error_message` not set for non-payment failures

**File:** `tasks.py:1575-1595`

```python
except Exception as exc:
    ...
    if goal.status == DietaryGoal.StatusChoices.PAYMENT_PENDING:
        goal.status = DietaryGoal.StatusChoices.REFUND_ELIGIBLE
        goal.error_message = f"Meal plan generation failed: {str(exc)}"  # <-- ONLY set here
    else:
        goal.status = DietaryGoal.StatusChoices.FAILED
        # ERROR_MESSAGE IS NOT SET for non-payment goals!
    goal.save(update_fields=['status', 'error_message'])
```

For free-tier goals or goals not in PAYMENT_PENDING status, `error_message` is never set, so the user sees a generic "Generation Failed" with no useful diagnostic info.

### Gap 2: `error_message` not exposed in API serializers

**File:** `serializers.py`

Neither `DietaryGoalSerializer` nor `DietaryGoalDetailSerializer` includes `error_message` in their `fields` list. Even if the error_message were set, the frontend would never receive it.

### Gap 3: Retry on deterministic failures

**File:** `tasks.py:1594-1595`

```python
raise self.retry(exc=exc, countdown=30)
```

The task retries on ALL exceptions with a flat 30s delay. For `max_output_tokens` truncation, retrying is unlikely to help since the same prompt generates a similar-length response each time. All 4 attempts failed the same way.

The retry delay is also not exponential despite the comment saying "exponential backoff" - it's a flat 30 seconds every time.

### Gap 4: JSON repair only handles trailing commas

**File:** `llm_service.py:412-417`

```python
cleaned = re.sub(r',\s*}', '}', content)
cleaned = re.sub(r',\s*]', ']', cleaned)
parsed_response = json.loads(cleaned)
```

The JSON repair logic only fixes trailing commas. It does NOT handle:
- Unterminated strings (truncation mid-string)
- Missing closing braces/brackets (truncation at any depth)
- Truncated values

### Gap 5: Bare `except` in error handler

**File:** `tasks.py:1591-1592`

```python
except Exception:
    pass
```

If the goal status update fails (e.g., database connection lost), the error is silently swallowed. The goal remains stuck in PROCESSING status forever.

### Gap 6: Deprecated SDK warning not actionable

The `google.generativeai` package is fully deprecated. While it currently works, `response_mime_type` behavior may differ between the old and new SDK, especially for gemini-2.5-flash which was designed for the new `google.genai` package.

---

## 5. Frontend Error Display

### PlanView.tsx (lines 20-43)

```tsx
const { data: statusData } = useQuery({
    queryKey: ['taskStatus', id],
    queryFn: () => api.get(`/goals/${id}/task-status/`).then(res => res.data.data),
    refetchInterval: (query) =>
      query?.state?.data?.goal_status === 'completed' || 
      query?.state?.data?.goal_status === 'failed' ? false : 2500,
});

if (statusData?.goal_status === 'failed') {
    return (
        // Shows "Generation Failed." and 
        // "We couldn't generate your meal plan. Please try again with different parameters."
    );
}
```

- Frontend polls every 2.5 seconds via `GET /api/goals/{id}/task-status/`
- Stops polling when status is `completed` or `failed`
- Shows a **generic error message** with no details about what went wrong
- Does NOT display `error_message` from the backend (and it's not in the API response anyway)
- The "try again with different parameters" advice is misleading - the issue is a code bug, not bad parameters

---

## 6. Root Cause Analysis

### Primary Root Cause

**The `max_output_tokens: 8192` hardcoded limit in `llm_service.py:391` is too low for gemini-2.5-flash to generate a complete 7-day meal plan JSON.**

When the model was gemini-2.0-flash, 8192 tokens was the model's maximum, so setting it explicitly didn't help but also didn't hurt (the model would have capped there anyway). With gemini-2.5-flash, the model can generate up to 65,536 tokens, but the hardcoded limit prevents it from completing the JSON response.

### Contributing Factors

1. **Verbose prompts generate verbose outputs**: The system prompt asks for instructions (3 steps per meal), nutritional info, and detailed ingredient objects for 7 days x 6 meal slots = 42 meals
2. **Czech language adds token overhead**: Czech diacritics and longer word forms consume more tokens than English
3. **No response completion detection**: The code doesn't check `response.candidates[0].finish_reason` - if it's `MAX_TOKENS` instead of `STOP`, the response is known to be truncated
4. **Retries don't change anything**: Same prompt, same token limit = same truncation on every retry

### Why It Worked Before (with gemini-2.0-flash)

It likely worked inconsistently. With 2.0-flash:
- The model had an inherent 8192 token limit, so the explicit cap was redundant
- The model may have produced less verbose output, fitting within the limit
- Shorter plans or fewer days may have worked while 7-day plans sometimes failed

---

## 7. Recommended Fixes

### Fix 1: CRITICAL - Increase max_output_tokens (immediate fix)

**File:** `diet_planner/llm_service.py:391` and `llm_service.py:497`

```python
# Change from:
MAX_OUTPUT_TOKENS = 8192

# Change to:
MAX_OUTPUT_TOKENS = 65536  # gemini-2.5-flash supports up to 65,536
```

Or better, make it configurable via settings:

```python
MAX_OUTPUT_TOKENS = getattr(settings, 'GEMINI_MAX_OUTPUT_TOKENS', 65536)
```

### Fix 2: HIGH - Add truncation detection

**File:** `diet_planner/llm_service.py`, in `generate_meal_plan_only()` after getting the response:

```python
# Check if response was truncated
if hasattr(response, 'candidates') and response.candidates:
    finish_reason = response.candidates[0].finish_reason
    if finish_reason == 'MAX_TOKENS':
        logger.error(f"Response truncated at max_output_tokens ({MAX_OUTPUT_TOKENS})")
        raise ValueError(f"Response truncated: output exceeded {MAX_OUTPUT_TOKENS} tokens")
```

### Fix 3: HIGH - Set error_message for all failures

**File:** `diet_planner/tasks.py:1575-1592`

```python
except Exception as exc:
    logger.error(f"Task failed for goal {goal_id}: {str(exc)}", exc_info=True)
    try:
        goal = DietaryGoal.objects.get(id=goal_id)
        goal.error_message = f"Meal plan generation failed: {str(exc)}"  # Always set
        if goal.status == DietaryGoal.StatusChoices.PAYMENT_PENDING:
            goal.status = DietaryGoal.StatusChoices.REFUND_ELIGIBLE
        else:
            goal.status = DietaryGoal.StatusChoices.FAILED
        goal.save(update_fields=['status', 'error_message'])
    except Exception as inner_exc:
        logger.error(f"Failed to update goal {goal_id} status: {inner_exc}")
```

### Fix 4: MEDIUM - Expose error_message in API

Add `error_message` to `DietaryGoalSerializer` and `DietaryGoalDetailSerializer` fields lists so the frontend can display specific error information.

### Fix 5: MEDIUM - Better JSON repair

Implement more robust JSON repair for truncated responses:
- Detect and close unclosed strings
- Count and close missing brackets/braces
- Use a streaming JSON parser that can extract partial data

### Fix 6: MEDIUM - Exponential backoff (not flat retry)

```python
raise self.retry(exc=exc, countdown=30 * (2 ** self.request.retries))
```

### Fix 7: LOW - Migrate to google.genai SDK

Replace `google-generativeai` with `google-genai` in requirements.txt and update imports:
```python
# Old (deprecated):
import google.generativeai as genai

# New:
from google import genai
```

### Fix 8: LOW - Don't retry on deterministic errors

If the error is JSON truncation due to max_output_tokens, increase the limit and retry. Don't retry with the same parameters.

---

## 8. Quick Fix (Deploy within minutes)

Change ONE line in `diet_planner/llm_service.py`:

- **Line 391**: Change `MAX_OUTPUT_TOKENS = 8192` to `MAX_OUTPUT_TOKENS = 65536`
- **Line 497**: Change `MAX_OUTPUT_TOKENS = 8192` to `MAX_OUTPUT_TOKENS = 65536`

Then redeploy. This should resolve the immediate issue for goal 90 and prevent it from recurring.

---

## File References

| File | Lines | What |
|---|---|---|
| `diet_planner/llm_service.py` | 391, 497 | Hardcoded MAX_OUTPUT_TOKENS = 8192 (ROOT CAUSE) |
| `diet_planner/llm_service.py` | 389-426 | generate_meal_plan_only() - where truncated JSON fails parsing |
| `diet_planner/llm_service.py` | 407-417 | Insufficient JSON repair (trailing commas only) |
| `diet_planner/tasks.py` | 1373-1596 | process_dietary_goal_task - main Celery task |
| `diet_planner/tasks.py` | 1575-1595 | Error handler - doesn't set error_message for non-payment goals |
| `diet_planner/tasks.py` | 1591-1592 | Bare except: pass swallows DB errors |
| `diet_planner/models.py` | 130-141 | StatusChoices enum |
| `diet_planner/models.py` | 212-216 | error_message field |
| `diet_planner/serializers.py` | 9-39 | DietaryGoalSerializer - missing error_message field |
| `diet_planner/views.py` | 184-211 | DietaryGoalTaskStatusView - polling endpoint |
| `frontend/src/pages/PlanView.tsx` | 20-43 | Frontend polling and generic error display |
| `llm_diet_planner_project/settings.py` | 192-193 | GEMINI config |
| `requirements.txt` | 29 | Deprecated google-generativeai package |
