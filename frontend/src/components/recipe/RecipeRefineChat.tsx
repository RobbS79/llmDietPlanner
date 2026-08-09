import { useEffect, useRef, useState } from 'react';
import { ChevronRight, Clock, Flame, Loader2, MessageCircle, Send } from 'lucide-react';
import { getFoodImageUrl } from '@/lib/food-image';
import { useToast } from '@/components/ui/Toast';
import {
  refineAccept,
  refinePreview,
  researchStatus,
  type ChatMessage,
  type RefineCandidate,
  type ResearchJobStatus,
} from '@/lib/refineRecipe';
import { ResearchProgress } from './ResearchProgress';

const MAX_USER_MESSAGES = 8;

/** Web research runs in Celery and outlives this component. Parking the job id
 * makes the "recept se objeví tady, i když se sem vrátíte později" promise
 * true — before this, navigating away silently orphaned the job. */
const researchKey = (mealId: string) => `varto.research.${mealId}`;

const parkResearch = (mealId: string, jobId: number, startedAt: number) => {
  try {
    localStorage.setItem(researchKey(mealId), JSON.stringify({ jobId, startedAt }));
  } catch { /* private mode / quota — polling just won't survive a reload */ }
};

const unparkResearch = (mealId: string) => {
  try { localStorage.removeItem(researchKey(mealId)); } catch { /* ignore */ }
};

const readParkedResearch = (mealId: string): { jobId: number; startedAt: number } | null => {
  try {
    const raw = localStorage.getItem(researchKey(mealId));
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    return typeof parsed?.jobId === 'number' && typeof parsed?.startedAt === 'number'
      ? parsed : null;
  } catch { return null; }
};

// One-tap starters for the empty chat — the fastest way to teach that this is
// a conversation about the current meal, not a form field.
const QUICK_PROMPTS = ['Něco bez masa', 'Něco rychlejšího', 'Něco lehčího'];

/** Local transcript entry: assistant turns keep their suggestion attached so a
 * past suggestion can be re-expanded by clicking its line. Never sent to the
 * backend — the preview payload is mapped down to `{role, text}`. */
interface LocalMessage extends ChatMessage {
  candidate?: RefineCandidate;
}

interface RecipeRefineChatProps {
  mealId: string;
  /** Called with the swapped-in recipe (RecipeDetail shape) after a committed
   * accept, plus the replaced recipe so the page can offer an undo. */
  onAccepted: (
    recipe: Record<string, unknown>,
    previous?: { curated_recipe_id: number; name: string } | null,
  ) => void;
  onClose: () => void;
  /** Sent as the first message on mount — the invite card's intent chips open
   * the panel straight into a conversation instead of an empty prompt. */
  seedMessage?: string;
  /** Whether the backend agent can actually search the web (v2 flag). The intro
   * only offers it when true — a promise the v1 path cannot keep is worse than
   * saying nothing. */
  webResearch?: boolean;
}

/** Assistant transcript line: also what the backend LLM sees on later turns. */
const assistantText = (c: RefineCandidate, question: string | null, matched: boolean | null) => {
  const intro = matched === false
    ? `Přesně podle vašeho přání jsme nic nenašli, ale co třeba: ${c.name}?`
    : `Co třeba: ${c.name}?`;
  return question ? `${intro} ${question}` : intro;
};

export const RecipeRefineChat = ({
  mealId, onAccepted, onClose, seedMessage, webResearch = false,
}: RecipeRefineChatProps) => {
  const toast = useToast();
  const [messages, setMessages] = useState<LocalMessage[]>([]);
  const [candidate, setCandidate] = useState<RefineCandidate | null>(null);
  const [alternatives, setAlternatives] = useState<RefineCandidate[]>([]);
  const [rejectedIds, setRejectedIds] = useState<number[]>([]);
  const [noAlternatives, setNoAlternatives] = useState(false);
  const [input, setInput] = useState('');
  const [pending, setPending] = useState(false);
  const [researchJobId, setResearchJobId] = useState<number | null>(null);
  const [researching, setResearching] = useState(false);
  const [researchStage, setResearchStage] = useState<ResearchJobStatus>('queued');
  const [researchStartedAt, setResearchStartedAt] = useState(0);
  const headingRef = useRef<HTMLParagraphElement>(null);

  const userCount = messages.filter((m) => m.role === 'user').length;
  const capReached = userCount >= MAX_USER_MESSAGES;
  /** Every card currently on offer — the model's pick first, runners-up after. */
  const offered = candidate ? [candidate, ...alternatives] : [];

  const reset = () => {
    setMessages([]);
    setCandidate(null);
    setAlternatives([]);
    setRejectedIds([]);
    setNoAlternatives(false);
    setInput('');
    setResearchJobId(null);
    setResearching(false);
  };

  const send = async (rawText?: string) => {
    const text = (rawText ?? input).trim();
    if (!text || pending || capReached) return;
    // Typing a new message implicitly rejects everything currently on offer —
    // not just the first card, or the runners-up the user just scrolled past
    // would come straight back. A re-expanded candidate may already be in the
    // list, so dedupe.
    const nextRejected = [...rejectedIds];
    for (const c of offered) {
      if (!nextRejected.includes(c.curated_recipe_id)) nextRejected.push(c.curated_recipe_id);
    }
    const nextMessages: LocalMessage[] = [...messages, { role: 'user', text }];
    setMessages(nextMessages);
    setRejectedIds(nextRejected);
    setCandidate(null);
    setAlternatives([]);
    setInput('');
    setNoAlternatives(false);
    setPending(true);
    try {
      // Map down to the wire shape — attached card data never leaves the client.
      const wireMessages: ChatMessage[] = nextMessages.map(({ role, text }) => ({ role, text }));
      const r = await refinePreview(mealId, wireMessages, nextRejected);
      if (r.reply_text != null) {
        // v2 agent turn: LLM-authored reply; candidate/research are optional.
        setCandidate(r.candidate ?? null);
        setAlternatives(r.candidate ? (r.alternatives ?? []) : []);
        setMessages((prev) => [
          ...prev,
          { role: 'assistant', text: r.reply_text!, candidate: r.candidate ?? undefined },
        ]);
        if (r.research_job_id != null) {
          const startedAt = Date.now();
          parkResearch(mealId, r.research_job_id, startedAt);
          setResearchStartedAt(startedAt);
          setResearchStage('queued');
          setResearchJobId(r.research_job_id);
          setResearching(true);
        }
      } else if (!r.candidate) {
        setNoAlternatives(true);
      } else {
        setCandidate(r.candidate);
        setMessages((prev) => [
          ...prev,
          {
            role: 'assistant',
            text: assistantText(r.candidate!, r.question, r.hint_matched),
            candidate: r.candidate!,
          },
        ]);
      }
    } catch {
      // Roll back the turn so it isn't burned from the 8-message budget, and
      // put the draft back so the user can just hit send again.
      toast.error('Něco se nepovedlo, zkuste to prosím znovu.');
      setMessages(messages);
      setRejectedIds(rejectedIds);
      setCandidate(candidate);
      setAlternatives(alternatives);
      setInput(text);
    } finally {
      setPending(false);
    }
  };

  // Opening the panel moves focus to its heading — not the input, which would
  // silently skip the intro line and the starter chips for a screen reader.
  useEffect(() => { headingRef.current?.focus(); }, []);

  const seeded = useRef(false);
  useEffect(() => {
    if (!seedMessage || seeded.current) return;
    seeded.current = true;
    void send(seedMessage);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [seedMessage]);

  useEffect(() => {
    if (researchJobId == null) return;
    // Tight early, relaxed later: the first stage transitions happen fast, the
    // tail is mostly waiting on one page fetch + one curation call.
    const pollDelay = (elapsed: number) => (elapsed < 30_000 ? 3_000 : 8_000);
    const TIMEOUT_MS = 10 * 60_000;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;

    const tick = async () => {
      if (cancelled) return;
      const elapsed = Date.now() - researchStartedAt;
      if (elapsed > TIMEOUT_MS) {
        // The Celery job keeps running and the parked id survives, so coming
        // back later really does surface the result — say only that.
        setResearching(false);
        setResearchJobId(null);
        setMessages((prev) => [...prev, {
          role: 'assistant',
          text: 'Hledání se protáhlo. Nechávám ho běžet na pozadí — až se sem vrátíte, ukážu vám výsledek.',
        }]);
        return;
      }
      try {
        const s = await researchStatus(researchJobId);
        if (cancelled) return;
        if (s.status !== 'ready' && s.status !== 'failed') {
          setResearchStage(s.status);
        } else {
          setResearching(false);
          setResearchJobId(null);
          unparkResearch(mealId);
          if (s.status === 'ready' && s.candidate) {
            setCandidate(s.candidate);
            setAlternatives([]);
            setMessages((prev) => [...prev, {
              role: 'assistant',
              text: s.reply_text ?? `Co třeba: ${s.candidate!.name}?`,
              candidate: s.candidate!,
            }]);
          } else {
            setMessages((prev) => [...prev, {
              role: 'assistant',
              text: s.reply_text ?? 'Recept se nepodařilo najít, zkuste to prosím jinak.',
            }]);
          }
          return;
        }
      } catch {
        /* transient poll error — keep polling until timeout */
      }
      if (!cancelled) timer = setTimeout(tick, pollDelay(Date.now() - researchStartedAt));
    };

    timer = setTimeout(tick, pollDelay(Date.now() - researchStartedAt));
    return () => { cancelled = true; clearTimeout(timer); };
  }, [researchJobId, researchStartedAt, mealId]);

  // Resume a job this page started earlier: the search outlives the component,
  // so a reload or a trip back to the plan must not orphan it.
  useEffect(() => {
    const parked = readParkedResearch(mealId);
    if (!parked) return;
    setResearchStartedAt(parked.startedAt);
    setResearchStage('queued');
    setResearchJobId(parked.jobId);
    setResearching(true);
    setMessages((prev) => prev.length ? prev : [{
      role: 'assistant',
      text: 'Pokračuju v hledání receptu na webu — počkejte chviličku.',
    }]);
  }, [mealId]);

  const cancelResearch = () => {
    setResearching(false);
    setResearchJobId(null);
    unparkResearch(mealId);
    setMessages((prev) => [...prev, {
      role: 'assistant',
      // The Celery job isn't killed — don't claim it was.
      text: 'Hledání jsem přestala sledovat. Můžeme zkusit něco jiného.',
    }]);
  };

  const accept = async (chosen: RefineCandidate) => {
    if (pending) return;
    setPending(true);
    try {
      const r = await refineAccept(mealId, chosen.curated_recipe_id);
      if (r.replaced && r.recipe) {
        onAccepted(r.recipe, r.previous);
      } else {
        toast.error('Něco se nepovedlo, zkuste to prosím znovu.');
      }
    } catch {
      toast.error('Něco se nepovedlo, zkuste to prosím znovu.');
    } finally {
      setPending(false);
    }
  };

  return (
    <div className="rounded-2xl border border-line bg-card p-5 sm:p-6 max-w-2xl">
      <p
        ref={headingRef}
        tabIndex={-1}
        className="flex items-center gap-2 text-sm font-bold text-ink mb-3 focus:outline-none"
      >
        <MessageCircle size={16} className="text-green" /> Chat s naší kuchařkou
      </p>

      {messages.length === 0 && (
        <>
          <div className="mr-8 rounded-xl bg-paper border border-line px-4 py-3 text-sm text-muted mb-3">
            Řekněte mi, co vám na tomhle jídle nevyhovuje, na co máte chuť, nebo
            co máte doma v lednici.
            {webResearch && ' Když nic z naší sbírky receptů nesedne, zkusím najít nový recept na webu.'}
          </div>
          <div className="flex flex-wrap gap-2 mb-4">
            {QUICK_PROMPTS.map((prompt) => (
              <button
                key={prompt}
                type="button"
                onClick={() => send(prompt)}
                disabled={pending}
                className="h-10 px-4 rounded-full border border-line bg-paper text-sm font-semibold text-ink hover:border-green/60 hover:text-green focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-green/50 disabled:opacity-60 transition-colors"
              >
                {prompt}
              </button>
            ))}
          </div>
        </>
      )}

      {messages.length > 0 && (
        // Single live region for conversational text. The candidate cards sit
        // OUTSIDE it — announcing a whole card on every turn is noise, and the
        // assistant bubble already names the dish.
        <ul role="log" aria-live="polite" aria-relevant="additions" className="space-y-2 mb-4">
          {messages.map((m, idx) => {
            const pastSuggestion = m.candidate != null
              && m.candidate.curated_recipe_id !== candidate?.curated_recipe_id;
            if (pastSuggestion) {
              return (
                <li key={idx} className="mr-8">
                  <button
                    type="button"
                    onClick={() => setCandidate(m.candidate!)}
                    disabled={pending}
                    aria-label="Zobrazit tento návrh"
                    className="w-full flex items-center justify-between gap-2 text-left rounded-xl bg-paper border border-line px-4 py-2 text-sm text-muted hover:border-green/60 hover:text-ink disabled:opacity-60"
                  >
                    <span>{m.text}</span>
                    <ChevronRight size={14} className="shrink-0 text-green" />
                  </button>
                </li>
              );
            }
            return (
              <li
                key={idx}
                className={m.role === 'user'
                  ? 'ml-8 rounded-xl bg-green-soft px-4 py-2 text-sm text-ink'
                  : 'mr-8 rounded-xl bg-paper border border-line px-4 py-2 text-sm text-muted'}
              >
                {m.text}
              </li>
            );
          })}
        </ul>
      )}

      {researching && (
        <ResearchProgress
          status={researchStage}
          startedAt={researchStartedAt}
          onCancel={cancelResearch}
        />
      )}

      {offered.length > 0 && (
        <section
          aria-label={offered.length > 1 ? 'Vyberte, co vám sedí nejvíc' : 'Návrh pro vás'}
          className="mb-4"
        >
          <p className="mb-2 text-[10px] font-black uppercase tracking-widest text-muted">
            {offered.length > 1 ? 'Vyberte, co vám sedí nejvíc' : 'Návrh pro vás'}
          </p>
          <div className={offered.length > 1 ? 'grid gap-3 sm:grid-cols-2' : ''}>
            {offered.map((c) => {
              const imgUrl = getFoodImageUrl(c.food_category, c.name);
              return (
                <article
                  key={c.curated_recipe_id}
                  className="flex flex-col rounded-xl border border-green/40 bg-paper p-4"
                >
                  {imgUrl && (
                    <img src={imgUrl} alt={c.name} className="w-full h-32 object-cover rounded-lg mb-3" />
                  )}
                  <div className="flex-1">
                    <p className="font-black text-ink">{c.name}</p>
                    {c.why && <p className="text-xs text-green mt-1">{c.why}</p>}
                    <div className="flex gap-4 mt-2 text-[10px] font-black uppercase tracking-widest text-muted">
                      {c.preparation_time != null && (
                        <span className="flex items-center gap-1"><Clock size={12} className="text-green" /> {c.preparation_time} min</span>
                      )}
                      {c.calories != null && (
                        <span className="flex items-center gap-1"><Flame size={12} className="text-green" /> {c.calories} kcal</span>
                      )}
                    </div>
                  </div>
                  <button
                    onClick={() => accept(c)}
                    disabled={pending}
                    // Only disambiguate by dish when there IS a choice — with a
                    // single card the visible label is already unambiguous.
                    aria-label={offered.length > 1 ? `Použít recept ${c.name}` : undefined}
                    className="mt-4 flex items-center justify-center gap-2 px-6 h-11 bg-green text-white font-black uppercase text-[10px] tracking-widest rounded-xl disabled:opacity-60"
                  >
                    {pending && <Loader2 size={14} className="animate-spin" />} Použít tento recept
                  </button>
                </article>
              );
            })}
          </div>
          {!capReached && (
            <button
              type="button"
              onClick={() => void send('Ukažte mi něco jiného')}
              disabled={pending}
              className="mt-3 text-xs font-semibold text-muted hover:text-green underline underline-offset-2 disabled:opacity-60"
            >
              Ukázat jiné návrhy
            </button>
          )}
        </section>
      )}

      {noAlternatives && (
        <p className="mb-4 text-sm font-medium text-paprika-strong">
          Pro tento typ jídla už nemáme další alternativu.
        </p>
      )}

      {capReached && (
        <p className="mb-4 text-sm font-medium text-muted">
          To je pro dnešek vše — vyberte si recept, nebo začněte znovu.
        </p>
      )}

      {!capReached && !noAlternatives && (
        <div className="flex gap-2">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') void send(); }}
            placeholder="Napište, na co máte chuť…"
            aria-label="Napište, na co máte chuť…"
            maxLength={500}
            disabled={pending}
            className="flex-1 h-11 px-4 bg-paper border border-line rounded-xl text-sm text-ink placeholder:text-muted focus:border-green/60 focus:outline-none disabled:opacity-60"
          />
          <button
            onClick={() => send()}
            disabled={pending}
            aria-label="Odeslat"
            className="w-11 h-11 flex items-center justify-center bg-green text-white rounded-xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-green/50 focus-visible:ring-offset-2 disabled:opacity-60"
          >
            {pending ? <Loader2 size={16} className="animate-spin" /> : <Send size={16} />}
          </button>
        </div>
      )}

      <div className="mt-4 flex gap-3">
        {(capReached || noAlternatives) && (
          <button
            onClick={reset}
            disabled={pending}
            className="px-6 h-11 bg-card border border-line text-ink font-black uppercase text-[10px] tracking-widest rounded-xl disabled:opacity-60"
          >
            Začít znovu
          </button>
        )}
        <button
          onClick={onClose}
          disabled={pending}
          className="px-6 h-11 text-muted hover:text-ink font-black uppercase text-[10px] tracking-widest rounded-xl disabled:opacity-60"
        >
          Zavřít
        </button>
      </div>
    </div>
  );
};
