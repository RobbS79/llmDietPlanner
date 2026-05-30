import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { ArrowLeft, Printer, Check, Tag, Store, PiggyBank, Calendar, ChevronDown, Info, MessageSquare, Send, CheckCircle, Loader2 } from 'lucide-react';
import { useState } from 'react';
import { api } from '@/lib/api';
import { MainLayout } from '@/components/layout/MainLayout';
import { Card } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { LoadingScreen } from '@/components/ui/LoadingScreen';

// ---- Pricing payload shape (mirrors compute_pricing() in
// diet_planner/services/shopping_list_pricing.py) ----
interface PriceRange {
  low: number;
  high: number;
  currency: string;
  store_low: string;
  store_low_name: string;
  store_high: string;
  store_high_name: string;
  items_counted: number;
}
interface DealItem {
  ingredient: string;
  matched_product_name: string;
  sale: number;
  original: number | null;
  savings: number | null;
}
interface Deal {
  store: string;
  store_name: string;
  status: 'current' | 'upcoming';
  valid_from: string | null;
  valid_until: string | null;
  currency: string;
  items: DealItem[];
  store_total_savings: number;
}
interface Pricing {
  price_range: PriceRange | null;
  deals: Deal[];
  pantry_toggles: { basics_on: boolean; fridge_on: boolean };
}

const EMPTY_DEALS_COPY =
  'Snažili jsme se, ale pro vaše jídla jsme tento týden žádné slevy nenašli :(';

// Format an ISO datetime into the Czech "DD.MM." leaflet token.
const fmtDay = (iso: string | null): string => {
  if (!iso) return '';
  const d = new Date(iso);
  if (isNaN(d.getTime())) return '';
  return `${d.getDate()}.${d.getMonth() + 1}.`;
};

const fmtMoney = (n: number): string =>
  Number.isInteger(n) ? String(n) : n.toFixed(1);

const isStapleItem = (item: any): boolean =>
  item?.is_pantry_staple === true || item?.pantry === true;

const normName = (s: string | undefined | null): string =>
  (s || '').toLowerCase().trim();

// ---- Simplified list row: checkbox + name + qty (+ optional deal chip) ----
const ShoppingItem = ({
  item,
  done,
  onToggle,
  dealStoreName,
}: {
  item: any;
  done: boolean;
  onToggle: () => void;
  dealStoreName?: string | null;
}) => (
  <Card
    onClick={onToggle}
    className={`p-5 cursor-pointer select-none transition-all text-left ${done ? 'opacity-40 border-slate-600/50' : 'hover:border-emerald-500/20'}`}
  >
    <div className="flex items-center gap-4">
      <div className={`w-7 h-7 rounded-lg border-2 flex items-center justify-center shrink-0 transition-colors ${done ? 'bg-emerald-600 border-emerald-600' : 'border-slate-500'}`}>
        {done && <Check size={16} className="text-white" />}
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex justify-between items-center gap-3">
          <p className={`text-base font-black uppercase tracking-tight italic leading-none truncate ${done ? 'line-through text-zinc-400' : 'text-white'}`}>
            {item.ingredient}
          </p>
          <span className="text-[10px] font-black text-zinc-400 uppercase tracking-widest italic shrink-0 whitespace-nowrap">
            {item.quantity} {item.unit}
          </span>
        </div>
        {dealStoreName && (
          <div className="mt-2">
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[9px] font-black uppercase tracking-wider border bg-emerald-500/10 text-emerald-400 border-emerald-500/20">
              <Tag size={9} /> ★ akce u {dealStoreName}
            </span>
          </div>
        )}
      </div>
    </div>
  </Card>
);

// ---- Pantry pill toggle ----
const PantryToggle = ({
  label,
  on,
  onChange,
  disabled,
}: {
  label: string;
  on: boolean;
  onChange: (next: boolean) => void;
  disabled?: boolean;
}) => (
  <button
    type="button"
    onClick={() => onChange(!on)}
    disabled={disabled}
    aria-pressed={on}
    className="flex items-center gap-3 w-full text-left disabled:opacity-50"
  >
    <span className={`w-6 h-6 rounded-md border-2 flex items-center justify-center shrink-0 transition-colors ${on ? 'bg-emerald-600 border-emerald-600' : 'border-slate-500'}`}>
      {on && <Check size={14} className="text-white" />}
    </span>
    <span className={`text-xs font-bold italic leading-snug ${on ? 'text-zinc-100' : 'text-zinc-300'}`}>
      {label}
    </span>
  </button>
);

export const ShoppingListPage = () => {
  const { id } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const storageKey = `shopping-checked-${id}`;
  const [checked, setChecked] = useState<Set<string>>(() => {
    const saved = localStorage.getItem(storageKey);
    return saved ? new Set(JSON.parse(saved)) : new Set();
  });
  const [showFeedbackForm, setShowFeedbackForm] = useState(false);
  const [actualTotal, setActualTotal] = useState('');
  const [feedbackNote, setFeedbackNote] = useState('');
  const [basicsExpanded, setBasicsExpanded] = useState(false);
  // Optimistic local override for the pantry toggles. Falls back to the
  // server-persisted values from pricing.pantry_toggles when unset.
  const [toggleOverride, setToggleOverride] = useState<{ basics_on: boolean; fridge_on: boolean } | null>(null);

  const { data: goalDetail, isLoading } = useQuery({
    queryKey: ['plan', id],
    queryFn: () => api.get(`/goals/${id}/`).then(res => res.data.data),
  });

  const { data: existingFeedback } = useQuery({
    queryKey: ['price-feedback', id],
    queryFn: () => api.get(`/goals/${id}/price-feedback/`).then(res => res.data.data),
    enabled: Boolean(id),
  });

  const submitFeedback = useMutation({
    mutationFn: () => api.post(`/goals/${id}/price-feedback/`, {
      actual_total: parseFloat(actualTotal),
      note: feedbackNote,
    }),
    onSuccess: () => {
      setShowFeedbackForm(false);
      queryClient.invalidateQueries({ queryKey: ['price-feedback', id] });
    },
  });

  // Persist the pantry toggles and re-request pricing with the new values.
  // Mirrors the PATCH /goals/<id>/ pattern used for other plan settings
  // (see PlanView meal PATCH + Onboarding profile PATCH).
  const saveToggles = useMutation({
    // PATCH /goals/<id>/ persists the toggles as flat booleans
    // (pantry_basics_on / pantry_fridge_on) on the plan; the recomputed
    // `pricing` payload (range + deals) comes back on the next refetch.
    mutationFn: (toggles: { basics_on: boolean; fridge_on: boolean }) =>
      api.patch(`/goals/${id}/`, {
        pantry_basics_on: toggles.basics_on,
        pantry_fridge_on: toggles.fridge_on,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['plan', id] });
    },
  });

  if (isLoading || !goalDetail) return <LoadingScreen message="Loading shopping list..." />;

  const plan = goalDetail.dietary_plan;
  if (!plan) return <LoadingScreen message="Loading shopping list..." />;

  const pricing: Pricing | null = plan.pricing || null;
  const priceRange = pricing?.price_range || null;
  const deals: Deal[] = pricing?.deals || [];

  // Toggle state: optimistic override wins, else server value, else defaults.
  const serverToggles = pricing?.pantry_toggles || { basics_on: true, fridge_on: false };
  const toggles = toggleOverride || serverToggles;

  const currency = priceRange?.currency || plan.currency || 'Kč';

  const rawList = plan.shopping_list || [];
  const isCrossStore = rawList && !Array.isArray(rawList) && rawList.by_store;
  const items: any[] = isCrossStore ? (rawList.items || []) : rawList;

  // Sum of store_total_savings across CURRENT deals only (anchor headline).
  const currentSavings = deals
    .filter(d => d.status === 'current')
    .reduce((acc, d) => acc + (d.store_total_savings || 0), 0);

  // Map plan ingredient name -> store name of a matching deal (for the ★ chip).
  const dealStoreByIngredient: Record<string, string> = {};
  deals.forEach(d => {
    d.items.forEach(di => {
      const key = normName(di.ingredient);
      if (key && !dealStoreByIngredient[key]) dealStoreByIngredient[key] = d.store_name;
    });
  });

  const groceries = items.filter((i: any) => !isStapleItem(i));
  const pantry = items.filter((i: any) => isStapleItem(i));

  const totalItems = groceries.length;
  const checkedCount = checked.size;

  const toggleItem = (key: string) => {
    setChecked(prev => {
      const next = new Set(prev);
      next.has(key) ? next.delete(key) : next.add(key);
      localStorage.setItem(storageKey, JSON.stringify([...next]));
      return next;
    });
  };

  const handleToggleChange = (field: 'basics_on' | 'fridge_on', next: boolean) => {
    const updated = { ...toggles, [field]: next };
    setToggleOverride(updated);
    saveToggles.mutate(updated);
  };

  const handlePrint = () => window.print();

  const scrollToDeals = () => {
    document.getElementById('deals-section')?.scrollIntoView({ behavior: 'smooth' });
  };

  return (
    <MainLayout>
      <div className="max-w-3xl mx-auto px-6 py-12 w-full">
        <button
          onClick={() => navigate(`/plan/${id}`)}
          className="flex items-center gap-2 text-zinc-300 hover:text-white text-xs font-black uppercase tracking-widest mb-12 transition-colors print:hidden"
        >
          <ArrowLeft size={16} /> Zpět na plán
        </button>

        <header className="mb-8 flex flex-col sm:flex-row sm:items-end justify-between gap-8 text-left">
          <div className="space-y-4">
            <Badge variant="emerald">Nákupní seznam</Badge>
            <h1 className="text-5xl sm:text-6xl font-black text-white tracking-tighter uppercase italic leading-[0.9]">
              Váš seznam<span className="text-emerald-500 not-italic">.</span>
            </h1>
            <p className="text-zinc-400 text-sm font-bold italic">
              {totalItems} položek &middot; {checkedCount} odškrtnuto
            </p>
          </div>
          <button
            onClick={handlePrint}
            className="flex items-center gap-2 bg-slate-700 border border-slate-600 text-zinc-200 hover:text-white px-6 h-12 rounded-xl font-black uppercase text-[10px] tracking-[0.15em] transition-colors print:hidden"
          >
            <Printer size={16} /> Tisknout
          </button>
        </header>

        {/* ---- Sticky top card: range + pantry toggles + savings anchor ---- */}
        <Card className="p-6 mb-10 text-left sticky top-4 z-20 backdrop-blur supports-[backdrop-filter]:bg-slate-700/70 print:static">
          {priceRange && (
            <>
              <div>
                <p className="text-[10px] font-black text-zinc-400 uppercase tracking-[0.2em] italic mb-1">
                  Běžná cena
                </p>
                <p className="text-3xl font-black text-white italic tracking-tighter tabular-nums">
                  {fmtMoney(priceRange.low)}–{fmtMoney(priceRange.high)}
                  <span className="text-emerald-500 text-base not-italic ml-2 uppercase">{currency}</span>
                </p>
                <p className="text-[10px] font-bold text-zinc-400 italic mt-1">
                  od {priceRange.store_low_name} po {priceRange.store_high_name}
                </p>
              </div>
              <div className="h-px bg-slate-600/60 my-5" />
            </>
          )}

          <div className="space-y-3">
            <PantryToggle
              label="Mám doma základy (olej, sůl, koření)"
              on={toggles.basics_on}
              onChange={(next) => handleToggleChange('basics_on', next)}
              disabled={saveToggles.isPending}
            />
            <PantryToggle
              label="Mám doma mléko, máslo, vejce"
              on={toggles.fridge_on}
              onChange={(next) => handleToggleChange('fridge_on', next)}
              disabled={saveToggles.isPending}
            />
          </div>

          {currentSavings > 0 && (
            <>
              <div className="h-px bg-slate-600/60 my-5" />
              <button
                onClick={scrollToDeals}
                className="flex items-center gap-2 text-sm font-black text-emerald-400 hover:text-emerald-300 uppercase tracking-tight italic transition-colors"
              >
                <PiggyBank size={18} />
                Tento týden ušetříte až ~{Math.round(currentSavings)} {currency}
              </button>
            </>
          )}
        </Card>

        {/* ---- AKCE TENTO TÝDEN ---- */}
        <div id="deals-section" className="mb-10">
          <h2 className="text-xs font-black text-emerald-400 uppercase tracking-[0.25em] italic mb-4">
            Akce tento týden
          </h2>
          {deals.length === 0 ? (
            <Card className="p-6 text-left">
              <p className="text-sm font-bold text-zinc-300 italic leading-relaxed">
                {EMPTY_DEALS_COPY}
              </p>
            </Card>
          ) : (
            <div className="space-y-5">
              {deals.map((deal, di) => (
                <Card key={`${deal.store}-${deal.status}-${di}`} className="p-5 text-left">
                  <div className="flex items-center justify-between gap-3 mb-4 flex-wrap">
                    <div className="flex items-center gap-2 flex-wrap">
                      <Store size={16} className="text-zinc-300" />
                      <h3 className="text-sm font-black text-white uppercase tracking-widest italic">
                        {deal.store_name}
                      </h3>
                      {deal.status === 'upcoming' && (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[9px] font-black uppercase tracking-wider border bg-amber-500/10 text-amber-400 border-amber-500/20">
                          <Calendar size={9} /> [od {fmtDay(deal.valid_from)}]
                        </span>
                      )}
                      {(deal.valid_from || deal.valid_until) && (
                        <span className="text-[10px] font-bold text-zinc-400 italic">
                          {fmtDay(deal.valid_from)}–{fmtDay(deal.valid_until)}
                        </span>
                      )}
                    </div>
                    {deal.store_total_savings > 0 && (
                      <span className="text-[10px] font-black text-emerald-400 uppercase tracking-widest italic">
                        ušetříte {Math.round(deal.store_total_savings)} {deal.currency}
                      </span>
                    )}
                  </div>
                  <div className="space-y-3">
                    {deal.items.map((it, ii) => (
                      <div key={ii} className="flex items-center justify-between gap-3">
                        <p className="text-xs font-bold text-zinc-200 truncate min-w-0">
                          {it.matched_product_name || it.ingredient}
                        </p>
                        <div className="flex items-center gap-2 shrink-0 tabular-nums">
                          {it.original != null && (
                            <span className="text-[10px] font-bold text-zinc-400 line-through">
                              {fmtMoney(it.original)}
                            </span>
                          )}
                          <span className="text-sm font-black text-emerald-500">
                            {fmtMoney(it.sale)} {deal.currency}
                          </span>
                          {it.savings != null && it.savings > 0 && (
                            <span className="text-[10px] font-black text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded-lg">
                              −{Math.round(it.savings)} {deal.currency}
                            </span>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </Card>
              ))}
            </div>
          )}
        </div>

        {/* ---- NÁKUPNÍ SEZNAM (main list) ---- */}
        <div className="mb-10">
          <h2 className="text-xs font-black text-zinc-300 uppercase tracking-[0.25em] italic mb-4">
            Nákupní seznam
          </h2>
          <div className="space-y-3">
            {groceries.map((item: any) => {
              const itemKey = `g-${items.indexOf(item)}`;
              const dealStore = dealStoreByIngredient[normName(item.ingredient)] || null;
              return (
                <ShoppingItem
                  key={itemKey}
                  item={item}
                  done={checked.has(itemKey)}
                  onToggle={() => toggleItem(itemKey)}
                  dealStoreName={dealStore}
                />
              );
            })}
          </div>
        </div>

        {/* ---- ZÁKLADY (quiet collapsed pantry section) ---- */}
        {pantry.length > 0 && (
          <div className="mb-10 print:hidden">
            <button
              onClick={() => setBasicsExpanded(v => !v)}
              className="flex items-center gap-2 text-[10px] font-black text-zinc-400 hover:text-zinc-200 uppercase tracking-widest italic transition-colors"
            >
              <ChevronDown size={14} className={`transition-transform ${basicsExpanded ? 'rotate-180' : ''}`} />
              Základy (předpokládáme, že máte)
            </button>
            {basicsExpanded && (
              <p className="mt-3 text-xs font-bold text-zinc-500 italic leading-relaxed">
                {pantry.map((i: any) => i.ingredient).join(', ')}
              </p>
            )}
          </div>
        )}

        {/* ---- Price disclaimer + feedback ---- */}
        <div className="mt-6 space-y-4 print:hidden">
          <Card className="p-5 border-amber-500/10 text-left">
            <div className="flex gap-3">
              <Info size={18} className="text-amber-500/70 shrink-0 mt-0.5" />
              <div className="space-y-2">
                <p className="text-xs font-bold text-zinc-200 leading-relaxed">
                  Uvedené ceny jsou <span className="text-amber-400">orientační</span> a vycházejí z dostupných dat obchodů. Skutečná cena nákupu se může lišit v závislosti na aktuální nabídce, velikosti balení a dostupnosti produktů.
                </p>
                {existingFeedback ? (
                  <div className="flex items-center gap-2 pt-1">
                    <CheckCircle size={14} className="text-emerald-500" />
                    <p className="text-[10px] font-black text-emerald-500 uppercase tracking-widest">
                      Zpětná vazba odeslána &middot; Skutečná cena: {existingFeedback.actual_total} {existingFeedback.currency}
                    </p>
                  </div>
                ) : (
                  <button
                    onClick={() => setShowFeedbackForm(v => !v)}
                    className="flex items-center gap-1.5 text-[10px] font-black text-zinc-300 hover:text-emerald-400 uppercase tracking-widest transition-colors pt-1"
                  >
                    <MessageSquare size={12} />
                    {showFeedbackForm ? 'Skrýt formulář' : 'Zaplatili jste jinou cenu? Dejte nám vědět'}
                  </button>
                )}
              </div>
            </div>
          </Card>

          {showFeedbackForm && !existingFeedback && (
            <Card className="p-6 border-slate-600 text-left">
              <p className="text-xs font-black text-white uppercase tracking-widest italic mb-4">
                Zpětná vazba k ceně
              </p>
              <div className="space-y-4">
                <div>
                  <label className="block text-[10px] font-black text-zinc-400 uppercase tracking-widest mb-2">
                    Skutečná cena nákupu ({currency})
                  </label>
                  <input
                    type="number"
                    min="0"
                    step="0.01"
                    value={actualTotal}
                    onChange={e => setActualTotal(e.target.value)}
                    placeholder={priceRange ? String(priceRange.low) : '0'}
                    className="w-full h-12 bg-black/50 border border-slate-600 rounded-xl px-4 text-white font-bold text-sm focus:outline-none focus:border-emerald-500/50 transition-colors tabular-nums"
                  />
                </div>
                <div>
                  <label className="block text-[10px] font-black text-zinc-400 uppercase tracking-widest mb-2">
                    Poznámka (volitelné)
                  </label>
                  <textarea
                    value={feedbackNote}
                    onChange={e => setFeedbackNote(e.target.value)}
                    placeholder="Např. chyběly 2 položky, cena kuřecích prsou byla vyšší..."
                    rows={2}
                    maxLength={1000}
                    className="w-full bg-black/50 border border-slate-600 rounded-xl px-4 py-3 text-white font-bold text-sm focus:outline-none focus:border-emerald-500/50 transition-colors resize-none"
                  />
                </div>
                <button
                  onClick={() => submitFeedback.mutate()}
                  disabled={!actualTotal || submitFeedback.isPending}
                  className="flex items-center justify-center gap-2 w-full h-12 bg-emerald-600 hover:bg-emerald-500 text-white rounded-xl font-black uppercase text-[10px] tracking-widest transition-all disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  {submitFeedback.isPending ? (
                    <><Loader2 size={14} className="animate-spin" /> Odesílám...</>
                  ) : (
                    <><Send size={14} /> Odeslat zpětnou vazbu</>
                  )}
                </button>
              </div>
            </Card>
          )}
        </div>
      </div>
    </MainLayout>
  );
};
