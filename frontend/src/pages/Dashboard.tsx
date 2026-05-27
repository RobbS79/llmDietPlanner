import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery, useQueries, useMutation, useQueryClient } from '@tanstack/react-query';
import { Plus, MapPin, ChevronRight, Box, ArrowRight, Sparkles, Wallet, TrendingDown, Trash2, X, Check } from 'lucide-react';
import { api } from '@/lib/api';
import { MainLayout } from '@/components/layout/MainLayout';
import { Card } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { CardSkeleton } from '@/components/ui/Skeleton';

export const Dashboard = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [selectMode, setSelectMode] = useState(false);
  const [selected, setSelected] = useState<Set<number>>(new Set());

  const { data: goals, isLoading } = useQuery({
    queryKey: ['goals'],
    queryFn: () => api.get('/goals/list/').then(res => res.data.data),
  });
  const { data: profile } = useQuery({
    queryKey: ['profile'],
    queryFn: () => api.get('/auth/profile/').then(res => res.data.data),
  });

  const completedGoalIds = (goals || [])
    .filter((g: any) => g.status === 'completed')
    .slice(0, 6)
    .map((g: any) => g.id);

  const goalDetails = useQueries({
    queries: completedGoalIds.map((gid: number) => ({
      queryKey: ['plan', gid],
      queryFn: () => api.get(`/goals/${gid}/`).then(res => res.data.data),
      staleTime: 5 * 60 * 1000,
    })),
  });

  const costMap = new Map<number, { total: number; currency: string; days: number; shop: string }>();
  goalDetails.forEach((q: any) => {
    if (q.data?.dietary_plan?.total_price) {
      costMap.set(q.data.id, {
        total: parseFloat(q.data.dietary_plan.total_price),
        currency: q.data.dietary_plan.currency || 'CZK',
        days: q.data.num_days || 7,
        shop: q.data.shop || '',
      });
    }
  });

  const latestCost = completedGoalIds.length > 0 ? costMap.get(completedGoalIds[0]) : undefined;

  const deleteMutation = useMutation({
    mutationFn: (goalIds: number[]) => api.post('/goals/bulk-delete/', { goal_ids: goalIds }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['goals'] });
      setSelected(new Set());
      setSelectMode(false);
    },
  });

  const toggleSelect = (id: number) => {
    setSelected(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const selectAll = () => {
    if (!goals) return;
    if (selected.size === goals.length) {
      setSelected(new Set());
    } else {
      setSelected(new Set(goals.map((g: any) => g.id)));
    }
  };

  const exitSelectMode = () => {
    setSelectMode(false);
    setSelected(new Set());
  };

  const handleDelete = () => {
    if (selected.size === 0) return;
    const msg = selected.size === 1
      ? 'Opravdu chcete smazat tento plán?'
      : `Opravdu chcete smazat ${selected.size} plánů?`;
    if (!window.confirm(msg)) return;
    deleteMutation.mutate(Array.from(selected));
  };

  return (
    <MainLayout>
      <div className="max-w-7xl mx-auto px-6 py-12 w-full">
        <header className="flex flex-col sm:flex-row sm:items-end justify-between gap-8 mb-16 text-left">
          <div className="space-y-3">
            <h1 className="text-5xl font-black text-white tracking-tighter uppercase italic leading-none">
              Vaše<br /><span className="text-emerald-500 not-italic text-6xl">plány.</span>
            </h1>
            {profile && (
              <div className="flex items-center gap-2 pt-2">
                <Sparkles size={14} className="text-emerald-500" />
                <span className="text-[10px] font-black uppercase tracking-widest text-zinc-500">
                  {profile.free_generations_remaining} plánů zdarma zbývá
                </span>
              </div>
            )}
          </div>
          <div className="flex items-center gap-3 shrink-0">
            {!selectMode && goals?.length > 0 && (
              <button
                onClick={() => setSelectMode(true)}
                className="h-14 px-6 bg-zinc-800 text-zinc-300 font-black uppercase text-[10px] tracking-[0.2em] rounded-xl hover:bg-zinc-700 transition-all flex items-center gap-3 border border-zinc-700"
              >
                <Trash2 size={16} strokeWidth={3} /> Smazat
              </button>
            )}
            <button
              onClick={() => navigate('/create')}
              className="h-14 px-10 bg-white text-black font-black uppercase text-[10px] tracking-[0.2em] rounded-xl hover:bg-zinc-200 transition-all shadow-2xl active:scale-95 flex items-center gap-3"
            >
              <Plus size={20} strokeWidth={4} /> Nový plán
            </button>
          </div>
        </header>

        {selectMode && (
          <div className="mb-8 flex items-center justify-between bg-zinc-900 border border-zinc-700 rounded-2xl px-6 py-4">
            <div className="flex items-center gap-4">
              <button
                onClick={exitSelectMode}
                className="w-10 h-10 rounded-xl bg-zinc-800 hover:bg-zinc-700 flex items-center justify-center transition-colors"
              >
                <X size={18} className="text-zinc-400" />
              </button>
              <span className="text-sm font-bold text-zinc-300">
                {selected.size} {selected.size === 1 ? 'plán vybrán' : selected.size >= 2 && selected.size <= 4 ? 'plány vybrány' : 'plánů vybráno'}
              </span>
              <button
                onClick={selectAll}
                className="text-[10px] font-black uppercase tracking-widest text-emerald-500 hover:text-emerald-400 transition-colors"
              >
                {goals && selected.size === goals.length ? 'Zrušit vše' : 'Vybrat vše'}
              </button>
            </div>
            <button
              onClick={handleDelete}
              disabled={selected.size === 0 || deleteMutation.isPending}
              className="h-10 px-6 bg-red-600 text-white font-black uppercase text-[10px] tracking-[0.2em] rounded-xl hover:bg-red-500 transition-all flex items-center gap-2 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              <Trash2 size={14} strokeWidth={3} />
              {deleteMutation.isPending ? 'Mažu...' : `Smazat (${selected.size})`}
            </button>
          </div>
        )}

        {latestCost && !selectMode && (() => {
          const weeklyCost = Math.round(latestCost.total / latestCost.days * 7);
          const avgCzWeekly = 1850;
          const savings = Math.max(0, avgCzWeekly - weeklyCost);
          const shopName = latestCost.shop === 'ROHLIK' ? 'Rohlik.cz' : latestCost.shop === 'KOSIK' ? 'Kosik.cz' : latestCost.shop || 'obchodu';
          return (
            <div className="mb-10 bg-gradient-to-r from-emerald-600/10 to-teal-600/5 border border-emerald-500/20 rounded-2xl p-6 sm:p-8">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-6">
                <div className="flex items-center gap-5">
                  <div className="w-14 h-14 rounded-2xl bg-emerald-600/10 border border-emerald-500/20 flex items-center justify-center shrink-0">
                    <Wallet size={24} className="text-emerald-400" />
                  </div>
                  <div>
                    <p className="text-[9px] font-black text-emerald-400 uppercase tracking-[0.3em] mb-1">Poslední plán — týdenní náklady</p>
                    <p className="text-3xl sm:text-4xl font-black text-white italic tracking-tighter leading-none">
                      {weeklyCost.toLocaleString('cs-CZ')} <span className="text-emerald-500 text-sm not-italic uppercase">{latestCost.currency}/týden</span>
                    </p>
                    <p className="text-xs text-zinc-500 font-bold mt-1 italic">na {shopName}</p>
                  </div>
                </div>
                {savings > 0 && (
                  <div className="flex items-center gap-3 bg-emerald-500/10 border border-emerald-500/20 rounded-xl px-5 py-3">
                    <TrendingDown size={18} className="text-emerald-400" />
                    <div>
                      <p className="text-lg font-black text-emerald-400 italic tracking-tighter leading-none">-{savings.toLocaleString('cs-CZ')} {latestCost.currency}/týden</p>
                      <p className="text-[9px] font-black text-zinc-500 uppercase tracking-widest">vs. průměrný český nákup</p>
                    </div>
                  </div>
                )}
              </div>
            </div>
          );
        })()}

        <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
          {isLoading ? (
            <>
              <CardSkeleton />
              <CardSkeleton />
              <CardSkeleton />
            </>
          ) : goals?.length === 0 ? (
            <div className="col-span-full py-40 flex flex-col items-center justify-center border border-zinc-800 rounded-3xl bg-zinc-900/10 text-center">
              <Box size={64} className="text-zinc-500 mb-8" />
              <p className="text-zinc-600 font-bold uppercase tracking-widest text-xs mb-4 italic">Zatím žádné jídelníčky</p>
              <p className="text-zinc-500 text-xs mb-10">Vytvořte svůj první plán a zjistíte, kolik ušetříte.</p>
              <button onClick={() => navigate('/create')} className="text-emerald-500 font-black uppercase text-[10px] tracking-widest hover:underline flex items-center gap-2">
                Vytvořit první plán <ArrowRight size={14} />
              </button>
            </div>
          ) : (
            goals?.map((goal: any) => (
              <Card
                key={goal.id}
                className={`p-8 hover:bg-zinc-900 cursor-pointer group flex flex-col h-full text-left transition-all ${
                  selectMode && selected.has(goal.id)
                    ? 'border-emerald-500 bg-emerald-500/5'
                    : 'hover:border-emerald-500/30'
                }`}
                onClick={() => {
                  if (selectMode) {
                    toggleSelect(goal.id);
                  } else {
                    navigate(`/plan/${goal.id}`);
                  }
                }}
              >
                <div className="flex justify-between items-start mb-12">
                  <div className="flex items-center gap-3">
                    {selectMode && (
                      <div className={`w-6 h-6 rounded-lg border-2 flex items-center justify-center transition-all shrink-0 ${
                        selected.has(goal.id)
                          ? 'bg-emerald-500 border-emerald-500'
                          : 'border-zinc-600 bg-transparent'
                      }`}>
                        {selected.has(goal.id) && <Check size={14} strokeWidth={3} className="text-black" />}
                      </div>
                    )}
                    <Badge variant={goal.status === 'completed' ? 'emerald' : goal.status === 'failed' ? 'rose' : 'blue'}>
                      {goal.status.replace(/_/g, ' ')}
                    </Badge>
                  </div>
                  <span className="text-[10px] font-black text-zinc-500 uppercase tracking-widest">
                    #{goal.id}
                  </span>
                </div>

                <h3 className="text-2xl font-black text-white mb-8 leading-tight uppercase tracking-tight italic group-hover:text-emerald-400 transition-colors line-clamp-3">
                  {goal.prompt}
                </h3>

                {costMap.has(goal.id) && (
                  <div className="mb-4 bg-emerald-500/5 border border-emerald-500/10 rounded-xl px-4 py-3 flex items-center justify-between">
                    <span className="text-[9px] font-black text-zinc-500 uppercase tracking-widest">Celkem</span>
                    <span className="text-lg font-black text-emerald-400 italic tracking-tighter">
                      {Math.round(costMap.get(goal.id)!.total).toLocaleString('cs-CZ')} {costMap.get(goal.id)!.currency}
                    </span>
                  </div>
                )}

                <div className="mt-auto pt-8 flex flex-col gap-4 border-t border-zinc-800">
                  <div className="flex items-center justify-between text-[10px] font-bold uppercase tracking-widest text-zinc-500 italic">
                    <span className="flex items-center gap-2"><MapPin size={12} className="text-emerald-500" /> {goal.city}</span>
                    <span className="bg-zinc-800 px-2 py-0.5 rounded text-zinc-400">{goal.num_days} dní</span>
                  </div>
                  <div className="flex justify-between items-center text-[9px] font-black text-zinc-500 uppercase tracking-[0.4em] pt-1">
                    <span>{new Date(goal.created_at).toLocaleDateString()}</span>
                    <ChevronRight size={16} className="group-hover:translate-x-1 transition-transform group-hover:text-emerald-500" />
                  </div>
                </div>
              </Card>
            ))
          )}
        </div>
      </div>
    </MainLayout>
  );
};
