import { api } from '@/lib/api';

/** One chat turn. Assistant entries carry the transcript text the LLM sees
 * (suggestion + question), so the backend gets the full conversation. */
export interface ChatMessage {
  role: 'user' | 'assistant';
  text: string;
}

/** Card-sized candidate preview returned by a preview turn. */
export interface RefineCandidate {
  curated_recipe_id: number;
  name: string;
  description: string;
  food_category: string;
  preparation_time: number | null;
  calories: number | null;
  why: string | null;
}

export interface RefinePreviewResult {
  candidate: RefineCandidate | null;
  question: string | null;
  hint_matched: boolean | null;
  reason?: string;
  /** v2 agent fields — present iff REFINE_CHAT_AGENT_ENABLED on the backend. */
  reply_text?: string | null;
  research_job_id?: number | null;
}

export type ResearchJobStatus = 'queued' | 'searching' | 'curating' | 'ready' | 'failed';

export interface ResearchStatusResult {
  status: ResearchJobStatus;
  reply_text: string | null;
  candidate: RefineCandidate | null;
}

export interface RefineAcceptResult {
  replaced: boolean;
  recipe?: Record<string, unknown>;
}

/** Preview turn: send the whole conversation; nothing is written server-side. */
export async function refinePreview(
  mealId: string,
  messages: ChatMessage[],
  rejectedIds: number[],
): Promise<RefinePreviewResult> {
  const res = await api.post(`/recipes/${mealId}/refine/`, {
    messages,
    rejected_ids: rejectedIds,
  });
  return res.data.data as RefinePreviewResult;
}

/** Poll one web-research job (v2). Owner-only on the backend. */
export async function researchStatus(jobId: number): Promise<ResearchStatusResult> {
  const res = await api.get(`/recipes/research/${jobId}/`);
  return res.data.data as ResearchStatusResult;
}

/** Accept turn: commit the previewed candidate into the plan slot. */
export async function refineAccept(mealId: string, recipeId: number): Promise<RefineAcceptResult> {
  const res = await api.post(`/recipes/${mealId}/refine/`, { accept: recipeId });
  return res.data.data as RefineAcceptResult;
}
