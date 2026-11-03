// frontend/src/components/discover/TurnstileGate.tsx
// Shown only when /api/discover/ answers 403 CHALLENGE_REQUIRED. The backend asks
// only when both Turnstile keys are set at runtime; VITE_TURNSTILE_SITE_KEY is a
// build arg (Dockerfile.prod). If the build missed it, say so instead of an empty box.
import { useEffect, useRef } from 'react';

declare global { interface Window { turnstile?: { render: (el: HTMLElement, o: Record<string, unknown>) => string } } }

export function TurnstileGate({ onToken }: { onToken: (token: string) => void }) {
  const siteKey = import.meta.env.VITE_TURNSTILE_SITE_KEY as string | undefined;
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!siteKey || !box.current) return;
    const mount = () => window.turnstile?.render(box.current!, { sitekey: siteKey, callback: onToken, language: 'cs' });
    if (window.turnstile) { mount(); return; }
    const s = document.createElement('script');
    s.src = 'https://challenges.cloudflare.com/turnstile/v0/api.js';
    s.async = true; s.onload = mount;
    document.head.appendChild(s);
  }, [onToken, siteKey]);
  return (
    <div className="my-4 rounded-2xl border border-kraft bg-white p-4">
      {siteKey ? (
        <>
          {/* EN: Just a quick check that you're not a robot. */}
          <p className="mb-2 text-ink">Jen rychlé ověření, že nejsi robot.</p>
          <div ref={box} />
        </>
      ) : (
        // EN: Can't verify right now. Please try again in a moment.
        <p className="text-ink">Teď to nejde ověřit. Zkus to prosím za chvíli.</p>
      )}
    </div>
  );
}
