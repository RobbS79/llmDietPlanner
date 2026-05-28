import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { ArrowLeft, ShoppingCart, Printer, Check, Tag, Store, Sparkles, Clock, HelpCircle, TrendingDown, Percent, Loader2, ArrowRight, X, Info, MessageSquare, Send, CheckCircle, AlertTriangle, RefreshCw } from 'lucide-react';
import { useState } from 'react';
import { api } from '@/lib/api';
import { MainLayout } from '@/components/layout/MainLayout';
import { Card } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { LoadingScreen } from '@/components/ui/LoadingScreen';

const PRICE_SOURCE_CONFIG: Record<string, { label: string; color: string; icon: typeof Tag }> = {
  leaflet_discount: { label: 'Akce', color: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20', icon: Tag },
  store_regular: { label: 'Běžná cena', color: 'bg-blue-500/10 text-blue-400 border-blue-500/20', icon: Store },
  pantry_estimate: { label: 'Odhad', color: 'bg-amber-500/10 text-amber-400 border-amber-500/20', icon: Sparkles },
  cross_store_match: { label: 'Jiný obchod', color: 'bg-violet-500/10 text-violet-400 border-violet-500/20', icon: Store },
  historical_average: { label: 'Historická', color: 'bg-orange-500/10 text-orange-400 border-orange-500/20', icon: Clock },
  not_available: { label: 'Nedostupná', color: 'bg-zinc-500/10 text-zinc-300 border-zinc-500/20', icon: HelpCircle },
};

const PriceSourceBadge = ({ source, detail }: { source?: string; detail?: string }) => {
  if (!source) return null;
  const config = PRICE_SOURCE_CONFIG[source];
  if (!config) return null;
  const Icon = config.icon;
  return (
    <span
      className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[9px] font-black uppercase tracking-wider border ${config.color}`}
      title={detail || config.label}
    >
      <Icon size={9} />
      {config.label}
    </span>
  );
};

const isStapleItem = (item: any): boolean =>
  item?.is_pantry_staple === true || item?.pantry === true;

const ShoppingItem = ({ item, done, onToggle, staple = false }: { item: any; done: boolean; onToggle: () => void; staple?: boolean }) => {
  const fractionPct = staple && typeof item.fraction_used === 'number'
    ? Math.max(1, Math.round(item.fraction_used * 100))
    : null;
  return (
    <Card
      onClick={onToggle}
      className={`p-5 cursor-pointer select-none transition-all text-left ${done ? 'opacity-40 border-slate-600/50' : 'hover:border-emerald-500/20'}`}
    >
      <div className="flex items-center gap-4">
        <div className={`w-7 h-7 rounded-lg border-2 flex items-center justify-center shrink-0 transition-colors ${done ? 'bg-emerald-600 border-emerald-600' : 'border-slate-500'}`}>
          {done && <Check size={16} className="text-white" />}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex justify-between items-start gap-3">
            <p className={`text-base font-black uppercase tracking-tight italic leading-none truncate ${done ? 'line-through text-zinc-400' : 'text-white'}`}>
              {item.ingredient}
            </p>
            <div className="flex items-center gap-2 shrink-0">
              {item.original_price != null && item.discount_percentage != null && (
                <span className="text-[10px] font-bold text-zinc-400 line-through tabular-nums">
                  {item.original_price}
                </span>
              )}
              {item.price_total != null ? (
                <p className="text-sm font-black text-emerald-500 tabular-nums leading-none whitespace-nowrap">
                  {item.price_total} {item.currency}
                </p>
              ) : item.price != null ? (
                <p className="text-sm font-black text-emerald-500 tabular-nums leading-none whitespace-nowrap">
                  {item.price} {item.currency}
                </p>
              ) : null}
            </div>
          </div>
          <div className="flex justify-between items-center mt-2">
            <div className="flex items-center gap-2">
              <span className="text-[10px] font-black text-zinc-400 uppercase tracking-widest italic">
                {item.quantity} {item.unit}
              </span>
              <PriceSourceBadge source={item.price_source} detail={item.source_detail} />
            </div>
            {item.matched_product_name && (
              <span className="text-[10px] font-black text-zinc-400 uppercase tracking-widest italic opacity-50 max-w-[180px] truncate text-right">
                {item.matched_product_name}
              </span>
            )}
          </div>
          {staple && item.pantry_pack_price != null && (
            <div className="flex justify-between items-center mt-2 pt-2 border-t border-slate-600/50">
              <span className="text-[10px] font-bold text-zinc-300 italic">
                {fractionPct != null ? `${fractionPct}% balení` : 'Část balení'}
              </span>
              <span className="text-[10px] font-bold text-zinc-300 italic">
                Plné balení{item.pantry_package_size ? ` (${item.pantry_package_size} ${item.pantry_package_unit || ''})` : ''}:{' '}
                <span className="text-zinc-300 tabular-nums">{item.pantry_pack_price} {item.currency}</span>
              </span>
            </div>
          )}
        </div>
      </div>
    </Card>
  );
};

export const ShoppingListPage = () => {
  const { id } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const storageKey = `shopping-checked-${id}`;
  const [checked, setChecked] = useState<Set<string>>(() => {
    const saved = localStorage.getItem(storageKey);
    return saved ? new Set(JSON.parse(saved)) : new Set();
  });
  const [optimizing, setOptimizing] = useState(false);
  const [showOptimization, setShowOptimization] = useState(false);
  const [timeoutError, setTimeoutError] = useState(false);
  const [selectedShops, setSelectedShops] = useState<string[] | null>(null);
  const [showFeedbackForm, setShowFeedbackForm] = useState(false);
  const [actualTotal, setActualTotal] = useState('');
  const [feedbackNote, setFeedbackNote] = useState('');

  const { data: goalDetail, isLoading } = useQuery({
    queryKey: ['plan', id],
    queryFn: () => api.get(`/goals/${id}/`).then(res => res.data.data),
  });

  const country = goalDetail?.country;
  const { data: shopsData } = useQuery({
    queryKey: ['shops', country],
    queryFn: () => api.get(`/shops/?country=${country}`).then(res => res.data.data?.shops || []),
    enabled: Boolean(country),
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

  const triggerOptimization = useMutation({
    mutationFn: (opts: { force?: boolean } = {}) => {
      const body: { force?: boolean; shops?: string[] } = {};
      if (opts.force) body.force = true;
      if (selectedShops && selectedShops.length > 0) body.shops = selectedShops;
      return api.post(`/goals/${id}/optimize-discounts/`, body);
    },
    onMutate: () => { setOptimizing(true); setTimeoutError(false); },
    onSuccess: (res) => {
      if (res.data.data?.swaps) {
        setOptimizing(false);
        setShowOptimization(true);
        queryClient.invalidateQueries({ queryKey: ['plan', id] });
      } else {
        let resolved = false;
        const poll = setInterval(async () => {
          const check = await api.get(`/goals/${id}/optimize-discounts/`);
          if (check.data.data?.ready) {
            resolved = true;
            clearInterval(poll);
            setOptimizing(false);
            setShowOptimization(true);
            queryClient.invalidateQueries({ queryKey: ['plan', id] });
          }
        }, 3000);
        setTimeout(() => {
          clearInterval(poll);
          if (!resolved) {
            setTimeoutError(true);
            setOptimizing(false);
          }
        }, 180000);
      }
    },
    onError: () => setOptimizing(false),
  });

  const applyOptimization = useMutation({
    mutationFn: () => api.post(`/goals/${id}/apply-optimization/`),
    onSuccess: () => {
      setShowOptimization(false);
      queryClient.invalidateQueries({ queryKey: ['plan', id] });
    },
  });

  if (isLoading || !goalDetail) return <LoadingScreen message="Loading shopping list..." />;

  const plan = goalDetail.dietary_plan;
  if (!plan) return <LoadingScreen message="Loading shopping list..." />;

  const rawList = plan.shopping_list || [];
  const isCrossStore = rawList && !Array.isArray(rawList) && rawList.by_store;
  const items: any[] = isCrossStore ? (rawList.items || []) : rawList;
  const byStore: any[] | null = isCrossStore ? rawList.by_store : null;
  const availableShops: Array<{ code: string; name: string }> = shopsData || [];
  const discountOpt = plan.discount_optimization;
  const hasSwaps = discountOpt?.swaps?.length > 0;
  const isApplied = plan.discount_optimization_applied;
  const totalItems = items.length;
  const checkedCount = checked.size;

  const toggleItem = (key: string) => {
    setChecked(prev => {
      const next = new Set(prev);
      next.has(key) ? next.delete(key) : next.add(key);
      localStorage.setItem(storageKey, JSON.stringify([...next]));
      return next;
    });
  };

  const handlePrint = () => window.print();

  return (
    <MainLayout>
      <div className="max-w-3xl mx-auto px-6 py-12 w-full">
        <button
          onClick={() => navigate(`/plan/${id}`)}
          className="flex items-center gap-2 text-zinc-300 hover:text-white text-xs font-black uppercase tracking-widest mb-12 transition-colors print:hidden"
        >
          <ArrowLeft size={16} /> Zpět na plán
        </button>

        <header className="mb-16 flex flex-col sm:flex-row sm:items-end justify-between gap-8 text-left">
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

        {/* Discount optimization button */}
        {!isApplied && !showOptimization && (
          <div className="mb-8 print:hidden space-y-3">
            <button
              onClick={() => hasSwaps ? setShowOptimization(true) : triggerOptimization.mutate({})}
              disabled={optimizing}
              className="w-full flex items-center justify-center gap-3 h-14 bg-amber-500/10 border border-amber-500/20 text-amber-400 hover:bg-amber-500/20 rounded-xl font-black uppercase text-[10px] tracking-widest transition-all disabled:opacity-50"
            >
              {optimizing ? (
                <><Loader2 size={16} className="animate-spin" /> Hledám akční nabídky...</>
              ) : hasSwaps ? (
                <><Percent size={16} /> Zobrazit nalezené slevy ({discountOpt.swaps.length} záměn)</>
              ) : (
                <><Percent size={16} /> Optimalizovat podle akčních nabídek</>
              )}
            </button>
            {!hasSwaps && availableShops.length > 0 && (
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-[10px] font-black text-zinc-400 uppercase tracking-widest">Obchody:</span>
                <button
                  onClick={() => setSelectedShops(null)}
                  className={`text-[10px] font-black uppercase tracking-widest px-3 py-1.5 rounded-full border transition-colors ${
                    !selectedShops || selectedShops.length === 0
                      ? 'bg-amber-500/20 border-amber-500/40 text-amber-300'
                      : 'border-slate-600 text-zinc-300 hover:text-white'
                  }`}
                >
                  Všechny
                </button>
                {availableShops.map(s => {
                  const active = selectedShops?.includes(s.code) ?? false;
                  return (
                    <button
                      key={s.code}
                      onClick={() => setSelectedShops(prev => {
                        const set = new Set(prev || []);
                        set.has(s.code) ? set.delete(s.code) : set.add(s.code);
                        const next = Array.from(set);
                        return next.length === 0 ? null : next;
                      })}
                      className={`text-[10px] font-black uppercase tracking-widest px-3 py-1.5 rounded-full border transition-colors ${
                        active
                          ? 'bg-amber-500/20 border-amber-500/40 text-amber-300'
                          : 'border-slate-600 text-zinc-300 hover:text-white'
                      }`}
                    >
                      {s.name}
                    </button>
                  );
                })}
              </div>
            )}
            {timeoutError && (
              <div className="flex items-center gap-3 p-4 bg-amber-500/5 border border-amber-500/20 rounded-xl">
                <AlertTriangle size={18} className="text-amber-400 shrink-0" />
                <p className="text-xs font-bold text-amber-300">
                  Optimalizace trvá déle než obvykle. Zkuste to za chvíli znovu.
                </p>
              </div>
            )}
          </div>
        )}

        {isApplied && (
          <Card className="p-5 mb-8 border-emerald-500/20 text-left print:hidden">
            <div className="flex items-center gap-3">
              <Check size={20} className="text-emerald-500 shrink-0" />
              <div>
                <p className="text-sm font-black text-emerald-400 uppercase tracking-tight italic">Slevová optimalizace aplikována</p>
                <p className="text-[10px] font-bold text-zinc-400 mt-0.5">
                  Ušetřili jste {discountOpt?.total_saving} {plan.currency} díky akčním nabídkám
                </p>
              </div>
            </div>
          </Card>
        )}

        {/* Discount optimization comparison panel */}
        {showOptimization && hasSwaps && !isApplied && (
          <Card className="p-8 mb-8 border-amber-500/20 text-left print:hidden">
            <div className="flex items-center justify-between mb-6">
              <div className="flex items-center gap-3">
                <Percent size={20} className="text-amber-400" />
                <div>
                  <p className="text-sm font-black text-amber-400 uppercase tracking-tight italic">
                    Nalezeno {discountOpt.swaps.length} záměn
                  </p>
                  <p className="text-[10px] font-bold text-zinc-400 mt-0.5">
                    Celková úspora: {discountOpt.total_saving} {plan.currency}
                  </p>
                </div>
              </div>
              <button onClick={() => setShowOptimization(false)} className="text-zinc-400 hover:text-white transition-colors">
                <X size={20} />
              </button>
            </div>

            <div className="space-y-3 mb-8 max-h-[400px] overflow-y-auto">
              {discountOpt.swaps.map((swap: any, idx: number) => {
                const shopName = availableShops.find(s => s.code === swap.source_shop)?.name || swap.source_shop;
                return (
                  <div key={idx} className="flex items-center gap-4 p-4 bg-black/30 rounded-xl">
                    <div className="flex-1 min-w-0">
                      <p className="text-xs font-black text-zinc-300 line-through truncate">{swap.original_ingredient}</p>
                      <p className="text-xs font-black text-zinc-200 mt-0.5">{swap.original_price} {plan.currency}</p>
                    </div>
                    <ArrowRight size={16} className="text-amber-400 shrink-0" />
                    <div className="flex-1 min-w-0">
                      <p className="text-xs font-black text-white truncate">{swap.replacement_product}</p>
                      <div className="flex items-center gap-2 mt-0.5 flex-wrap">
                        <p className="text-xs font-black text-emerald-400">{swap.replacement_price} {plan.currency}</p>
                        {swap.source_shop && (
                          <span className="inline-flex items-center gap-1 text-[9px] font-black uppercase tracking-wider px-2 py-0.5 rounded-full border bg-blue-500/10 text-blue-400 border-blue-500/20">
                            <Store size={9} /> {shopName}
                          </span>
                        )}
                        {swap.discount_confirmed === true && (
                          <span className="inline-flex items-center gap-1 text-[9px] font-black uppercase tracking-wider px-2 py-0.5 rounded-full border bg-emerald-500/10 text-emerald-400 border-emerald-500/20" title="Potvrzená akce z letáku">
                            <Tag size={9} /> Akce
                          </span>
                        )}
                      </div>
                    </div>
                    <span className="text-[10px] font-black text-emerald-400 bg-emerald-500/10 px-2 py-1 rounded-lg shrink-0">
                      -{swap.saving} {plan.currency}
                    </span>
                  </div>
                );
              })}
            </div>

            <div className="flex gap-3">
              <button
                onClick={() => applyOptimization.mutate()}
                disabled={applyOptimization.isPending}
                className="flex-1 flex items-center justify-center gap-3 h-14 bg-emerald-600 hover:bg-emerald-500 text-white rounded-xl font-black uppercase text-[10px] tracking-widest transition-all disabled:opacity-50"
              >
                {applyOptimization.isPending ? (
                  <><Loader2 size={16} className="animate-spin" /> Aplikuji...</>
                ) : (
                  <><Check size={16} /> Použít slevy (ušetřit {discountOpt.total_saving} {plan.currency})</>
                )}
              </button>
              <button
                onClick={() => setShowOptimization(false)}
                className="px-6 h-14 border border-slate-600 text-zinc-300 hover:text-white rounded-xl font-black uppercase text-[10px] tracking-widest transition-all"
              >
                Ponechat původní
              </button>
            </div>
          </Card>
        )}

        {/* No discounts found message */}
        {showOptimization && discountOpt && !hasSwaps && (
          <Card className="p-6 mb-8 border-amber-500/30 text-left print:hidden">
            <div className="flex items-start gap-4">
              <Percent size={22} className="text-amber-400 shrink-0 mt-0.5" />
              <div className="flex-1">
                <p className="text-sm font-black text-amber-300 uppercase tracking-tight italic">
                  Žádné slevy nenalezeny
                </p>
                <p className="text-xs font-bold text-zinc-300 mt-2">
                  {discountOpt.message === 'no_discounts'
                    ? 'V tuto chvíli nejsou v databázi žádné akční nabídky pro vybrané obchody.'
                    : 'Nenalezeny žádné vhodné záměny pro aktuální plán.'}
                </p>
                {discountOpt.shops_queried && discountOpt.shops_queried.length > 0 && (
                  <p className="text-[10px] font-bold text-zinc-400 mt-2 uppercase tracking-widest">
                    Prohledáno: {discountOpt.shops_queried.join(', ')}
                  </p>
                )}
                <div className="flex gap-3 mt-4">
                  <button
                    onClick={() => triggerOptimization.mutate({ force: true })}
                    disabled={optimizing}
                    className="flex items-center gap-2 px-4 h-10 bg-amber-500/10 border border-amber-500/30 text-amber-300 hover:bg-amber-500/20 rounded-lg font-black uppercase text-[10px] tracking-widest transition-all disabled:opacity-50"
                  >
                    {optimizing ? (
                      <><Loader2 size={14} className="animate-spin" /> Aktualizuji...</>
                    ) : (
                      <><RefreshCw size={14} /> Načíst znovu</>
                    )}
                  </button>
                  <button
                    onClick={() => setShowOptimization(false)}
                    className="px-4 h-10 text-zinc-300 hover:text-white font-black uppercase text-[10px] tracking-widest transition-colors"
                  >
                    Zavřít
                  </button>
                </div>
              </div>
            </div>
          </Card>
        )}

        {/* Cross-store savings banner */}
        {isCrossStore && rawList.savings_vs_single > 0 && (
          <Card className="p-5 mb-8 border-emerald-500/20 text-left">
            <div className="flex items-center gap-3">
              <TrendingDown size={20} className="text-emerald-500 shrink-0" />
              <div>
                <p className="text-sm font-black text-emerald-400 uppercase tracking-tight italic">
                  Ušetříte {rawList.savings_vs_single} {plan.currency}
                </p>
                <p className="text-[10px] font-bold text-zinc-400 mt-0.5">
                  oproti nákupu v jednom obchodu ({rawList.best_single_store}) &middot; {rawList.num_stores} obchody
                </p>
              </div>
            </div>
          </Card>
        )}

        {/* Cross-store grouped view */}
        {byStore ? (
          <div className="space-y-10">
            {byStore.map((storeGroup: any) => {
              const storeKey = storeGroup.store || 'unavailable';
              return (
                <div key={storeKey}>
                  <div className="flex items-center justify-between mb-4">
                    <div className="flex items-center gap-2">
                      <Store size={16} className="text-zinc-300" />
                      <h2 className="text-sm font-black text-white uppercase tracking-widest italic">
                        {storeGroup.store_name}
                      </h2>
                    </div>
                    {storeGroup.subtotal > 0 && (
                      <span className="text-sm font-black text-emerald-500 tabular-nums">
                        {storeGroup.subtotal} {plan.currency}
                      </span>
                    )}
                  </div>
                  <div className="space-y-3">
                    {storeGroup.items.map((item: any, idx: number) => {
                      const itemKey = `${storeKey}-${idx}`;
                      return (
                        <ShoppingItem
                          key={itemKey}
                          item={item}
                          done={checked.has(itemKey)}
                          onToggle={() => toggleItem(itemKey)}
                        />
                      );
                    })}
                  </div>
                </div>
              );
            })}
          </div>
        ) : (
          /* Single-store flat list, split into Groceries and Pantry sections */
          (() => {
            const groceries = items.filter((i: any) => !isStapleItem(i));
            const pantry = items.filter((i: any) => isStapleItem(i));
            return (
              <div className="space-y-10">
                <div className="space-y-3">
                  {pantry.length > 0 && (
                    <h2 className="text-xs font-black text-zinc-300 uppercase tracking-widest italic mb-3">
                      Potraviny
                    </h2>
                  )}
                  {groceries.map((item: any) => {
                    const itemKey = `g-${items.indexOf(item)}`;
                    return (
                      <ShoppingItem
                        key={itemKey}
                        item={item}
                        done={checked.has(itemKey)}
                        onToggle={() => toggleItem(itemKey)}
                      />
                    );
                  })}
                </div>
                {pantry.length > 0 && (
                  <div className="space-y-3">
                    <div className="mb-3">
                      <h2 className="text-xs font-black text-zinc-300 uppercase tracking-widest italic">
                        Spíž · pouze část balení
                      </h2>
                      <p className="text-[10px] font-bold text-zinc-400 italic mt-1">
                        Tyto suroviny většinou už máte doma. Účtujeme jen tu část, kterou skutečně použijete.
                      </p>
                    </div>
                    {pantry.map((item: any) => {
                      const itemKey = `p-${items.indexOf(item)}`;
                      return (
                        <ShoppingItem
                          key={itemKey}
                          item={item}
                          done={checked.has(itemKey)}
                          onToggle={() => toggleItem(itemKey)}
                          staple
                        />
                      );
                    })}
                  </div>
                )}
              </div>
            );
          })()
        )}

        {/* Total */}
        {(() => {
          const estimatedCount = items.filter((i: any) => i.estimated).length;
          const unavailableCount = items.filter((i: any) => i.price_source === 'not_available').length;
          const hasEstimates = estimatedCount > 0 || unavailableCount > 0;
          const pantryPrice = plan.pantry_price != null ? Number(plan.pantry_price) : 0;
          return (
            <Card className="p-8 mt-10 text-left">
              <div className="flex justify-between items-center">
                <div className="flex items-center gap-3">
                  <ShoppingCart size={22} className="text-emerald-500" />
                  <div>
                    <p className="text-xs font-black text-zinc-400 uppercase tracking-[0.2em] italic">
                      {hasEstimates ? 'Odhadovaná cena celkem' : 'Cena celkem'}
                    </p>
                    {pantryPrice > 0 && (
                      <p className="text-[10px] text-zinc-300 font-bold mt-0.5">
                        Včetně {pantryPrice.toFixed(2)} {plan.currency} za poměrnou část spíže
                      </p>
                    )}
                    {unavailableCount > 0 && (
                      <p className="text-[10px] text-amber-500/80 font-bold mt-0.5">
                        {unavailableCount} {unavailableCount === 1 ? 'položka' : 'položek'} bez ceny
                      </p>
                    )}
                  </div>
                </div>
                <p className="text-4xl font-black text-white italic tracking-tighter">
                  {plan.total_price}<span className="text-emerald-500 text-base not-italic ml-2 uppercase">{plan.currency}</span>
                </p>
              </div>
            </Card>
          );
        })()}

        {/* Price disclaimer + feedback */}
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
                    Skutečná cena nákupu ({plan.currency})
                  </label>
                  <input
                    type="number"
                    min="0"
                    step="0.01"
                    value={actualTotal}
                    onChange={e => setActualTotal(e.target.value)}
                    placeholder={plan.total_price?.toString() || '0'}
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
