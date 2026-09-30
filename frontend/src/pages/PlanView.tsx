import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { AlertCircle, MapPin, Timer, Globe, Download, UtensilsCrossed, ChefHat, Flame } from 'lucide-react';
import { api } from '@/lib/api';
import { MainLayout } from '@/components/layout/MainLayout';
import { Badge } from '@/components/ui/Badge';
import { LoadingScreen } from '@/components/ui/LoadingScreen';
import { useToast } from '@/components/ui/Toast';
import { dayMealEntries, dayTotals, groupPoolMeals, poolTotals, type PlanMeal } from '@/lib/planMeals';
import { DayCard } from '@/components/plan/DayCard';
import { WeekStrip } from '@/components/plan/WeekStrip';
import { SlotSection } from '@/components/plan/SlotSection';
import { SlotStrip } from '@/components/plan/SlotStrip';
import { mealsLabel, poolSummary, type PoolCounts } from '@/lib/poolCounts';
import { normalizeNutrition, nutritionBasisFor } from '@/lib/nutrition';
import { AdRail } from '@/components/ads/AdRail';

/** "3 večeře · 1 snack"; without usable counts, "N jídel" from the meals themselves. */
function poolHeading(counts: Partial<PoolCounts> | null | undefined, meals: unknown[]): string {
  const hasCounts = !!counts && Object.values(counts).some((n) => (n ?? 0) > 0);
  return hasCounts ? poolSummary(counts) : mealsLabel(meals.length);
}

export function exportPlanAsText(goalDetail: any, plan: any) {
  const lines: string[] = [];
  const isPool = Array.isArray(plan.meals);
  lines.push(`JÍDELNÍČEK — ${goalDetail.city}, ${isPool ? poolHeading(goalDetail.counts, plan.meals) : `${goalDetail.num_days} dní`}`);
  lines.push(`Vytvořeno: ${new Date().toLocaleDateString('cs-CZ')}`);
  lines.push('');
  const pushMeal = (label: string, meal: PlanMeal) => {
    lines.push(`  ${label.toUpperCase()}: ${meal.name}`);
    if (meal.description) lines.push(`    ${meal.description}`);
    const ni = meal.nutritional_info as Record<string, unknown> | undefined;
    const rows = ni
      ? normalizeNutrition(ni, Number(ni.servings ?? (meal as any).servings) || null, nutritionBasisFor(meal as any))
      : null;
    if (rows) lines.push(`    ${rows.map((r) => `${r.label}: ${r.value} ${r.unit}`).join(' | ')}`);
  };
  if (isPool) {
    groupPoolMeals(plan.meals, goalDetail.id).forEach((section) => {
      lines.push(`═══ ${section.label.toUpperCase()} ═══`);
      section.entries.forEach(({ label, meal }) => pushMeal(label, meal));
      lines.push('');
    });
  } else {
    plan.days?.forEach((day: any) => {
      lines.push(`═══ DEN ${day.day_number} ═══`);
      dayMealEntries(day, goalDetail.id).forEach(({ label, meal }) => pushMeal(label, meal));
      lines.push('');
    });
  }
  const blob = new Blob([lines.join('\n')], { type: 'text/plain' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `jidelnicek-${goalDetail.city}.txt`;
  a.click();
  URL.revokeObjectURL(url);
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

  const cookedSet = new Set<string>(
    (mealInstances || []).filter((mi: any) => mi.is_cooked).map((mi: any) => String(mi.meal_identifier))
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
      <div className="flex-1 flex flex-col items-center justify-center p-12 text-center bg-paper text-ink">
        <div className="w-24 h-24 rounded-3xl bg-paprika-soft flex items-center justify-center text-paprika-strong border border-paprika/30 mb-10">
          <AlertCircle size={48} />
        </div>
        <h1 className="font-display text-5xl font-black tracking-tighter uppercase mb-4 leading-none italic">Plán nenalezen<span className="text-paprika not-italic">.</span></h1>
        <p className="text-muted max-w-sm font-medium tracking-tight italic opacity-80 leading-relaxed mb-12">Tento plán neexistuje nebo k němu nemáte přístup.</p>
        <button onClick={() => navigate('/')} className="px-10 h-14 bg-green text-white font-black uppercase text-[10px] tracking-widest rounded-xl shadow-2xl">Zpět na plány</button>
      </div>
    );
  }

  if (statusData?.goal_status === 'failed') {
    return (
      <div className="flex-1 flex flex-col items-center justify-center p-12 text-center bg-paper text-ink">
        <div className="w-24 h-24 rounded-3xl bg-paprika-soft flex items-center justify-center text-paprika-strong border border-paprika/30 mb-10 animate-bounce">
          <AlertCircle size={48} />
        </div>
        <h1 className="font-display text-5xl font-black tracking-tighter uppercase mb-4 leading-none italic">Generování selhalo<span className="text-paprika not-italic">.</span></h1>
        <p className={`text-muted max-w-sm font-medium tracking-tight italic opacity-80 leading-relaxed ${statusData?.error_message ? 'mb-4' : 'mb-12'}`}>Nepodařilo se vygenerovat jídelníček. Zkuste to prosím znovu s jinými parametry.</p>
        {statusData?.error_message && (
          <p className="text-muted max-w-md mb-12 text-xs font-mono opacity-60 leading-relaxed">{statusData.error_message}</p>
        )}
        <button onClick={() => navigate('/')} className="px-10 h-14 bg-green text-white font-black uppercase text-[10px] tracking-widest rounded-xl shadow-2xl">Zpět na plány</button>
      </div>
    );
  }

  if (statusData?.goal_status !== 'completed') {
    return <LoadingScreen message="Vybíráme recepty a skládáme nákupní seznamy..." status={statusData} goalId={id} />;
  }

  const plan = goalDetail?.dietary_plan;
  if (!plan) return <LoadingScreen message="Načítáme detaily plánu..." />;

  const isPool = Array.isArray(plan?.meals);
  const sections = isPool ? groupPoolMeals(plan.meals, id!) : [];
  const totals = isPool ? poolTotals(plan.meals, id!, cookedSet) : null;
  const counts = goalDetail?.counts || {};
  const hasMains = sections.some((section) => section.isMain && section.entries.length > 0);

  return (
    <MainLayout>
      <div className="max-w-[1320px] mx-auto px-6 py-12 w-full flex gap-10 justify-center items-start">
      <div className="w-full max-w-[960px] min-w-0">
        <header className="mb-24 flex flex-col lg:flex-row lg:items-end justify-between gap-12 text-left">
          <div className="space-y-6">
            <Badge variant="emerald">Plán připraven</Badge>
            <h1 className="font-display text-7xl sm:text-8xl font-black text-ink tracking-tighter uppercase italic leading-[0.85]">Váš plán<span className="text-paprika not-italic">.</span></h1>
            <div className="flex flex-wrap gap-4 pt-6">
              {[
                { icon: MapPin, text: goalDetail.city },
                { icon: Timer, text: isPool ? poolHeading(counts, plan.meals) : `${goalDetail.num_days} dní` },
                { icon: Globe, text: (goalDetail.language_code || 'CS').toUpperCase() },
              ].map((meta, i) => (
                <div key={i} className="flex items-center gap-3 bg-card border border-line px-5 py-3 rounded-xl text-[10px] font-black uppercase tracking-[0.2em] text-muted">
                  <meta.icon size={14} className="text-green" /> {meta.text}
                </div>
              ))}
            </div>
          </div>

          <button
            onClick={() => exportPlanAsText(goalDetail, plan)}
            className="flex items-center gap-3 bg-green text-white px-10 h-16 rounded-2xl font-black uppercase text-xs tracking-[0.2em] shadow-2xl active:scale-95 border-b-4 border-green-mid"
          >
            <Download size={20} /> Exportovat
          </button>
        </header>

        {/* Your request — surface the original prompt so the user sees what they asked for */}
        {(goalDetail.prompt || goalDetail.dietary_restrictions) && (
          <div className="mb-16 bg-card border border-line rounded-3xl p-8 sm:p-10 text-left">
            <div className="flex items-center gap-3 mb-5">
              <UtensilsCrossed size={16} className="text-green" />
              <span className="text-[10px] font-black uppercase tracking-[0.25em] text-muted">Vaše zadání</span>
            </div>
            {goalDetail.prompt && (
              <p className="text-ink text-lg font-medium tracking-tight leading-relaxed whitespace-pre-line">{goalDetail.prompt}</p>
            )}
            {goalDetail.dietary_restrictions && (
              <div className="mt-5 flex flex-wrap items-center gap-2">
                <span className="text-[10px] font-black uppercase tracking-[0.2em] text-paprika-strong">Omezení</span>
                <span className="text-muted text-sm font-medium tracking-tight">{goalDetail.dietary_restrictions}</span>
              </div>
            )}
          </div>
        )}

        {isPool && totals && (
          <div className="mb-16 grid grid-cols-2 sm:grid-cols-3 gap-4 text-left">
            {[
              // EN: "Meals", "Avg kcal per main", "Cooked"
              { label: 'Jídel', value: totals.total, icon: null, color: 'text-ink' },
              { label: 'Prům. kcal na hlavní jídlo', value: hasMains ? totals.avgMainKcal : '—', icon: Flame, color: 'text-orange-600' },
              { label: 'Uvařeno', value: `${totals.cooked}/${totals.total}`, icon: ChefHat, color: 'text-green' },
            ].map((stat) => (
              <div key={stat.label} className="bg-card border border-line rounded-2xl p-5">
                <p className="text-[9px] font-black text-muted uppercase tracking-widest mb-2">{stat.label}</p>
                <p className={`text-2xl font-black italic tracking-tighter ${stat.color}`}>{stat.value}</p>
              </div>
            ))}
          </div>
        )}

        {/* Nutritional Summary */}
        {!isPool && plan.days?.length > 0 && (() => {
          const dailyTotals = plan.days.map((day: any) => dayTotals(day, id!));
          const avg = {
            kcal: Math.round(dailyTotals.reduce((s: number, d: any) => s + d.kcal, 0) / dailyTotals.length),
            protein: Math.round(dailyTotals.reduce((s: number, d: any) => s + d.protein, 0) / dailyTotals.length),
            carbs: Math.round(dailyTotals.reduce((s: number, d: any) => s + d.carbs, 0) / dailyTotals.length),
            fat: Math.round(dailyTotals.reduce((s: number, d: any) => s + d.fat, 0) / dailyTotals.length),
          };
          const cookedCount = plan.days.reduce((total: number, day: any) =>
            total + dayMealEntries(day, id!).filter(e => cookedSet.has(e.mealId)).length, 0
          );
          const totalMeals = plan.days.reduce((total: number, day: any) =>
            total + dayMealEntries(day, id!).length, 0
          );
          return (
            <div className="mb-16 grid grid-cols-2 sm:grid-cols-5 gap-4 text-left">
              {[
                { label: 'Prům. kcal/den', value: avg.kcal, icon: Flame, color: 'text-orange-600' },
                { label: 'Prům. bílkoviny', value: `${avg.protein}g`, icon: null, color: 'text-paprika-strong' },
                { label: 'Prům. sacharidy', value: `${avg.carbs}g`, icon: null, color: 'text-amber-600' },
                { label: 'Prům. tuky', value: `${avg.fat}g`, icon: null, color: 'text-blue-600' },
                { label: 'Uvařeno', value: `${cookedCount}/${totalMeals}`, icon: ChefHat, color: 'text-green' },
              ].map((stat) => (
                <div key={stat.label} className="bg-card border border-line rounded-2xl p-5">
                  <p className="text-[9px] font-black text-muted uppercase tracking-widest mb-2">{stat.label}</p>
                  <p className={`text-2xl font-black italic tracking-tighter ${stat.color}`}>{stat.value}</p>
                </div>
              ))}
            </div>
          );
        })()}

        {isPool ? (
          <>
            <SlotStrip sections={sections} />
            <div className="space-y-8">
              {sections.map((section) => (
                <SlotSection
                  key={section.slot}
                  section={section}
                  requested={counts[section.slot] ?? section.entries.length}
                  cookedSet={cookedSet}
                  onOpen={(mealId, chat) => navigate(`/plan/${id}/recipe/${mealId}${chat ? '?chat=1' : ''}`)}
                  onToggleCooked={(mealId, isCooked, mealName) => toggleCooked.mutate({ mealId, isCooked, mealName })}
                />
              ))}
            </div>
          </>
        ) : (
          <>
            <WeekStrip days={plan.days || []} goalId={id!} />
            <div className="space-y-8">
              {plan.days?.map((day: any) => (
                <DayCard
                  key={day.day_number}
                  day={day}
                  goalId={id!}
                  cookedSet={cookedSet}
                  onOpen={(mealId, chat) => navigate(`/plan/${id}/recipe/${mealId}${chat ? '?chat=1' : ''}`)}
                  onToggleCooked={(mealId, isCooked, mealName) => toggleCooked.mutate({ mealId, isCooked, mealName })}
                />
              ))}
            </div>
          </>
        )}
      </div>
      <AdRail slot="plan-right" />
      </div>
    </MainLayout>
  );
};
