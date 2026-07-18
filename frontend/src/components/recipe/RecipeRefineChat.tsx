import { useState } from 'react';
import { Clock, Flame, Loader2, Send } from 'lucide-react';
import { getFoodImageUrl } from '@/lib/food-image';
import { useToast } from '@/components/ui/Toast';
import {
  refineAccept,
  refinePreview,
  type ChatMessage,
  type RefineCandidate,
} from '@/lib/refineRecipe';

const MAX_USER_MESSAGES = 8;

interface RecipeRefineChatProps {
  mealId: string;
  /** Called with the swapped-in recipe (RecipeDetail shape) after a committed accept. */
  onAccepted: (recipe: Record<string, unknown>) => void;
  onClose: () => void;
}

/** Assistant transcript line: also what the backend LLM sees on later turns. */
const assistantText = (c: RefineCandidate, question: string | null, matched: boolean | null) => {
  const intro = matched === false
    ? `Přesně podle vašeho přání jsme nic nenašli, ale co třeba: ${c.name}?`
    : `Co třeba: ${c.name}?`;
  return question ? `${intro} ${question}` : intro;
};

export const RecipeRefineChat = ({ mealId, onAccepted, onClose }: RecipeRefineChatProps) => {
  const toast = useToast();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [candidate, setCandidate] = useState<RefineCandidate | null>(null);
  const [rejectedIds, setRejectedIds] = useState<number[]>([]);
  const [noAlternatives, setNoAlternatives] = useState(false);
  const [input, setInput] = useState('');
  const [pending, setPending] = useState(false);

  const userCount = messages.filter((m) => m.role === 'user').length;
  const capReached = userCount >= MAX_USER_MESSAGES;

  const reset = () => {
    setMessages([]);
    setCandidate(null);
    setRejectedIds([]);
    setNoAlternatives(false);
    setInput('');
  };

  const send = async () => {
    const text = input.trim();
    if (!text || pending || capReached) return;
    // Typing a new message implicitly rejects the currently shown candidate.
    const nextRejected = candidate ? [...rejectedIds, candidate.curated_recipe_id] : rejectedIds;
    const nextMessages: ChatMessage[] = [...messages, { role: 'user', text }];
    setMessages(nextMessages);
    setRejectedIds(nextRejected);
    setCandidate(null);
    setInput('');
    setNoAlternatives(false);
    setPending(true);
    try {
      const r = await refinePreview(mealId, nextMessages, nextRejected);
      if (!r.candidate) {
        setNoAlternatives(true);
        return;
      }
      setCandidate(r.candidate);
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', text: assistantText(r.candidate!, r.question, r.hint_matched) },
      ]);
    } catch {
      // Roll back the turn so it isn't burned from the 8-message budget, and
      // put the draft back so the user can just hit send again.
      toast.error('Něco se nepovedlo, zkuste to prosím znovu.');
      setMessages(messages);
      setRejectedIds(rejectedIds);
      setCandidate(candidate);
      setInput(text);
    } finally {
      setPending(false);
    }
  };

  const accept = async () => {
    if (!candidate || pending) return;
    setPending(true);
    try {
      const r = await refineAccept(mealId, candidate.curated_recipe_id);
      if (r.replaced && r.recipe) {
        onAccepted(r.recipe);
      } else {
        toast.error('Něco se nepovedlo, zkuste to prosím znovu.');
      }
    } catch {
      toast.error('Něco se nepovedlo, zkuste to prosím znovu.');
    } finally {
      setPending(false);
    }
  };

  const imgUrl = candidate ? getFoodImageUrl(candidate.food_category, candidate.name) : '';

  return (
    <div className="rounded-2xl border border-line bg-card p-5 max-w-xl">
      <p className="text-sm font-bold text-ink mb-3">Na co máte chuť? Poradíme vám s výběrem.</p>

      {messages.length > 0 && (
        <ul className="space-y-2 mb-4">
          {messages.map((m, idx) => (
            <li
              key={idx}
              className={m.role === 'user'
                ? 'ml-8 rounded-xl bg-green-soft px-4 py-2 text-sm text-ink'
                : 'mr-8 rounded-xl bg-paper border border-line px-4 py-2 text-sm text-muted'}
            >
              {m.text}
            </li>
          ))}
        </ul>
      )}

      {candidate && (
        <div className="rounded-xl border border-green/40 bg-paper p-4 mb-4">
          {imgUrl && (
            <img src={imgUrl} alt={candidate.name} className="w-full h-32 object-cover rounded-lg mb-3" />
          )}
          <p className="font-black text-ink">{candidate.name}</p>
          {candidate.why && <p className="text-xs text-green mt-1">{candidate.why}</p>}
          <div className="flex gap-4 mt-2 text-[10px] font-black uppercase tracking-widest text-muted">
            {candidate.preparation_time != null && (
              <span className="flex items-center gap-1"><Clock size={12} className="text-green" /> {candidate.preparation_time} min</span>
            )}
            {candidate.calories != null && (
              <span className="flex items-center gap-1"><Flame size={12} className="text-green" /> {candidate.calories} kcal</span>
            )}
          </div>
          <button
            onClick={accept}
            disabled={pending}
            className="mt-4 flex items-center gap-2 px-6 h-11 bg-green text-white font-black uppercase text-[10px] tracking-widest rounded-xl disabled:opacity-60"
          >
            {pending && <Loader2 size={14} className="animate-spin" />} Použít tento recept
          </button>
        </div>
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
            onKeyDown={(e) => { if (e.key === 'Enter') send(); }}
            placeholder="Napište, na co máte chuť…"
            aria-label="Napište, na co máte chuť…"
            disabled={pending}
            className="flex-1 h-11 px-4 bg-paper border border-line rounded-xl text-sm text-ink placeholder:text-muted focus:border-green/60 focus:outline-none disabled:opacity-60"
          />
          <button
            onClick={send}
            disabled={pending}
            aria-label="Odeslat"
            className="w-11 h-11 flex items-center justify-center bg-green text-white rounded-xl disabled:opacity-60"
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
