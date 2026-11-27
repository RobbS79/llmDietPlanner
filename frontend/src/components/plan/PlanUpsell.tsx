// A quiet line under a finished plan for free users: how many free plans are
// left and what Standard adds. Subscribers and failed billing calls see nothing.
import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { fetchBillingMe } from '@/lib/billing';

// EN: plan / plans (2–4) / plans (5+, 0)
const plans = (n: number) => `${n} ${n === 1 ? 'plán' : n >= 2 && n <= 4 ? 'plány' : 'plánů'}`;

export function PlanUpsell() {
  const [remaining, setRemaining] = useState<number | null>(null);

  useEffect(() => {
    let live = true;
    fetchBillingMe()
      .then((b) => { if (live && !b?.subscription?.entitled) setRemaining(Math.max(0, b?.free_generations_remaining ?? 0)); })
      .catch(() => { /* stay silent */ });
    return () => { live = false; };
  }, []);

  if (remaining === null) return null;
  return (
    <aside className="mt-12 rounded-2xl border border-line bg-card p-6 text-left">
      <p className="text-ink">
        {/* EN: You have N more free plan(s). / You've used up your free plans. */}
        {remaining > 0 ? `Máš ještě ${plans(remaining)} zdarma.` : 'Plány zdarma už máš vyčerpané.'}{' '}
        {/* EN: Standard for 99 CZK a month: 7 plans every month and unlimited shopping lists. */}
        <span className="text-muted">Standard za 99 Kč měsíčně: 7 plánů každý měsíc a nákupní seznamy bez omezení.</span>
      </p>
      {/* EN: Have a look at the subscription */}
      <Link to="/pricing" className="mt-2 inline-block font-semibold text-green underline underline-offset-2">Podívat se na předplatné</Link>
    </aside>
  );
}
