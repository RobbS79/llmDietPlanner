// Two questions instead of country, city and five steppers (spec 2026-11-03).
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '@/lib/api';
import { isAccessTokenValid } from '@/lib/auth';
import { readBasket } from '@/lib/basket';
import { trackPlanStarted } from '@/lib/analytics';
import { COUNT_OPTIONS, GOALS, countsFor, goalPrompt } from '@/lib/planSheet';
import { SignupSheet } from '@/components/auth/SignupSheet';

type Props = { understood: string[]; prompt: string; onClose: () => void };

export function PlanSheet({ understood, prompt, onClose }: Props) {
  const navigate = useNavigate();
  const [goal, setGoal] = useState<string | null>(null);
  const [count, setCount] = useState<string>('5 večeří');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [needSignup, setNeedSignup] = useState(false);
  const signedIn = isAccessTokenValid() || !!localStorage.getItem('refresh_token');

  const build = async () => {
    const counts = countsFor(count);
    const text = goalPrompt(goal, prompt);
    if (!counts) { navigate(`/create?prompt=${encodeURIComponent(text)}`); return; }
    if (!signedIn) { setNeedSignup(true); return; }
    setBusy(true);
    setError('');
    trackPlanStarted();
    try {
      const res = await api.post('/goals/', { prompt: text, ...counts, pinned_recipe_ids: readBasket().recipeIds });
      navigate(`/plan/${res.data.data.goal_id}`);
    } catch (e) {
      // e.g. 403 EMAIL_NOT_VERIFIED carries a Czech `error` text; 402 is redirected by the api interceptor.
      const msg = (e as { response?: { data?: { error?: string } } }).response?.data?.error;
      // EN: Couldn't build the plan. Please try again.
      setError(msg || 'Plán se nepodařilo sestavit. Zkus to prosím znovu.');
    } finally { setBusy(false); }
  };

  if (needSignup) return <SignupSheet thumbs={[]} onClose={onClose} />;
  const chip = (value: string, on: boolean, set: () => void) => (
    <button key={value} type="button" aria-pressed={on} onClick={set}
      className={`rounded-xl border px-3.5 py-2.5 ${on ? 'border-2 border-green bg-green/10 font-semibold' : 'border-kraft bg-white'}`}>{value}</button>
  );
  return (
    <div role="dialog" aria-modal="true" aria-labelledby="plan-h" className="fixed inset-0 z-50 flex items-end justify-center bg-ink/50 sm:items-center"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="flex w-full max-w-[600px] flex-col gap-4 rounded-t-3xl bg-paper p-6 sm:rounded-3xl">
        {/* EN: Plan for the whole week */}
        <h2 id="plan-h" className="font-display text-3xl font-bold">Plán na celý týden</h2>
        {/* EN: Your picked meals stay in the plan. */}
        {readBasket().recipeIds.length > 0 && <p>Tvoje vybraná jídla v plánu zůstanou.</p>}
        {/* EN: What are you after? */}
        <p className="font-display text-lg font-bold">O co ti jde?</p>
        <div className="flex flex-wrap gap-2">{GOALS.map((g) => chip(g, goal === g, () => setGoal(goal === g ? null : g)))}</div>
        {/* EN: How many meals do you want prepared? */}
        <p className="font-display text-lg font-bold">Kolik jídel chceš mít připravených?</p>
        <div className="flex flex-wrap gap-2">{COUNT_OPTIONS.map((c) => chip(c, count === c, () => setCount(c)))}</div>
        {/* EN: From your search we take: ... */}
        {understood.length > 0 && <p className="text-sm text-muted">Z hledání si bereme: {understood.join(', ')}</p>}
        {error && <p role="alert" className="text-sm font-semibold text-paprika">{error}</p>}
        {/* EN: Build my plan */}
        <button type="button" disabled={busy} onClick={build} className="w-full rounded-xl bg-green p-3.5 text-[17px] font-bold text-white disabled:opacity-60">
          Sestavit můj plán</button>
        {/* EN: Collection recipes are instant. What we don't have, Uvařto writes, which takes a few minutes. Uses 1 of your 2 free plans. */}
        <p className="text-xs text-muted">Recepty ze sbírky jsou hned. Co ve sbírce nemáme, Uvařto dopíše, to trvá pár minut. Spotřebuje se 1 ze 2 plánů zdarma.</p>
      </div>
    </div>
  );
}
