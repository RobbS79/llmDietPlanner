import { useEffect, useState } from 'react';
import axios from 'axios';
import { getConsent, setConsent, loadPixel, CONSENT_VERSION } from '@/lib/analytics';

// Binary GDPR consent banner (Přijmout / Odmítnout, equal prominence).
// Shows until a decision exists in localStorage. Market-Paper themed.
export function ConsentBanner() {
  const [visible, setVisible] = useState(false);
  useEffect(() => { setVisible(getConsent() === null); }, []);

  async function decide(consent: boolean) {
    setConsent(consent);
    setVisible(false);
    if (consent) loadPixel();
    // Only sync to the server when authenticated. The consent endpoint is
    // IsAuthenticated, so an anonymous POST just 401s — noise on the ad funnel.
    // Anonymous consent lives in localStorage and rides the signup payload.
    // Bare axios (not the shared `api` instance) avoids the shared instance's
    // 401 interceptor, which would redirect a token-expired user to /login.
    if (localStorage.getItem('access_token')) {
      try { await axios.post('/api/analytics/consent/', { consent, version: CONSENT_VERSION }); }
      catch { /* offline or token expired — decision persists in localStorage */ }
    }
  }

  if (!visible) return null;

  return (
    <div role="dialog" aria-label="Souhlas s cookies"
         className="fixed bottom-0 inset-x-0 z-[60] border-t border-line bg-paper text-ink px-4 py-4 shadow-lg">
      <div className="mx-auto max-w-4xl flex flex-col sm:flex-row sm:items-center gap-3">
        <p className="text-sm leading-snug text-muted flex-1">
          Používáme marketingové cookies (Meta Pixel), abychom měřili, jak lidé
          přicházejí z reklam. Bez vašeho souhlasu se nenačtou.{' '}
          <a href="/privacy" className="text-green hover:text-green-mid underline underline-offset-2 font-semibold">
            Zásady ochrany údajů
          </a>.
        </p>
        <div className="flex gap-2 shrink-0">
          <button onClick={() => decide(false)}
                  className="px-4 py-2 text-sm font-bold rounded-xl border border-line text-ink hover:bg-kraft transition-all">
            Odmítnout
          </button>
          <button onClick={() => decide(true)}
                  className="px-4 py-2 text-sm font-bold rounded-xl bg-green hover:bg-green-mid text-white shadow-lg transition-all">
            Přijmout
          </button>
        </div>
      </div>
    </div>
  );
}
