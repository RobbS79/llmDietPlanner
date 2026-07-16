import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Loader2 } from 'lucide-react';
import { Card } from '@/components/ui/Card';
import { openBillingPortal, type BillingMe } from '@/lib/billing';

const TIER_LABEL: Record<string, string> = { standard: 'Standard', premium: 'Premium' };

export function SubscriptionSection({ billing }: { billing: BillingMe | undefined }) {
  const [portalLoading, setPortalLoading] = useState(false);
  const sub = billing?.subscription;
  const isEntitled = !!sub?.entitled;

  const handlePortal = async () => {
    if (portalLoading) return;
    setPortalLoading(true);
    try {
      await openBillingPortal(); // redirects on success
    } catch {
      setPortalLoading(false);
    }
  };

  return (
    <Card variant="paper" className="p-8 space-y-6">
      <h2 className="font-display text-xl font-black text-ink uppercase italic tracking-tight">Předplatné</h2>

      {!billing ? (
        <p className="text-sm text-muted font-bold">Načítání…</p>
      ) : isEntitled && sub ? (
        <div className="space-y-4">
          <div>
            <label className="text-[10px] font-black uppercase tracking-widest text-muted block mb-1.5">Aktuální tarif</label>
            <span className="text-lg font-black text-ink">{TIER_LABEL[sub.tier] ?? sub.tier}</span>
          </div>
          <p className="text-sm text-muted font-bold">
            Využito {sub.plans_used_this_period} z {sub.plans_used_this_period + sub.remaining_quota} tento měsíc
          </p>
          <button
            type="button"
            onClick={handlePortal}
            disabled={portalLoading}
            className="flex items-center gap-3 px-8 h-12 bg-green hover:bg-green-mid text-white rounded-xl font-black uppercase text-[10px] tracking-widest transition-all active:scale-[0.98] disabled:opacity-50"
          >
            {portalLoading && <Loader2 size={14} className="animate-spin" />}
            Spravovat předplatné
          </button>
        </div>
      ) : (
        <div className="space-y-4">
          <div>
            <label className="text-[10px] font-black uppercase tracking-widest text-muted block mb-1.5">Aktuální tarif</label>
            <span className="text-lg font-black text-ink">Zdarma</span>
          </div>
          <p className="text-sm text-muted font-bold">Zbývá {billing.free_generations_remaining} generování zdarma</p>
          <Link
            to="/pricing"
            className="inline-flex items-center gap-3 px-8 h-12 bg-green hover:bg-green-mid text-white rounded-xl font-black uppercase text-[10px] tracking-widest transition-all"
          >
            Zobrazit tarify
          </Link>
        </div>
      )}
    </Card>
  );
}
