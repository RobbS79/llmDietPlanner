import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery, useQueries, useMutation, useQueryClient } from '@tanstack/react-query';
import { Plus, MapPin, ChevronRight, Box, ArrowRight, Sparkles, Wallet, Trash2, X, Check } from 'lucide-react';
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

  const costMap = new Map<number, { total: number; perDay: number | null; currency: string; days: number }>();
  goalDetails.forEach((q: any) => {
    // Use the new pro-rated food-cost ESTIMATE; legacy total_price is gone.
    const estimate = q.data?.dietary_plan?.pricing?.estimate;
    if (estimate && estimate.total > 0) {
      costMap.set(q.data.id, {
        total: estimate.total,
        perDay: estimate.per_day ?? null,
        currency: estimate.currency || 'CZK',
        days: q.data.num_days || 7,
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
            <h1 className="text-5xl font-black font-display text-ink tracking-tighter uppercase italic leading-none">
              Vaše<br /><span className="text-paprika not-italic text-6xl">plány.</span>
            </h1>
            {profile && (
              <div className="flex items-center gap-2 pt-2">
                <Sparkles size={14} className="text-green" />
                <span className="text-[10px] font-black uppercase tracking-widest text-muted">
                  {profile.free_generations_remaining} plánů zdarma zbývá
                </span>
              </div>
            )}
          </div>
          <div className="flex items-center gap-3 shrink-0">
            {!selectMode && goals?.length > 0 && (
              <button
                onClick={() => setSelectMode(true)}
                className="h-14 px-6 bg-kraft text-ink font-black uppercase text-[10px] tracking-[0.2em] rounded-xl hover:bg-line transition-all flex items-center gap-3 border border-line"
              >
                <Trash2 size={16} strokeWidth={3} /> Smazat
              </button>
            )}
            <button
              onClick={() => navigate('/create')}
              className="h-14 px-10 bg-green text-white font-black uppercase text-[10px] tracking-[0.2em] rounded-xl hover:bg-green-mid transition-all shadow-2xl active:scale-95 flex items-center gap-3"
            >
              <Plus size={20} strokeWidth={4} /> Nový plán
            </button>
          </div>
        </header>

        {selectMode && (
          <div className="mb-8 flex items-center justify-between bg-card border border-line rounded-2xl px-6 py-4">
            <div className="flex items-center gap-4">
              <button
                onClick={exitSelectMode}
                className="w-10 h-10 rounded-xl bg-kraft hover:bg-line flex items-center justify-center transition-colors"
              >
                <X size={18} className="text-ink" />
              </button>
              <span className="text-sm font-bold text-muted">
                {selected.size} {selected.size === 1 ? 'plán vybrán' : selected.size >= 2 && selected.size <= 4 ? 'plány vybrány' : 'plánů vybráno'}
              </span>
              <button
                onClick={selectAll}
                className="text-[10px] font-black uppercase tracking-widest text-green hover:text-green-mid transition-colors"
              >
                {goals && selected.size === goals.length ? 'Zrušit vše' : 'Vybrat vše'}
              </button>
            </div>
            <button
              onClick={handleDelete}
              disabled={selected.size === 0 || deleteMutation.isPending}
              className="h-10 px-6 bg-paprika text-white font-black uppercase text-[10px] tracking-[0.2em] rounded-xl hover:bg-paprika-strong transition-all flex items-center gap-2 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              <Trash2 size={14} strokeWidth={3} />
              {deleteMutation.isPending ? 'Mažu...' : `Smazat (${selected.size})`}
            </button>
          </div>
        )}

        {latestCost && !selectMode && (() => {
          const dailyCost = Math.round(latestCost.perDay ?? latestCost.total / latestCost.days);
          return (
            <div className="mb-10 bg-green-soft border border-green/40 rounded-2xl p-6 sm:p-8">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-6">
                <div className="flex items-center gap-5">
                  <div className="w-14 h-14 rounded-2xl bg-green-soft border border-green/40 flex items-center justify-center shrink-0">
                    <Wallet size={24} className="text-green" />
                  </div>
                  <div>
                    {/* EN gloss: "Latest plan — food cost per day" — per-day per-person is the hero */}
                    <p className="text-[9px] font-black text-green uppercase tracking-[0.3em] mb-1">Poslední plán — cena jídla na den</p>
                    <p className="text-3xl sm:text-4xl font-black text-ink italic tracking-tighter leading-none tabular-nums">
                      ~{dailyCost.toLocaleString('cs-CZ')} <span className="text-green text-sm not-italic uppercase">{latestCost.currency}</span>
                      {/* EN gloss: "/ day · per person" */}
                      <span className="text-muted text-xs not-italic ml-2 lowercase">/ den &middot; na osobu</span>
                    </p>
                    {/* EN gloss: "approx. {total} {currency} total for the plan — estimate" */}
                    <p className="text-xs text-muted font-bold mt-1 italic tabular-nums">~{Math.round(latestCost.total).toLocaleString('cs-CZ')} {latestCost.currency} celkem &middot; odhad</p>
                  </div>
                </div>
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
            <div className="col-span-full py-40 flex flex-col items-center justify-center border border-line rounded-3xl bg-kraft/40 text-center">
              <Box size={64} className="text-muted mb-8" />
              <p className="text-muted font-bold uppercase tracking-widest text-xs mb-4 italic">Zatím žádné jídelníčky</p>
              <p className="text-muted text-xs mb-10">Vytvořte svůj první plán a zjistíte, kolik ušetříte.</p>
              <button onClick={() => navigate('/create')} className="text-green font-black uppercase text-[10px] tracking-widest hover:underline flex items-center gap-2">
                Vytvořit první plán <ArrowRight size={14} />
              </button>
            </div>
          ) : (
            goals?.map((goal: any) => (
              <Card
                key={goal.id}
                className={`p-8 hover:bg-kraft cursor-pointer group flex flex-col h-full text-left transition-all ${
                  selectMode && selected.has(goal.id)
                    ? 'border-green bg-green-soft'
                    : 'hover:border-green/40'
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
                          ? 'bg-green border-green/40'
                          : 'border-line bg-transparent'
                      }`}>
                        {selected.has(goal.id) && <Check size={14} strokeWidth={3} className="text-white" />}
                      </div>
                    )}
                    <Badge variant={goal.status === 'completed' ? 'emerald' : goal.status === 'failed' ? 'rose' : 'blue'}>
                      {goal.status.replace(/_/g, ' ')}
                    </Badge>
                  </div>
                  <span className="text-[10px] font-black text-muted uppercase tracking-widest">
                    #{goal.id}
                  </span>
                </div>

                <h3 className="text-2xl font-black text-ink mb-8 leading-tight uppercase tracking-tight italic group-hover:text-green-mid transition-colors line-clamp-3">
                  {goal.prompt}
                </h3>

                {costMap.has(goal.id) && (() => {
                  const c = costMap.get(goal.id)!;
                  const perDay = Math.round(c.perDay ?? c.total / c.days);
                  return (
                    <div className="mb-4 bg-green-soft border border-green/40 rounded-xl px-4 py-3 flex items-center justify-between">
                      {/* EN gloss: "Estimate · per day" */}
                      <span className="text-[9px] font-black text-muted uppercase tracking-widest">Odhad &middot; na den</span>
                      <span className="text-lg font-black text-green italic tracking-tighter tabular-nums">
                        ~{perDay.toLocaleString('cs-CZ')} {c.currency}
                      </span>
                    </div>
                  );
                })()}

                <div className="mt-auto pt-8 flex flex-col gap-4 border-t border-line">
                  <div className="flex items-center justify-between text-[10px] font-bold uppercase tracking-widest text-muted italic">
                    <span className="flex items-center gap-2"><MapPin size={12} className="text-green" /> {goal.city}</span>
                    <span className="bg-kraft px-2 py-0.5 rounded text-ink">{goal.num_days} dní</span>
                  </div>
                  <div className="flex justify-between items-center text-[9px] font-black text-muted uppercase tracking-[0.4em] pt-1">
                    <span>{new Date(goal.created_at).toLocaleDateString()}</span>
                    <ChevronRight size={16} className="group-hover:translate-x-1 transition-transform group-hover:text-green" />
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
