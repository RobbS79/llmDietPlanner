import { useQuery } from '@tanstack/react-query';
import { getWeekDeals, formatDealDate, type WeekDeal } from '@/lib/discover';

const SEARCH_WORD: Record<string, string> = {
  garlic: 'česneku', potatoes: 'brambor', 'olive-oil': 'olivového oleje', lemons: 'citronů',
  parsley: 'petržele', ginger: 'zázvoru', carrots: 'mrkve', cream: 'smetany', 'sour-cream': 'smetany',
};

export const dealSearch = (d: WeekDeal) =>
  `Co uvařit z ${SEARCH_WORD[d.canonical] ?? d.name.split(' ').slice(0, 2).join(' ').toLowerCase()}`;

export function DealsStrip({ onPick }: { onPick: (q: string) => void }) {
  const { data } = useQuery({ queryKey: ['week-deals'], queryFn: getWeekDeals, staleTime: 30 * 60 * 1000 });
  if (!data?.length) return null;   // stale or empty: hide entirely, never "0 v akci"
  return (
    <section className="py-8" aria-labelledby="deals-h">
      {/* EN: "This week on offer" */}
      <h2 id="deals-h" className="font-display text-3xl font-bold text-ink">Tento týden v akci</h2>
      {/* EN: "Ingredients from the Tesco, Lidl, Kaufland, Albert and Penny leaflets. Click and see what to cook from them." */}
      <p className="mt-1 max-w-prose text-[15px] text-muted">Suroviny z letáků Tesca, Lidlu, Kauflandu, Albertu a Penny. Klikni a uvidíš, co z nich uvařit.</p>
      <div className="mt-3 flex gap-2.5 overflow-x-auto pb-2">
        {data.map((d) => (
          <button key={d.canonical} type="button" onClick={() => onPick(dealSearch(d))}
            className="min-w-[150px] flex-none rounded-xl bg-yellow-300 px-3.5 py-2.5 text-left">
            <b className="block text-[17px] text-ink">{d.name.split(' ').slice(0, 2).join(' ')}</b>
            <span className="text-[13px] text-ink">{d.shop} · do {formatDealDate(d.valid_until)}</span>
          </button>
        ))}
      </div>
      {/* EN: "Based on leaflets the shops published. We don't show prices and deals may differ between stores." */}
      <p className="mt-1 text-xs text-muted">Podle letáků, které obchody zveřejnily. Ceny neuvádíme a akce se můžou v jednotlivých prodejnách lišit.</p>
    </section>
  );
}
