/**
 * Right-hand ad rail. Reserved layout for display banners (IAB 300x250 /
 * 300x600), shown on every page that mounts it — but ONLY when
 * `VITE_ADS_ENABLED=true` at build time. There is no ad contract yet
 * (2026-09-16), so the default build renders nothing and the content column
 * simply centers. When a network is signed: set the env var on the DO build,
 * drop the network's tag into the slot below, extend the CSP script-src and
 * add an advertising purpose to the consent banner.
 */
export function adsEnabled(): boolean {
  return String(import.meta.env.VITE_ADS_ENABLED || '').toLowerCase() === 'true';
}

export const AdRail = ({ slot }: { slot: string }) => {
  if (!adsEnabled()) return null;
  return (
    <aside aria-label="Reklama" className="hidden xl:block w-[300px] shrink-0">
      <div className="sticky top-6">
        <div
          data-ad-slot={slot}
          className="w-[300px] min-h-[250px] rounded-2xl border border-dashed border-line bg-card flex items-center justify-center text-[10px] font-black uppercase tracking-[0.2em] text-muted"
        >
          Reklama
        </div>
      </div>
    </aside>
  );
};
