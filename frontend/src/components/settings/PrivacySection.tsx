import { useState } from 'react';
import { AlertCircle } from 'lucide-react';
import { Card } from '@/components/ui/Card';
import { useToast } from '@/components/ui/Toast';
import { api } from '@/lib/api';
import { getConsent, setConsent, CONSENT_VERSION } from '@/lib/analytics';
import { extractApiError, type Profile } from '@/lib/settings';

// Reconcile server-known consent (Phase-1 B4) with the local decision that
// actually gates the pixel — localStorage wins if present (it's what
// analytics.ts checks before firing), server value seeds first-time load.
function initialConsent(profile: Profile): boolean {
  const local = getConsent();
  return local !== null ? local : profile.marketing_consent;
}

export function PrivacySection({ profile }: { profile: Profile }) {
  const toast = useToast();
  const [consent, setConsentState] = useState<boolean>(() => initialConsent(profile));
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');

  const handleToggle = async () => {
    const next = !consent;
    setConsentState(next);
    setConsent(next);
    setPending(true);
    setError('');
    try {
      await api.post('/analytics/consent/', { consent: next, version: CONSENT_VERSION });
      toast.success('Souhlas uložen');
    } catch (err) {
      setConsentState(!next);
      setConsent(!next);
      setError(extractApiError(err, 'Nepodařilo se uložit nastavení souhlasu.'));
    } finally {
      setPending(false);
    }
  };

  return (
    <Card variant="paper" className="p-8 space-y-6">
      <h2 className="font-display text-xl font-black text-ink uppercase italic tracking-tight">Soukromí</h2>

      {error && (
        <div role="alert" className="flex items-center gap-3 bg-paprika-soft border border-paprika/20 text-paprika-strong rounded-xl p-4 text-xs font-bold">
          <AlertCircle size={16} className="shrink-0" />
          <span>{error}</span>
        </div>
      )}

      <div className="flex items-center justify-between gap-4">
        <div>
          <h3 className="text-sm font-black text-ink uppercase tracking-tight mb-1">Marketingové cookies</h3>
          <p className="text-xs text-muted font-bold max-w-md">
            Používáme Meta Pixel k měření účinnosti reklam. Změna se plně projeví po znovunačtení stránky.
          </p>
        </div>
        <button
          type="button"
          role="switch"
          aria-checked={consent}
          onClick={handleToggle}
          disabled={pending}
          className={`shrink-0 inline-flex items-center gap-2 px-4 py-2 rounded-full border text-[10px] font-black uppercase tracking-widest transition-all disabled:opacity-50 ${
            consent ? 'bg-green-soft border-green/40 text-green' : 'bg-kraft border-line text-muted'
          }`}
        >
          {consent ? 'Povoleno' : 'Zakázáno'}
        </button>
      </div>
    </Card>
  );
}
