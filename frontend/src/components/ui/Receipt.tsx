interface ReceiptItem {
  day?: string;        // e.g. "PO"
  name: string;
  price?: string;      // formatted, e.g. "72" — omit for the price-less deals mode
  meta?: string;       // right-side secondary text when there's no price, e.g. "300 g"
  deal?: boolean;      // shows "ve slevě" chip
}
interface ReceiptProps {
  title: string;        // e.g. "Váš týden"
  subtitle?: string;    // e.g. "3 jídla denně · 7 dní"
  source?: string;      // e.g. "Rohlík.cz"
  items: ReceiptItem[];
  totalLabel: string;   // e.g. "Ve slevě tento týden"
  total?: string;       // money total, e.g. "92–115" — omit in deals mode
  footnote?: string;    // deals headline shown in the footer when there's no money total
  currency?: string;    // default "Kč"
}

// Kraft-receipt signature card. Two modes:
//  - price mode: pass `price` per item + a money `total`.
//  - deals mode: pass `meta` (unit) per item + a `footnote` headline, no money.
export const Receipt = ({ title, subtitle, source, items, totalLabel, total, footnote, currency = 'Kč' }: ReceiptProps) => (
  <div className="relative bg-card border border-line rounded-2xl p-7 shadow-[0_26px_50px_-28px_rgba(36,30,26,0.35)]">
    <div className="absolute left-0 right-0 -top-px h-2 rounded-t-2xl"
         style={{ background: 'repeating-linear-gradient(90deg,#DB5026 0 14px,transparent 14px 22px)' }} />
    <div className="flex items-end justify-between border-b-2 border-dashed border-line pb-3.5 mb-1.5">
      <div>
        <div className="font-display font-bold text-lg text-ink">{title}</div>
        {subtitle && <div className="text-[11px] uppercase tracking-[0.12em] text-muted mt-0.5">{subtitle}</div>}
      </div>
      {source && <div className="text-xs font-bold text-green">{source}</div>}
    </div>
    {items.map((it, i) => (
      <div key={i} className="flex items-baseline gap-2 py-2.5 text-[15px]">
        {it.day && <span className="font-price text-[11px] text-muted w-8">{it.day}</span>}
        <span className="font-semibold text-ink">{it.name}</span>
        {it.deal && <span className="bg-paprika-soft text-paprika-strong font-bold text-[11px] px-1.5 py-0.5 rounded-md">ve slevě</span>}
        <span className="flex-1 border-b border-dotted border-[#cdbfa6] translate-y-[-4px]" />
        {it.price != null
          ? <span className="font-price font-bold text-[15px] text-ink">{it.price}&nbsp;{currency}</span>
          : it.meta && <span className="font-price text-[13px] text-muted">{it.meta}</span>}
      </div>
    ))}
    {total != null ? (
      <div className="flex items-center justify-between border-t-2 border-dashed border-line mt-2 pt-4">
        <span className="font-bold text-sm uppercase tracking-[0.1em] text-muted">{totalLabel}</span>
        <span className="font-price font-bold text-3xl text-ink">{total}<small className="text-[15px] text-muted">&nbsp;{currency}</small></span>
      </div>
    ) : (
      <div className="border-t-2 border-dashed border-line mt-2 pt-4 text-center">
        {footnote && <p className="font-display font-bold text-base text-paprika-strong">{footnote}</p>}
        <p className="text-[11px] font-bold uppercase tracking-[0.12em] text-muted mt-1">{totalLabel}</p>
      </div>
    )}
  </div>
);
