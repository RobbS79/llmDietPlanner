import { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { CheckCircle2, Loader2, AlertCircle, ArrowRight, Receipt } from 'lucide-react';
import { fetchBillingMe, openBillingPortal, type BillingMe } from '@/lib/billing';
import { isAccessTokenValid } from '@/lib/auth';

const TIER_LABEL: Record<string, string> = {
  standard: 'Standard',
  premium: 'Premium',
};

const POLL_INTERVAL_MS = 1500;
const TIMEOUT_MS = 30_000;

/**
 * Stripe redirects here after a successful Checkout. We poll /billing/me/
 * until the webhook provisions the subscription, then celebrate. If polling
 * times out we surface a soft fallback (Stripe webhooks usually land in <5s
 * but can lag; the email receipt is also already on its way).
 */
export const BillingSuccess = () => {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const sessionId = params.get('session_id');
  const [timedOut, setTimedOut] = useState(false);
  const [portalLoading, setPortalLoading] = useState(false);

  // Bounce to login if the session expired during checkout.
  useEffect(() => {
    if (!isAccessTokenValid() && !localStorage.getItem('refresh_token')) {
      navigate('/login?next=/billing/success' + (sessionId ? `?session_id=${sessionId}` : ''));
    }
  }, [navigate, sessionId]);

  const { data, isError } = useQuery<BillingMe>({
    queryKey: ['billing-me', sessionId],
    queryFn: fetchBillingMe,
    refetchInterval: (q) => (q.state.data?.subscription?.entitled ? false : POLL_INTERVAL_MS),
    refetchIntervalInBackground: true,
    refetchOnWindowFocus: false,
  });

  // 30s safety net so we don't poll forever on a stuck webhook.
  useEffect(() => {
    const t = setTimeout(() => setTimedOut(true), TIMEOUT_MS);
    return () => clearTimeout(t);
  }, []);

  const sub = data?.subscription ?? null;
  const isActive = !!sub?.entitled;
  const tierLabel = useMemo(
    () => (sub?.tier ? TIER_LABEL[sub.tier] ?? sub.tier : ''),
    [sub?.tier],
  );
  const periodEnd = useMemo(() => {
    if (!sub?.current_period_end) return '';
    try {
      return new Date(sub.current_period_end).toLocaleDateString('cs-CZ', {
        day: 'numeric', month: 'long', year: 'numeric',
      });
    } catch {
      return '';
    }
  }, [sub?.current_period_end]);

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
    <div className="min-h-screen bg-[#1e293b] text-white flex flex-col items-center justify-center px-6 py-16">
      <div className="w-full max-w-lg bg-[#0f172a] border border-white/10 rounded-3xl p-10 text-center shadow-2xl">
        {isActive ? (
          <>
            <CheckCircle2 size={64} className="mx-auto text-emerald-400 mb-6" />
            <h1 className="text-3xl font-black tracking-tighter uppercase italic mb-3">
              Předplatné aktivní<span className="text-emerald-400 not-italic">.</span>
            </h1>
            <p className="text-zinc-300 mb-2">
              Děkujeme! Tarif <strong className="text-white">{tierLabel}</strong> je aktivní.
            </p>
            {periodEnd && (
              <p className="text-zinc-400 text-sm mb-8">
                Další platba: {periodEnd}
              </p>
            )}
            <div className="flex flex-col sm:flex-row gap-3 mt-6">
              <Link
                to="/create"
                className="flex-1 inline-flex items-center justify-center gap-2 h-14 px-8 bg-white text-black font-black uppercase text-[11px] tracking-widest rounded-xl hover:bg-zinc-100 transition"
              >
                Vytvořit jídelníček <ArrowRight size={16} />
              </Link>
              <button
                onClick={handlePortal}
                disabled={portalLoading}
                className="flex-1 inline-flex items-center justify-center gap-2 h-14 px-8 bg-transparent border border-white/20 text-white font-black uppercase text-[11px] tracking-widest rounded-xl hover:bg-white/5 transition disabled:opacity-50"
              >
                {portalLoading ? <Loader2 size={16} className="animate-spin" /> : <Receipt size={16} />}
                Faktury a fakturace
              </button>
            </div>
          </>
        ) : timedOut || isError ? (
          <>
            <AlertCircle size={64} className="mx-auto text-amber-400 mb-6" />
            <h1 className="text-2xl font-black tracking-tighter uppercase italic mb-3">
              Aktivace trvá déle než obvykle<span className="text-amber-400 not-italic">.</span>
            </h1>
            <p className="text-zinc-300 mb-2">
              Platba byla v pořádku přijata. Aktivace předplatného obvykle trvá pár sekund —
              někdy se zpozdí. Potvrzení dorazí i e-mailem ze Stripe.
            </p>
            <p className="text-zinc-400 text-sm mb-8">
              Pokud se tarif za chvíli neaktivuje, klikni na „Spravovat fakturaci“ nebo nás kontaktuj.
            </p>
            <div className="flex flex-col sm:flex-row gap-3 mt-6">
              <button
                onClick={() => window.location.reload()}
                className="flex-1 inline-flex items-center justify-center gap-2 h-14 px-8 bg-white text-black font-black uppercase text-[11px] tracking-widest rounded-xl hover:bg-zinc-100 transition"
              >
                Zkusit znovu
              </button>
              <button
                onClick={handlePortal}
                disabled={portalLoading}
                className="flex-1 inline-flex items-center justify-center gap-2 h-14 px-8 bg-transparent border border-white/20 text-white font-black uppercase text-[11px] tracking-widest rounded-xl hover:bg-white/5 transition disabled:opacity-50"
              >
                {portalLoading ? <Loader2 size={16} className="animate-spin" /> : <Receipt size={16} />}
                Spravovat fakturaci
              </button>
            </div>
          </>
        ) : (
          <>
            <Loader2 size={64} className="mx-auto text-emerald-400 mb-6 animate-spin" />
            <h1 className="text-2xl font-black tracking-tighter uppercase italic mb-3">
              Aktivujeme tvé předplatné<span className="text-emerald-400 not-italic">…</span>
            </h1>
            <p className="text-zinc-300 mb-2">
              Platba prošla. Aktivujeme tvůj tarif — obvykle to trvá pár sekund.
            </p>
            <p className="text-zinc-500 text-xs mt-8 break-all">
              {sessionId ? `ID platby: ${sessionId}` : ''}
            </p>
          </>
        )}
      </div>
    </div>
  );
};
