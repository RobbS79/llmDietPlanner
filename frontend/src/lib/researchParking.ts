/**
 * Web research runs in Celery and outlives the chat panel — and the page.
 * Parking the job id is what makes the "recept se objeví tady v chatu, i když
 * se sem vrátíte později" promise true; without it, navigating away or
 * reloading orphans a job that keeps running.
 *
 * Lives outside the chat component on purpose: the recipe page has to read it
 * while the panel is CLOSED, otherwise a reload never restores anything.
 */
export interface ParkedResearch {
  jobId: number;
  startedAt: number;
}

const key = (mealId: string) => `varto.research.${mealId}`;

export const parkResearch = (mealId: string, jobId: number, startedAt: number): void => {
  try {
    localStorage.setItem(key(mealId), JSON.stringify({ jobId, startedAt }));
  } catch { /* private mode / quota — polling just won't survive a reload */ }
};

export const unparkResearch = (mealId: string): void => {
  try { localStorage.removeItem(key(mealId)); } catch { /* ignore */ }
};

export const readParkedResearch = (mealId: string): ParkedResearch | null => {
  try {
    const raw = localStorage.getItem(key(mealId));
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    return typeof parsed?.jobId === 'number' && typeof parsed?.startedAt === 'number'
      ? { jobId: parsed.jobId, startedAt: parsed.startedAt }
      : null;
  } catch { return null; }
};
