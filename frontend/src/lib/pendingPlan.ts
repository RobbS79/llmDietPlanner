// The plan-sheet answers of a visitor who pressed "Sestavit můj plán" signed out.
// After signup the sheet builds straight from them instead of asking again.
// Same freshness rule as the return intent: older than 15 minutes is ignored.
import { PENDING_PLAN_KEY } from './storageKeys';
import { RETURN_MAX_AGE_MS } from './returnIntent';

export type PendingPlan = { goal: string | null; count: string; prompt: string; pinned: number[] };

export function savePendingPlan(p: PendingPlan): void {
  try { localStorage.setItem(PENDING_PLAN_KEY, JSON.stringify({ ...p, ts: Date.now() })); } catch { /* private mode */ }
}

/** Read and remove; null unless fresh and well-formed. */
export function takePendingPlan(): PendingPlan | null {
  let raw: string | null = null;
  try { raw = localStorage.getItem(PENDING_PLAN_KEY); localStorage.removeItem(PENDING_PLAN_KEY); } catch { return null; }
  try {
    const v = JSON.parse(raw || 'null');
    const age = Date.now() - (v?.ts ?? NaN);
    if (!(age >= 0 && age < RETURN_MAX_AGE_MS)) return null;
    if (typeof v.count !== 'string' || typeof v.prompt !== 'string') return null;
    if (v.goal !== null && typeof v.goal !== 'string') return null;
    if (!Array.isArray(v.pinned) || !v.pinned.every((n: unknown) => Number.isInteger(n))) return null;
    return { goal: v.goal, count: v.count, prompt: v.prompt, pinned: v.pinned };
  } catch { return null; }
}
