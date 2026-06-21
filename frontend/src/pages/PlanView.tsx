import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { AlertCircle, MapPin, Timer, Globe, Download, ShoppingCart, UtensilsCrossed, ArrowRight, List, ChefHat, Flame, Wallet, CalendarDays } from 'lucide-react';
import { getFoodImageUrl } from '@/lib/food-image';
import { fmtMoney, getEstimate } from '@/lib/pricing';
import { api } from '@/lib/api';
import { MainLayout } from '@/components/layout/MainLayout';
import { Card } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { LoadingScreen } from '@/components/ui/LoadingScreen';
import { useToast } from '@/components/ui/Toast';

const MEAL_LABELS: Record<string, string> = {
  breakfast: 'Snídaně',
  lunch: 'Oběd',
  dinner: 'Večeře',
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
  const exportItems = Array.isArray(plan.shopping_list)
    ? plan.shopping_list
    : plan.shopping_list?.items || [];
  const exportEstimate = getEstimate(plan);
  const exportCurrency = exportEstimate?.currency || plan.currency || 'CZK';
  exportItems.forEach((item: any) => {
    const priced = item.price_total != null ? `~${item.price_total} ${exportCurrency}` : '—';
    lines.push(`  ${item.ingredient} — ${item.quantity} ${item.unit} — ${priced}`);
  });
  lines.push('');
  // Estimate, never an exact total.
  if (exportEstimate) {
    lines.push(`ESTIMATED TOTAL: ~${Math.round(exportEstimate.total)} ${exportCurrency}`);
  }

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
  const toast = useToast();

  const { data: statusData, error: statusError } = useQuery({
    queryKey: ['taskStatus', id],
    queryFn: () => api.get(`/goals/${id}/task-status/`).then(res => res.data.data),
    retry: 1,
    refetchInterval: (query: any) =>
      query?.state?.data?.goal_status === 'completed' || query?.state?.data?.goal_status === 'failed' ? false : 2500,
  });

  const { data: goalDetail, error: goalError } = useQuery({
    queryKey: ['plan', id],
    queryFn: () => api.get(`/goals/${id}/`).then(res => res.data.data),
    retry: 1,
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
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: ['mealInstances', id] });
      toast.success(variables.isCooked ? 'Označeno jako uvařeno!' : 'Odznačeno');
    },
  });

  if (statusError || goalError) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center p-12 text-center bg-[#1e293b] text-white">
        <div className="w-24 h-24 rounded-3xl bg-rose-500/10 flex items-center justify-center text-rose-500 border border-rose-500/20 mb-10">
          <AlertCircle size={48} />
        </div>
        <h1 className="text-5xl font-black tracking-tighter uppercase mb-4 leading-none italic">Plán nenalezen<span className="text-rose-600 not-italic">.</span></h1>
        <p className="text-zinc-400 max-w-sm font-medium tracking-tight italic opacity-80 leading-relaxed mb-12">Tento plán neexistuje nebo k němu nemáte přístup.</p>
        <button onClick={() => navigate('/')} className="px-10 h-14 bg-white text-black font-black uppercase text-[10px] tracking-widest rounded-xl shadow-2xl">Zpět na plány</button>
      </div>
    );
  }

  if (statusData?.goal_status === 'failed') {
    return (
      <div className="flex-1 flex flex-col items-center justify-center p-12 text-center bg-[#1e293b] text-white">
        <div className="w-24 h-24 rounded-3xl bg-rose-500/10 flex items-center justify-center text-rose-500 border border-rose-500/20 mb-10 animate-bounce">
          <AlertCircle size={48} />
        </div>
        <h1 className="text-5xl font-black tracking-tighter uppercase mb-4 leading-none italic">Generování selhalo<span className="text-rose-600 not-italic">.</span></h1>
        <p className={`text-zinc-400 max-w-sm font-medium tracking-tight italic opacity-80 leading-relaxed ${statusData?.error_message ? 'mb-4' : 'mb-12'}`}>Nepodařilo se vygenerovat jídelníček. Zkuste to prosím znovu s jinými parametry.</p>
        {statusData?.error_message && (
          <p className="text-zinc-300 max-w-md mb-12 text-xs font-mono opacity-60 leading-relaxed">{statusData.error_message}</p>
        )}
        <button onClick={() => navigate('/')} className="px-10 h-14 bg-white text-black font-black uppercase text-[10px] tracking-widest rounded-xl shadow-2xl">Zpět na plány</button>
      </div>
    );
  }

  if (statusData?.goal_status !== 'completed') {
    return <LoadingScreen message="Vytváříme váš personalizovaný jídelníček s reálnými cenami z obchodu..." status={statusData} goalId={id} />;
  }

  const plan = goalDetail?.dietary_plan;
  if (!plan) return <LoadingScreen message="Načítáme detaily plánu..." />;

  return (
    <MainLayout>
      <div className="max-w-[1400px] mx-auto px-6 py-12 w-full">
        <header className="mb-24 flex flex-col lg:flex-row lg:items-end justify-between gap-12 text-left">
          <div className="space-y-6">
            <Badge variant="emerald">Plán připraven</Badge>
            <h1 className="text-7xl sm:text-8xl font-black text-white tracking-tighter uppercase italic leading-[0.85]">Váš plán<span className="text-emerald-500 not-italic">.</span></h1>
            <div className="flex flex-wrap gap-4 pt-6">
              {[
                { icon: MapPin, text: goalDetail.city },
                { icon: Timer, text: `${goalDetail.num_days} dní` },
                { icon: Globe, text: (goalDetail.language_code || 'CS').toUpperCase() },
              ].map((meta, i) => (
                <div key={i} className="flex items-center gap-3 bg-slate-700 border border-slate-600 px-5 py-3 rounded-xl text-[10px] font-black uppercase tracking-[0.2em] text-zinc-300">
                  <meta.icon size={14} className="text-emerald-500" /> {meta.text}
                </div>
              ))}
            </div>
          </div>

          <button
            onClick={() => exportPlanAsText(goalDetail, plan)}
            className="flex items-center gap-3 bg-white text-black px-10 h-16 rounded-2xl font-black uppercase text-xs tracking-[0.2em] shadow-2xl active:scale-95 border-b-4 border-zinc-300"
          >
            <Download size={20} /> Exportovat
          </button>
        </header>

        {/* Your request — surface the original prompt so the user sees what they asked for */}
        {(goalDetail.prompt || goalDetail.dietary_restrictions) && (
          <div className="mb-16 bg-slate-800/60 border border-slate-700 rounded-3xl p-8 sm:p-10 text-left">
            <div className="flex items-center gap-3 mb-5">
              <UtensilsCrossed size={16} className="text-emerald-400" />
              <span className="text-[10px] font-black uppercase tracking-[0.25em] text-zinc-400">Vaše zadání</span>
            </div>
            {goalDetail.prompt && (
              <p className="text-zinc-200 text-lg font-medium tracking-tight leading-relaxed whitespace-pre-line">{goalDetail.prompt}</p>
            )}
            {goalDetail.dietary_restrictions && (
              <div className="mt-5 flex flex-wrap items-center gap-2">
                <span className="text-[10px] font-black uppercase tracking-[0.2em] text-rose-400">Omezení</span>
                <span className="text-zinc-300 text-sm font-medium tracking-tight">{goalDetail.dietary_restrictions}</span>
              </div>
            )}
          </div>
        )}

        {/* Plan price estimate — honest, de-emphasised. The headline is the
            whole-trolley ESTIMATE for this plan; per-day/per-portion are small
            secondary lines. No fabricated "savings vs average shopping". */}
        {(() => {
          const estimate = getEstimate(plan);
          if (!estimate || estimate.total <= 0) return null;
          const currency = estimate.currency || plan.currency || 'Kč';

          return (
            <div className="mb-16 bg-gradient-to-br from-emerald-600/10 to-teal-600/5 border border-emerald-500/20 rounded-3xl p-8 sm:p-10 text-left">
              <div className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-8">
                <div className="space-y-2">
                  <div className="flex items-center gap-2 mb-3">
                    <Wallet size={18} className="text-emerald-400" />
                    {/* EN gloss: "Estimated price of this plan" */}
                    <p className="text-[9px] font-black text-emerald-400 uppercase tracking-[0.3em]">Odhadovaná cena plánu</p>
                  </div>
                  <p className="text-5xl sm:text-6xl font-black text-white italic tracking-tighter leading-none tabular-nums">
                    ~{fmtMoney(estimate.total)}<span className="text-emerald-500 text-lg not-italic ml-2 uppercase">{currency}</span>
                  </p>
                  {(estimate.per_day != null || estimate.per_portion != null) && (
                    // EN gloss: "approx. {n} {currency}/day · approx. {n} {currency}/portion"
                    <p className="text-xs text-zinc-300 font-bold italic tabular-nums">
                      {estimate.per_day != null && <>~{fmtMoney(estimate.per_day)} {currency}/den</>}
                      {estimate.per_day != null && estimate.per_portion != null && <> &middot; </>}
                      {estimate.per_portion != null && <>~{fmtMoney(estimate.per_portion)} {currency}/porce</>}
                    </p>
                  )}
                </div>

                <div className="flex items-start gap-2 sm:max-w-xs">
                  <CalendarDays size={14} className="text-zinc-400 shrink-0 mt-0.5" />
                  {/* EN gloss: "Just an estimate — based on currently available store data. The real price may differ." */}
                  <p className="text-[11px] text-zinc-400 font-bold italic leading-relaxed">
                    Jen odhad – vychází z aktuálně dostupných dat obchodů.
                    Skutečná cena se může lišit.
                    {estimate.priced_items < estimate.total_items && (
                      // EN gloss: " Estimate covers {priced} of {total} items."
                      <> Odhad pokrývá {estimate.priced_items} z {estimate.total_items} položek.</>
                    )}
                  </p>
                </div>
              </div>
            </div>
          );
        })()}

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
                { label: 'Prům. kcal/den', value: avg.kcal, icon: Flame, color: 'text-orange-400' },
                { label: 'Prům. bílkoviny', value: `${avg.protein}g`, icon: null, color: 'text-rose-400' },
                { label: 'Prům. sacharidy', value: `${avg.carbs}g`, icon: null, color: 'text-amber-400' },
                { label: 'Prům. tuky', value: `${avg.fat}g`, icon: null, color: 'text-blue-400' },
                { label: 'Uvařeno', value: `${cookedCount}/${totalMeals}`, icon: ChefHat, color: 'text-emerald-400' },
              ].map((stat) => (
                <div key={stat.label} className="bg-slate-700/50 border border-slate-600 rounded-2xl p-5">
                  <p className="text-[9px] font-black text-zinc-400 uppercase tracking-widest mb-2">{stat.label}</p>
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
                <div className="absolute -left-10 top-0 bottom-0 w-[1px] bg-gradient-to-b from-emerald-600/50 via-zinc-800 to-transparent hidden 2xl:block" />
                <div className="flex items-center gap-6 mb-12">
                  <div className="w-14 h-14 rounded-2xl bg-white text-black flex items-center justify-center text-3xl font-black italic shadow-2xl">{day.day_number}</div>
                  <h2 className="text-3xl font-black text-white uppercase tracking-tighter italic leading-none">Den {day.day_number}</h2>
                </div>

                <div className="grid gap-10">
                  {['breakfast', 'lunch', 'dinner'].map(m => day[m] && (() => {
                    const mealId = day[m].meal_identifier || `${id}:${day.day_number}:${m}:0`;
                    const isCooked = cookedSet.has(mealId);
                    return (
                      <Card
                        key={m}
                        className={`p-0 hover:bg-slate-700/80 hover:border-emerald-500/20 group/meal relative overflow-hidden text-left ${isCooked ? 'border-emerald-500/20 bg-emerald-500/[0.02]' : ''}`}
                      >
                        {(() => {
                          const imgUrl = getFoodImageUrl(day[m].food_category, day[m].name);
                          return imgUrl ? (
                            <div className="relative h-48 sm:h-56 overflow-hidden">
                              <img src={imgUrl} alt={day[m].name} className="w-full h-full object-cover" loading="lazy"
                                onError={(e) => { ((e.target as HTMLImageElement).closest('.relative') as HTMLElement).style.display = 'none'; }}
                              />
                              <div className="absolute inset-0 bg-gradient-to-t from-[#334155] via-[#334155]/60 to-transparent" />
                            </div>
                          ) : (
                            <div className="absolute top-0 right-0 p-8 text-zinc-900 opacity-20 pointer-events-none group-hover/meal:text-emerald-900 transition-colors">
                              <UtensilsCrossed size={120} />
                            </div>
                          );
                        })()}

                        <div className="px-10 pb-10 -mt-16 relative z-10">
                        <div className="flex justify-between items-center mb-10 relative z-10">
                          <div className="flex items-center gap-3">
                            <span className="px-5 py-1.5 bg-emerald-600 text-white rounded-lg text-[9px] font-black uppercase tracking-[0.3em] italic shadow-xl">{MEAL_LABELS[m] || m}</span>
                            {isCooked && <span className="px-3 py-1 bg-emerald-500/10 text-emerald-400 rounded-lg text-[9px] font-black uppercase tracking-widest border border-emerald-500/20">Uvařeno</span>}
                          </div>
                          <div className="flex items-center gap-3">
                            <button
                              onClick={(e) => { e.stopPropagation(); toggleCooked.mutate({ mealId, isCooked: !isCooked, mealName: day[m].name }); }}
                              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[9px] font-black uppercase tracking-widest border transition-all ${isCooked ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400 hover:bg-rose-500/10 hover:border-rose-500/30 hover:text-rose-400' : 'bg-black/30 border-slate-600 text-zinc-400 hover:border-emerald-500/30 hover:text-emerald-400'}`}
                            >
                              <ChefHat size={14} /> {isCooked ? 'Zrušit' : 'Označit jako uvařené'}
                            </button>
                            <div className="flex items-center gap-2 bg-black/30 px-3 py-1.5 rounded-lg text-[9px] font-black text-zinc-400 border border-slate-600 uppercase tracking-widest italic">
                              <Timer size={14} className="text-emerald-500" /> {day[m].preparation_time || 20} min
                            </div>
                          </div>
                        </div>

                        <div className="cursor-pointer" onClick={() => navigate(`/plan/${id}/recipe/${mealId}`)}>
                          <h3 className={`text-4xl font-black mb-6 tracking-tighter leading-tight uppercase italic group-hover/meal:text-emerald-400 transition-colors relative z-10 ${isCooked ? 'text-zinc-300 line-through' : 'text-white'}`}>{day[m].name}</h3>
                          <p className="text-zinc-300 text-lg font-medium leading-relaxed mb-12 max-w-2xl relative z-10 italic">"{day[m].description}"</p>

                          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 relative z-10 pt-8 border-t border-slate-600">
                            {Object.entries(day[m].nutritional_info || {}).map(([k, v]: any) => (
                              <div key={k} className="space-y-1.5">
                                <p className="text-[9px] font-black text-zinc-400 uppercase tracking-widest italic leading-none">{k}</p>
                                <p className="text-xl font-black text-zinc-200 italic tracking-tighter leading-none">{v}</p>
                              </div>
                            ))}
                          </div>

                          <div className="flex items-center gap-2 mt-8 text-[10px] font-black text-emerald-500 uppercase tracking-widest italic opacity-0 group-hover/meal:opacity-100 transition-opacity relative z-10">
                            Zobrazit recept <ArrowRight size={14} />
                          </div>
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
            <Card className="p-10 border-emerald-500/10 text-left shadow-deep">
              <div className="flex items-center gap-4 mb-14 border-b border-slate-600 pb-10">
                <div className="w-12 h-12 rounded-xl bg-emerald-600/10 flex items-center justify-center text-emerald-500 border border-emerald-500/10">
                  <ShoppingCart size={28} />
                </div>
                <h2 className="text-2xl font-black uppercase tracking-tighter italic text-white leading-none">Nákupní seznam</h2>
              </div>

              <div className="space-y-6 max-h-[440px] overflow-y-auto pr-4 custom-scrollbar mb-14">
                {(Array.isArray(plan.shopping_list) ? plan.shopping_list : plan.shopping_list?.items || []).map((item: any, idx: number) => {
                  const sidebarCurrency = getEstimate(plan)?.currency || plan.currency || 'Kč';
                  return (
                    <div key={idx} className="group border-b border-slate-600 pb-6 last:border-0 last:pb-0">
                      <div className="flex justify-between items-start gap-3 mb-2">
                        {/* Plain ingredient only — no brand / product name */}
                        <p className="text-base font-black text-white group-hover:text-emerald-400 transition-colors uppercase tracking-tight italic leading-none truncate min-w-0">{item.ingredient}</p>
                        <div className="flex flex-col items-end shrink-0">
                          {item.price_total != null ? (
                            <p className="text-sm font-black text-zinc-300 tabular-nums leading-none whitespace-nowrap">~{fmtMoney(item.price_total)} {sidebarCurrency}</p>
                          ) : (
                            // EN gloss: "no estimate" — when we can't price an item
                            <p className="text-[10px] font-black text-zinc-500 uppercase tracking-widest italic leading-none whitespace-nowrap">bez odhadu</p>
                          )}
                          {item.estimated && item.price_total != null && (
                            // EN gloss: "estimate" — small honest label on every priced row
                            <span
                              title="Odhadovaná cena"
                              className="mt-1 text-[8px] font-black text-amber-400/90 uppercase tracking-widest italic leading-none"
                            >
                              odhad
                            </span>
                          )}
                        </div>
                      </div>
                      <div className="flex justify-between items-center text-[10px] font-black text-zinc-400 uppercase tracking-widest italic">
                        <span className="bg-slate-900 px-2.5 py-1 rounded-lg border border-slate-600">{item.quantity} {item.unit}</span>
                      </div>
                    </div>
                  );
                })}
              </div>

              <div className="pt-10 border-t-2 border-emerald-600/30 space-y-10">
                {(() => {
                  const estimate = getEstimate(plan);
                  const currency = estimate?.currency || plan.currency || 'Kč';
                  return (
                    <div className="space-y-2 text-left">
                      {/* EN gloss: "Estimated total price" — leading "~" reinforces it is not exact */}
                      <p className="text-[9px] font-black text-zinc-300 uppercase tracking-[0.3em] italic leading-none">Odhadovaná cena celkem</p>
                      <p className="text-6xl font-black text-white italic tracking-tighter leading-none tabular-nums">
                        ~{fmtMoney(estimate?.total ?? 0)}<span className="text-emerald-500 text-xl not-italic ml-2 uppercase leading-none">{currency}</span>
                      </p>
                      {estimate?.per_day != null && (
                        // EN gloss: "approx. {n} {currency}/day"
                        <p className="text-[10px] font-bold text-zinc-400 italic tabular-nums">~{fmtMoney(estimate.per_day)} {currency}/den</p>
                      )}
                    </div>
                  );
                })()}
                <button
                  onClick={() => navigate(`/plan/${id}/shopping-list`)}
                  className="w-full h-16 bg-emerald-600 hover:bg-emerald-500 text-white rounded-xl font-black uppercase text-xs tracking-[0.2em] shadow-emerald-500/20 active:scale-[0.98] transition-all flex items-center justify-center gap-4"
                >
                  <List size={18} /> Zobrazit celý seznam
                </button>
              </div>
            </Card>
          </aside>
        </div>
      </div>
    </MainLayout>
  );
};
