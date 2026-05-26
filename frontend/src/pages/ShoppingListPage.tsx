import { useParams, useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { ArrowLeft, ShoppingCart, Printer, Check, Tag, Store, Sparkles, Clock, HelpCircle } from 'lucide-react';
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
  not_available: { label: 'Nedostupná', color: 'bg-zinc-500/10 text-zinc-500 border-zinc-500/20', icon: HelpCircle },
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

export const ShoppingListPage = () => {
  const { id } = useParams();
  const navigate = useNavigate();

  const storageKey = `shopping-checked-${id}`;
  const [checked, setChecked] = useState<Set<number>>(() => {
    const saved = localStorage.getItem(storageKey);
    return saved ? new Set(JSON.parse(saved)) : new Set();
  });

  const { data: goalDetail, isLoading } = useQuery({
    queryKey: ['plan', id],
    queryFn: () => api.get(`/goals/${id}/`).then(res => res.data.data),
  });

  if (isLoading || !goalDetail) return <LoadingScreen message="Loading shopping list..." />;

  const plan = goalDetail.dietary_plan;
  if (!plan) return <LoadingScreen message="Loading shopping list..." />;

  const items = plan.shopping_list || [];
  const toggleItem = (idx: number) => {
    setChecked(prev => {
      const next = new Set(prev);
      next.has(idx) ? next.delete(idx) : next.add(idx);
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
          className="flex items-center gap-2 text-zinc-500 hover:text-white text-xs font-black uppercase tracking-widest mb-12 transition-colors print:hidden"
        >
          <ArrowLeft size={16} /> Zpět na plán
        </button>

        <header className="mb-16 flex flex-col sm:flex-row sm:items-end justify-between gap-8 text-left">
          <div className="space-y-4">
            <Badge variant="emerald">Nákupní seznam</Badge>
            <h1 className="text-5xl sm:text-6xl font-black text-white tracking-tighter uppercase italic leading-[0.9]">
              Váš seznam<span className="text-emerald-500 not-italic">.</span>
            </h1>
            <p className="text-zinc-600 text-sm font-bold italic">
              {items.length} položek &middot; {checked.size} odškrtnuto
            </p>
          </div>
          <button
            onClick={handlePrint}
            className="flex items-center gap-2 bg-zinc-900 border border-zinc-800 text-zinc-400 hover:text-white px-6 h-12 rounded-xl font-black uppercase text-[10px] tracking-[0.15em] transition-colors print:hidden"
          >
            <Printer size={16} /> Tisknout
          </button>
        </header>

        <div className="space-y-3">
          {items.map((item: any, idx: number) => {
            const done = checked.has(idx);
            return (
              <Card
                key={idx}
                onClick={() => toggleItem(idx)}
                className={`p-5 cursor-pointer select-none transition-all text-left ${done ? 'opacity-40 border-zinc-800/50' : 'hover:border-emerald-500/20'}`}
              >
                <div className="flex items-center gap-4">
                  <div className={`w-7 h-7 rounded-lg border-2 flex items-center justify-center shrink-0 transition-colors ${done ? 'bg-emerald-600 border-emerald-600' : 'border-zinc-700'}`}>
                    {done && <Check size={16} className="text-white" />}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex justify-between items-start gap-3">
                      <p className={`text-base font-black uppercase tracking-tight italic leading-none truncate ${done ? 'line-through text-zinc-600' : 'text-white'}`}>
                        {item.ingredient}
                      </p>
                      <div className="flex items-center gap-2 shrink-0">
                        {item.original_price != null && item.discount_percentage != null && (
                          <span className="text-[10px] font-bold text-zinc-600 line-through tabular-nums">
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
                        <span className="text-[10px] font-black text-zinc-600 uppercase tracking-widest italic">
                          {item.quantity} {item.unit}
                        </span>
                        <PriceSourceBadge source={item.price_source} detail={item.source_detail} />
                      </div>
                      {item.matched_product_name && (
                        <span className="text-[10px] font-black text-zinc-600 uppercase tracking-widest italic opacity-50 max-w-[180px] truncate text-right">
                          {item.matched_product_name}
                        </span>
                      )}
                    </div>
                  </div>
                </div>
              </Card>
            );
          })}
        </div>

        {/* Total */}
        {(() => {
          const estimatedCount = items.filter((i: any) => i.estimated).length;
          const unavailableCount = items.filter((i: any) => i.price_source === 'not_available').length;
          const hasEstimates = estimatedCount > 0 || unavailableCount > 0;
          return (
            <Card className="p-8 mt-10 text-left">
              <div className="flex justify-between items-center">
                <div className="flex items-center gap-3">
                  <ShoppingCart size={22} className="text-emerald-500" />
                  <div>
                    <p className="text-xs font-black text-zinc-600 uppercase tracking-[0.2em] italic">
                      {hasEstimates ? 'Odhadovaná cena celkem' : 'Cena celkem'}
                    </p>
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
      </div>
    </MainLayout>
  );
};
