import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { AlertCircle, MapPin, Timer, Globe, Download, ShoppingCart, UtensilsCrossed, ArrowRight, List, ChefHat, Flame } from 'lucide-react';
import { api } from '@/lib/api';
import { MainLayout } from '@/components/layout/MainLayout';
import { Card } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { LoadingScreen } from '@/components/ui/LoadingScreen';

const MEAL_LABELS: Record<string, string> = {
  breakfast: 'Breakfast',
  lunch: 'Lunch',
  dinner: 'Dinner',
};

function exportPlanAsText(goalDetail: any, plan: any) {
  const lines: string[] = [];
  lines.push(`MEAL PLAN — ${goalDetail.city}, ${goalDetail.num_days} Days`);
  lines.push(`Generated: ${new Date().toLocaleDateString()}`);
  lines.push('');

  plan.days?.forEach((day: any) => {
    lines.push(`═══ DAY ${day.day_number} ═══`);
    ['breakfast', 'lunch', 'dinner'].forEach(m => {
      if (!day[m]) return;
      lines.push(`  ${m.toUpperCase()}: ${day[m].name}`);
      lines.push(`    ${day[m].description}`);
      const ni = day[m].nutritional_info;
      if (ni) lines.push(`    ${Object.entries(ni).map(([k, v]) => `${k}: ${v}`).join(' | ')}`);
    });
    lines.push('');
  });

  lines.push('═══ SHOPPING LIST ═══');
  plan.shopping_list?.forEach((item: any) => {
    lines.push(`  ${item.ingredient} — ${item.quantity} ${item.unit} — ${item.price} ${item.currency}`);
  });
  lines.push('');
  lines.push(`TOTAL: ${plan.total_price} ${plan.currency}`);

  const blob = new Blob([lines.join('\n')], { type: 'text/plain' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `meal-plan-${goalDetail.city}-${goalDetail.num_days}d.txt`;
  a.click();
  URL.revokeObjectURL(url);
}

function parseNutrition(ni: any) {
  if (!ni) return { kcal: 0, protein: 0, carbs: 0, fat: 0 };
  const parse = (v: any) => parseInt(String(v).replace(/[^\d]/g, '')) || 0;
  return {
    kcal: parse(ni.calories || ni.kcal || ni.Calories || ni.energy || 0),
    protein: parse(ni.protein || ni.Protein || 0),
    carbs: parse(ni.carbs || ni.carbohydrates || ni.Carbs || 0),
    fat: parse(ni.fat || ni.Fat || ni.fats || 0),
  };
}

export const PlanView = () => {
  const { id } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const { data: statusData } = useQuery({
    queryKey: ['taskStatus', id],
    queryFn: () => api.get(`/goals/${id}/task-status/`).then(res => res.data.data),
    refetchInterval: (query: any) =>
      query?.state?.data?.goal_status === 'completed' || query?.state?.data?.goal_status === 'failed' ? false : 2500,
  });

  const { data: goalDetail } = useQuery({
    queryKey: ['plan', id],
    queryFn: () => api.get(`/goals/${id}/`).then(res => res.data.data),
    enabled: statusData?.goal_status === 'completed',
  });

  const { data: mealInstances } = useQuery({
    queryKey: ['mealInstances', id],
    queryFn: () => api.get(`/goals/${id}/meal-instances/`).then(res => res.data.data),
    enabled: statusData?.goal_status === 'completed',
  });

  const cookedSet = new Set(
    (mealInstances || []).filter((mi: any) => mi.is_cooked).map((mi: any) => mi.meal_identifier)
  );

  const toggleCooked = useMutation({
    mutationFn: ({ mealId, isCooked, mealName }: { mealId: string; isCooked: boolean; mealName: string }) =>
      api.patch(`/meals/${mealId}/`, { is_cooked: isCooked, meal_name: mealName }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['mealInstances', id] }),
  });

  if (statusData?.goal_status === 'failed') {
    return (
      <div className="flex-1 flex flex-col items-center justify-center p-12 text-center bg-[#09090b] text-white">
        <div className="w-24 h-24 rounded-3xl bg-rose-500/10 flex items-center justify-center text-rose-500 border border-rose-500/20 mb-10 animate-bounce">
          <AlertCircle size={48} />
        </div>
        <h1 className="text-5xl font-black tracking-tighter uppercase mb-4 leading-none italic">Generation Failed<span className="text-rose-600 not-italic">.</span></h1>
        <p className={`text-zinc-600 max-w-sm font-medium tracking-tight italic opacity-80 leading-relaxed ${statusData?.error_message ? 'mb-4' : 'mb-12'}`}>We couldn't generate your meal plan. Please try again with different parameters.</p>
        {statusData?.error_message && (
          <p className="text-zinc-700 max-w-md mb-12 text-xs font-mono opacity-60 leading-relaxed">{statusData.error_message}</p>
        )}
        <button onClick={() => navigate('/')} className="px-10 h-14 bg-white text-black font-black uppercase text-[10px] tracking-widest rounded-xl shadow-2xl">Back to Plans</button>
      </div>
    );
  }

  if (statusData?.goal_status !== 'completed') {
    return <LoadingScreen message="Generating your personalized meal plan with real store prices..." status={statusData} />;
  }

  const plan = goalDetail?.dietary_plan;
  if (!plan) return <LoadingScreen message="Loading plan details..." />;

  return (
    <MainLayout>
      <div className="max-w-[1400px] mx-auto px-6 py-12 w-full">
        <header className="mb-24 flex flex-col lg:flex-row lg:items-end justify-between gap-12 text-left">
          <div className="space-y-6">
            <Badge variant="emerald">Plan Ready</Badge>
            <h1 className="text-7xl sm:text-8xl font-black text-white tracking-tighter uppercase italic leading-[0.85]">Your Plan<span className="text-indigo-500 not-italic">.</span></h1>
            <div className="flex flex-wrap gap-4 pt-6">
              {[
                { icon: MapPin, text: goalDetail.city },
                { icon: Timer, text: `${goalDetail.num_days} Days` },
                { icon: Globe, text: goalDetail.language_code.toUpperCase() },
              ].map((meta, i) => (
                <div key={i} className="flex items-center gap-3 bg-zinc-900 border border-zinc-800 px-5 py-3 rounded-xl text-[10px] font-black uppercase tracking-[0.2em] text-zinc-500">
                  <meta.icon size={14} className="text-indigo-500" /> {meta.text}
                </div>
              ))}
            </div>
          </div>

          <button
            onClick={() => exportPlanAsText(goalDetail, plan)}
            className="flex items-center gap-3 bg-white text-black px-10 h-16 rounded-2xl font-black uppercase text-[11px] tracking-[0.2em] shadow-2xl active:scale-95 border-b-4 border-zinc-300"
          >
            <Download size={20} /> Export Plan
          </button>
        </header>

        {/* Nutritional Summary */}
        {plan.days?.length > 0 && (() => {
          const dailyTotals = plan.days.map((day: any) => {
            const meals = ['breakfast', 'lunch', 'dinner'].filter(m => day[m]);
            return meals.reduce((acc: any, m: string) => {
              const n = parseNutrition(day[m].nutritional_info);
              return { kcal: acc.kcal + n.kcal, protein: acc.protein + n.protein, carbs: acc.carbs + n.carbs, fat: acc.fat + n.fat };
            }, { kcal: 0, protein: 0, carbs: 0, fat: 0 });
          });
          const avg = {
            kcal: Math.round(dailyTotals.reduce((s: number, d: any) => s + d.kcal, 0) / dailyTotals.length),
            protein: Math.round(dailyTotals.reduce((s: number, d: any) => s + d.protein, 0) / dailyTotals.length),
            carbs: Math.round(dailyTotals.reduce((s: number, d: any) => s + d.carbs, 0) / dailyTotals.length),
            fat: Math.round(dailyTotals.reduce((s: number, d: any) => s + d.fat, 0) / dailyTotals.length),
          };
          const cookedCount = plan.days.reduce((total: number, day: any) =>
            total + ['breakfast', 'lunch', 'dinner'].filter(m => day[m] && cookedSet.has(day[m].meal_identifier || `${id}:${day.day_number}:${m}:0`)).length, 0
          );
          const totalMeals = plan.days.reduce((total: number, day: any) =>
            total + ['breakfast', 'lunch', 'dinner'].filter(m => day[m]).length, 0
          );
          return (
            <div className="mb-16 grid grid-cols-2 sm:grid-cols-5 gap-4 text-left">
              {[
                { label: 'Avg Kcal/Day', value: avg.kcal, icon: Flame, color: 'text-orange-400' },
                { label: 'Avg Protein', value: `${avg.protein}g`, icon: null, color: 'text-rose-400' },
                { label: 'Avg Carbs', value: `${avg.carbs}g`, icon: null, color: 'text-amber-400' },
                { label: 'Avg Fat', value: `${avg.fat}g`, icon: null, color: 'text-blue-400' },
                { label: 'Cooked', value: `${cookedCount}/${totalMeals}`, icon: ChefHat, color: 'text-emerald-400' },
              ].map((stat) => (
                <div key={stat.label} className="bg-zinc-900/50 border border-zinc-800 rounded-2xl p-5">
                  <p className="text-[9px] font-black text-zinc-600 uppercase tracking-widest mb-2">{stat.label}</p>
                  <p className={`text-2xl font-black italic tracking-tighter ${stat.color}`}>{stat.value}</p>
                </div>
              ))}
            </div>
          );
        })()}

        <div className="grid lg:grid-cols-12 gap-16 items-start">
          <div className="lg:col-span-8 space-y-32">
            {plan.days?.map((day: any) => (
              <div key={day.day_number} className="relative group text-left">
                <div className="absolute -left-10 top-0 bottom-0 w-[1px] bg-gradient-to-b from-indigo-600/50 via-zinc-800 to-transparent hidden 2xl:block" />
                <div className="flex items-center gap-6 mb-12">
                  <div className="w-14 h-14 rounded-2xl bg-white text-black flex items-center justify-center text-3xl font-black italic shadow-2xl">{day.day_number}</div>
                  <h2 className="text-3xl font-black text-white uppercase tracking-tighter italic leading-none">Day {day.day_number}</h2>
                </div>

                <div className="grid gap-10">
                  {['breakfast', 'lunch', 'dinner'].map(m => day[m] && (() => {
                    const mealId = day[m].meal_identifier || `${id}:${day.day_number}:${m}:0`;
                    const isCooked = cookedSet.has(mealId);
                    return (
                      <Card
                        key={m}
                        className={`p-10 hover:bg-zinc-900/80 hover:border-indigo-500/20 group/meal relative overflow-hidden text-left ${isCooked ? 'border-emerald-500/20 bg-emerald-500/[0.02]' : ''}`}
                      >
                        <div className="absolute top-0 right-0 p-8 text-zinc-900 opacity-20 pointer-events-none group-hover/meal:text-indigo-900 transition-colors">
                          <UtensilsCrossed size={120} />
                        </div>

                        <div className="flex justify-between items-center mb-10 relative z-10">
                          <div className="flex items-center gap-3">
                            <span className="px-5 py-1.5 bg-indigo-600 text-white rounded-lg text-[9px] font-black uppercase tracking-[0.3em] italic shadow-xl">{MEAL_LABELS[m] || m}</span>
                            {isCooked && <span className="px-3 py-1 bg-emerald-500/10 text-emerald-400 rounded-lg text-[9px] font-black uppercase tracking-widest border border-emerald-500/20">Cooked</span>}
                          </div>
                          <div className="flex items-center gap-3">
                            <button
                              onClick={(e) => { e.stopPropagation(); toggleCooked.mutate({ mealId, isCooked: !isCooked, mealName: day[m].name }); }}
                              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[9px] font-black uppercase tracking-widest border transition-all ${isCooked ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400 hover:bg-rose-500/10 hover:border-rose-500/30 hover:text-rose-400' : 'bg-black/30 border-zinc-800 text-zinc-600 hover:border-emerald-500/30 hover:text-emerald-400'}`}
                            >
                              <ChefHat size={14} /> {isCooked ? 'Undo' : 'Mark Cooked'}
                            </button>
                            <div className="flex items-center gap-2 bg-black/30 px-3 py-1.5 rounded-lg text-[9px] font-black text-zinc-600 border border-zinc-800 uppercase tracking-widest italic">
                              <Timer size={14} className="text-indigo-500" /> {day[m].preparation_time || 20} min
                            </div>
                          </div>
                        </div>

                        <div className="cursor-pointer" onClick={() => navigate(`/plan/${id}/recipe/${mealId}`)}>
                          <h3 className={`text-4xl font-black mb-6 tracking-tighter leading-tight uppercase italic group-hover/meal:text-indigo-400 transition-colors relative z-10 ${isCooked ? 'text-zinc-500 line-through' : 'text-white'}`}>{day[m].name}</h3>
                          <p className="text-zinc-500 text-lg font-medium leading-relaxed mb-12 max-w-2xl relative z-10 italic">"{day[m].description}"</p>

                          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 relative z-10 pt-8 border-t border-zinc-800">
                            {Object.entries(day[m].nutritional_info || {}).map(([k, v]: any) => (
                              <div key={k} className="space-y-1.5">
                                <p className="text-[9px] font-black text-zinc-600 uppercase tracking-widest italic leading-none">{k}</p>
                                <p className="text-xl font-black text-zinc-200 italic tracking-tighter leading-none">{v}</p>
                              </div>
                            ))}
                          </div>

                          <div className="flex items-center gap-2 mt-8 text-[10px] font-black text-indigo-500 uppercase tracking-widest italic opacity-0 group-hover/meal:opacity-100 transition-opacity relative z-10">
                            View Recipe <ArrowRight size={14} />
                          </div>
                        </div>
                      </Card>
                    );
                  })())}
                </div>
              </div>
            ))}
          </div>

          <aside className="lg:col-span-4 lg:sticky lg:top-10">
            <Card className="p-10 border-indigo-500/10 text-left shadow-[0_50px_100px_-20px_rgba(0,0,0,0.8)]">
              <div className="flex items-center gap-4 mb-14 border-b border-zinc-800 pb-10">
                <div className="w-12 h-12 rounded-xl bg-indigo-600/10 flex items-center justify-center text-indigo-500 border border-indigo-500/10">
                  <ShoppingCart size={28} />
                </div>
                <h2 className="text-2xl font-black uppercase tracking-tighter italic text-white leading-none">Shopping List</h2>
              </div>

              <div className="space-y-6 max-h-[440px] overflow-y-auto pr-4 custom-scrollbar mb-14">
                {plan.shopping_list?.map((item: any, idx: number) => (
                  <div key={idx} className="group border-b border-zinc-800 pb-6 last:border-0 last:pb-0">
                    <div className="flex justify-between items-start gap-3 mb-2">
                      <p className="text-base font-black text-white group-hover:text-indigo-400 transition-colors uppercase tracking-tight italic leading-none truncate min-w-0">{item.ingredient}</p>
                      <p className="text-sm font-black text-indigo-500 tabular-nums leading-none shrink-0 whitespace-nowrap">{item.price} {item.currency}</p>
                    </div>
                    <div className="flex justify-between items-center text-[10px] font-black text-zinc-600 uppercase tracking-widest italic">
                      <span className="bg-zinc-950 px-2.5 py-1 rounded-lg border border-zinc-800">{item.quantity} {item.unit}</span>
                      <span className="opacity-30 group-hover:opacity-100 transition-opacity max-w-[120px] truncate text-right">{item.matched_product_name}</span>
                    </div>
                  </div>
                ))}
              </div>

              <div className="pt-10 border-t-2 border-indigo-600/30 space-y-10">
                <div className="space-y-2 text-left">
                  <p className="text-[9px] font-black text-zinc-700 uppercase tracking-[0.3em] italic leading-none">Estimated Total</p>
                  <p className="text-6xl font-black text-white italic tracking-tighter leading-none">
                    {plan.total_price}<span className="text-blue-500 text-xl not-italic ml-2 uppercase leading-none">{plan.currency}</span>
                  </p>
                </div>
                <button
                  onClick={() => navigate(`/plan/${id}/shopping-list`)}
                  className="w-full h-16 bg-indigo-600 hover:bg-indigo-500 text-white rounded-xl font-black uppercase text-xs tracking-[0.2em] shadow-indigo-500/20 active:scale-[0.98] transition-all flex items-center justify-center gap-4"
                >
                  <List size={18} /> View Full List
                </button>
              </div>
            </Card>
          </aside>
        </div>
      </div>
    </MainLayout>
  );
};
