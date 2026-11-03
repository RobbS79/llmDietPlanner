// frontend/src/components/discover/TurnstileGate.tsx
// Shown only when /api/discover/ answers 403 CHALLENGE_REQUIRED. Without a
// site key (VITE_TURNSTILE_SITE_KEY) the backend never asks, so this never renders.
import { useEffect, useRef } from 'react';

declare global { interface Window { turnstile?: { render: (el: HTMLElement, o: Record<string, unknown>) => string } } }
const SITE_KEY = import.meta.env.VITE_TURNSTILE_SITE_KEY as string | undefined;

export function TurnstileGate({ onToken }: { onToken: (token: string) => void }) {
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!SITE_KEY || !box.current) return;
    const mount = () => window.turnstile?.render(box.current!, { sitekey: SITE_KEY, callback: onToken, language: 'cs' });
    if (window.turnstile) { mount(); return; }
    const s = document.createElement('script');
    s.src = 'https://challenges.cloudflare.com/turnstile/v0/api.js';
    s.async = true; s.onload = mount;
    document.head.appendChild(s);
  }, [onToken]);
  return (
    <div className="my-4 rounded-2xl border border-kraft bg-white p-4">
      {/* EN: Just a quick check that you're not a robot. */}
      <p className="mb-2 text-ink">Jen rychlé ověření, že nejsi robot.</p>
      <div ref={box} />
    </div>
  );
}
