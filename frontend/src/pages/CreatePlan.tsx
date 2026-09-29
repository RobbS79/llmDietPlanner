import { useState, useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useQuery, useMutation } from '@tanstack/react-query';
import { Loader2, BrainCircuit, Minus, Plus, Check, AlertCircle, RotateCcw, ArrowRight, ArrowLeft, ChefHat, FileText, ChevronDown } from 'lucide-react';
import { api } from '@/lib/api';
import { MainLayout } from '@/components/layout/MainLayout';
import { Card } from '@/components/ui/Card';
import { ProtocolUpload } from '@/components/ProtocolUpload';
import { buildPreferencesPrompt } from '@/lib/preferences';
import { countLabel, mealsLabel, poolSummary, type PoolSlot } from '@/lib/poolCounts';

const STEPS = [
  { label: 'Cíle', icon: BrainCircuit },
  { label: 'Jídla', icon: ChefHat },
];

type CountField = 'breakfasts' | 'lunches' | 'dinners' | 'small_meals' | 'snacks';
const COUNT_FIELDS: { slot: PoolSlot; field: CountField; label: string }[] = [
  { slot: 'breakfast', field: 'breakfasts', label: 'Snídaně' },
  { slot: 'lunch', field: 'lunches', label: 'Obědy' },
  { slot: 'dinner', field: 'dinners', label: 'Večeře' },
  { slot: 'small_meal', field: 'small_meals', label: 'Svačiny' },
  { slot: 'snack', field: 'snacks', label: 'Drobné snacky' },
];
// EN: "Working week" 5/5/5/5/0, "Weekend" 2/2/2/0/2
const PRESETS = [
  { label: 'Pracovní týden', counts: { breakfasts: 5, lunches: 5, dinners: 5, small_meals: 5, snacks: 0 } },
  { label: 'Víkend', counts: { breakfasts: 2, lunches: 2, dinners: 2, small_meals: 0, snacks: 2 } },
];
// Legacy (pre-pool) goals have all-zero counts; show their day length instead.
const goalChipCount = (goal: { counts?: Record<string, number>; num_days?: number | null }) => {
  const total = Object.values(goal.counts || {}).reduce((a, b) => a + (b || 0), 0);
  return total === 0 && goal.num_days ? `${goal.num_days} dní` : mealsLabel(total);
};
const clampCount = (n: number) => Math.min(14, Math.max(0, Number.isFinite(n) ? Math.round(n) : 0));

export const CreatePlan = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const [step, setStep] = useState(0);
  const [error, setError] = useState('');
  const [protocolExpanded, setProtocolExpanded] = useState(false);
  const [formData, setFormData] = useState({
    prompt: '',
    dietary_restrictions: '',
    country: 'CZ',
    city: '',
    language_code: 'cs',
    breakfasts: 5,
    lunches: 5,
    dinners: 5,
    small_meals: 5,
    snacks: 0,
    goal_id: null as number | null,
    historic_plan_id: null as number | null,
  });

  const { data: profile } = useQuery({
    queryKey: ['profile'],
    queryFn: () => api.get('/auth/profile/').then(res => res.data.data),
  });

  useEffect(() => {
    const prefs = (location.state as any)?.fromOnboarding || profile?.dietary_preferences;
    if (!prefs || Object.keys(prefs).length === 0) return;

    const { prompt, restrictions } = buildPreferencesPrompt(prefs);

    setFormData(prev => ({
      ...prev,
      prompt: prev.prompt || prompt,
      dietary_restrictions: prev.dietary_restrictions || restrictions,
      country: prefs.country || prev.country,
      language_code: prefs.country === 'SK' ? 'sk' : 'cs',
    }));
  }, [profile?.dietary_preferences, location.state]);

  const { data: previousGoals } = useQuery({
    queryKey: ['goals'],
    queryFn: () => api.get('/goals/list/').then(res => res.data.data),
  });

  const completedGoals = previousGoals?.filter((g: any) => g.status === 'completed') || [];

  const prefillFrom = (goal: any) => {
    setFormData(prev => ({
      ...prev,
      prompt: goal.prompt || prev.prompt,
      country: goal.country || prev.country,
      city: goal.city || prev.city,
      language_code: goal.language_code || prev.language_code,
      breakfasts: goal.breakfasts ?? prev.breakfasts,
      lunches: goal.lunches ?? prev.lunches,
      dinners: goal.dinners ?? prev.dinners,
      small_meals: goal.small_meals ?? prev.small_meals,
      snacks: goal.snacks ?? prev.snacks,
    }));
  };

  const mutation = useMutation({
    mutationFn: (data: any) => api.post('/goals/', data),
    onSuccess: (res) => { setError(''); navigate(`/plan/${res.data.data.goal_id}`); },
    onError: (err: any) => setError(err.response?.data?.error || 'Nepodařilo se vytvořit plán. Zkuste to znovu.'),
  });

  const update = (field: string, value: any) => setFormData(prev => ({ ...prev, [field]: value }));

  const totalMeals = COUNT_FIELDS.reduce((s, f) => s + formData[f.field], 0);

  const canAdvance = () => {
    if (step === 0) return formData.prompt.trim().length > 0 && formData.city.trim().length > 0;
    return totalMeals > 0;
  };

  const next = () => { if (step < STEPS.length - 1 && canAdvance()) setStep(step + 1); };
  const back = () => { if (step > 0) setStep(step - 1); };

  const handleSubmit = () => {
    setError('');
    mutation.mutate(formData);
  };

  return (
    <MainLayout>
      <div className="max-w-4xl mx-auto px-6 py-12 w-full pb-32 sm:pb-12">
        <header className="mb-12 text-center space-y-4">
          <h1 className="font-display text-5xl sm:text-7xl font-black text-ink tracking-tighter uppercase italic leading-[0.85]">
            Nový<br /><span className="text-paprika not-italic">plán.</span>
          </h1>
        </header>

        {/* Progress bar */}
        <div className="mb-12 max-w-md mx-auto">
          <div className="flex items-center justify-between mb-3">
            {STEPS.map((s, i) => (
              <button
                key={i}
                type="button"
                onClick={() => { if (i < step || (i === step) || (i <= step + 1 && canAdvance())) setStep(i); }}
                className={`flex items-center gap-2 text-[10px] font-black uppercase tracking-widest transition-all ${
                  i === step ? 'text-green' : i < step ? 'text-green cursor-pointer' : 'text-muted'
                }`}
              >
                <div className={`w-8 h-8 rounded-lg flex items-center justify-center text-sm font-black transition-all ${
                  i === step ? 'bg-green text-white shadow-lg' : i < step ? 'bg-green-soft text-green border border-green/40' : 'bg-kraft text-muted border border-line'
                }`}>
                  {i < step ? <Check size={14} /> : i + 1}
                </div>
                <span className="hidden sm:inline">{s.label}</span>
              </button>
            ))}
          </div>
          <div className="h-1 bg-kraft rounded-full overflow-hidden">
            <div
              className="h-full bg-gradient-to-r from-green to-green-mid rounded-full transition-all duration-500 ease-out"
              style={{ width: `${((step + 1) / STEPS.length) * 100}%` }}
            />
          </div>
          <p className="text-center text-[10px] font-black text-muted uppercase tracking-widest mt-3">
            Krok {step + 1} z {STEPS.length}
          </p>
        </div>

        {completedGoals.length > 0 && step === 0 && (
          <div className="mb-12 p-6 bg-card border border-line rounded-2xl text-left">
            <div className="flex items-center gap-3 mb-4">
              <RotateCcw size={16} className="text-green" />
              <span className="text-[10px] font-black uppercase tracking-widest text-muted">Použít předchozí nastavení</span>
            </div>
            <div className="flex flex-wrap gap-2">
              {completedGoals.slice(0, 5).map((goal: any) => (
                <button
                  key={goal.id}
                  type="button"
                  onClick={() => prefillFrom(goal)}
                  className="px-4 py-2.5 bg-paper border border-line rounded-xl text-xs font-bold text-ink hover:bg-kraft hover:border-green/40 transition-all truncate max-w-[220px]"
                  title={goal.prompt}
                >
                  {goal.city} · {goalChipCount(goal)} — {goal.prompt?.slice(0, 30)}{goal.prompt?.length > 30 ? '...' : ''}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Step 1: Dietary Goals */}
        {step === 0 && (
          <section className="space-y-8 text-left animate-[fadeIn_0.3s_ease-out]">
            <div className="flex items-center gap-4 text-ink">
              <div className="w-8 h-8 rounded-lg bg-green flex items-center justify-center font-black italic shadow-lg">1</div>
              <h2 className="font-display text-2xl font-black uppercase tracking-tight italic leading-none">Stravovací cíle</h2>
            </div>

            <Card className="p-8 space-y-10">
              <div className="space-y-4">
                <label className="text-[10px] font-black uppercase tracking-widest text-muted flex items-center gap-2 italic">
                  <BrainCircuit size={14} className="text-green" /> Popište své cíle
                </label>
                <textarea
                  autoFocus
                  className="w-full bg-paper border border-line rounded-2xl p-6 text-lg font-bold text-ink placeholder:text-muted focus:outline-none focus:ring-2 focus:ring-green transition-all min-h-[220px] leading-relaxed"
                  placeholder="např. Vysoko proteinová dieta, 2400 kcal denně. Bez mléčných výrobků. Cenově dostupné suroviny v Praze..."
                  value={formData.prompt}
                  onChange={e => update('prompt', e.target.value)}
                />
              </div>

              <div className="grid grid-cols-2 gap-8">
                <div className="space-y-3">
                  <label className="text-[10px] font-black uppercase tracking-widest text-muted">Země</label>
                  <select
                    className="w-full bg-paper border border-line rounded-xl h-14 px-5 text-xs font-black text-ink uppercase tracking-widest focus:outline-none appearance-none cursor-pointer"
                    value={formData.country}
                    onChange={e => {
                      const c = e.target.value;
                      update('country', c);
                      update('language_code', c === 'CZ' ? 'cs' : 'sk');
                    }}
                  >
                    <option value="CZ">Česko (CZK)</option>
                    <option value="SK">Slovensko (EUR)</option>
                  </select>
                </div>
                <div className="space-y-3">
                  <label className="text-[10px] font-black uppercase tracking-widest text-muted">Město</label>
                  <input type="text" className="w-full bg-paper border border-line rounded-xl h-14 px-5 text-sm font-black text-ink placeholder:text-muted focus:outline-none" placeholder="např. Praha" value={formData.city} onChange={e => update('city', e.target.value)} />
                </div>
              </div>

              {/* Protocol upload section */}
              <div className="pt-8 border-t border-line">
                <button
                  type="button"
                  onClick={() => setProtocolExpanded(!protocolExpanded)}
                  className="flex items-center gap-3 w-full text-left group"
                >
                  <FileText size={16} className={formData.historic_plan_id ? 'text-green' : 'text-muted'} />
                  <span className="text-[10px] font-black uppercase tracking-widest text-muted group-hover:text-ink transition-colors">
                    Máte dietní protokol od specialisty?
                  </span>
                  {formData.historic_plan_id && (
                    <span className="text-[9px] font-bold text-green bg-green-soft px-2 py-0.5 rounded-md">
                      Připojeno
                    </span>
                  )}
                  <ChevronDown size={14} className={`text-muted ml-auto transition-transform ${protocolExpanded ? 'rotate-180' : ''}`} />
                </button>

                {protocolExpanded && (
                  <div className="mt-4">
                    <ProtocolUpload
                      selectedProtocolId={formData.historic_plan_id}
                      onProtocolSelect={(id) => update('historic_plan_id', id)}
                    />
                  </div>
                )}
              </div>
            </Card>
          </section>
        )}

        {/* Step 2: Meal Settings */}
        {step === 1 && (
          <section className="space-y-8 text-left animate-[fadeIn_0.3s_ease-out]">
            <div className="flex items-center gap-4 text-ink">
              <div className="w-8 h-8 rounded-lg bg-green flex items-center justify-center font-black italic shadow-lg">2</div>
              <h2 className="font-display text-2xl font-black uppercase tracking-tight italic leading-none">Nastavení jídel</h2>
            </div>

            <Card className="p-8 space-y-10">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-[10px] font-black uppercase tracking-widest text-muted italic mr-2">Rychlá volba</span>
                {PRESETS.map(p => (
                  <button key={p.label} type="button" onClick={() => setFormData(prev => ({ ...prev, ...p.counts }))}
                    className="px-4 py-2 rounded-xl text-[10px] font-black uppercase tracking-widest border border-line bg-paper text-muted hover:text-ink hover:border-green/40 transition-all">
                    {p.label}
                  </button>
                ))}
              </div>

              <div className="grid sm:grid-cols-2 gap-5">
                {COUNT_FIELDS.map(({ slot, field, label }) => (
                  <div key={field} className="flex items-center justify-between gap-4 bg-paper border border-line rounded-2xl px-5 py-4">
                    <div>
                      <label htmlFor={`count-${field}`} className="block text-[10px] font-black uppercase tracking-widest text-muted">{label}</label>
                      <span className="text-sm font-bold text-ink">{countLabel(slot, formData[field])}</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <button type="button" aria-label={`Méně: ${label}`} onClick={() => update(field, clampCount(formData[field] - 1))}
                        className="w-9 h-9 rounded-lg border border-line bg-card text-ink hover:border-green/40 flex items-center justify-center"><Minus size={14} /></button>
                      <input id={`count-${field}`} type="number" min={0} max={14} value={formData[field]}
                        onFocus={e => e.target.select()}
                        onChange={e => update(field, clampCount(parseInt(e.target.value, 10)))}
                        className="w-14 h-9 bg-card border border-line rounded-lg text-center text-sm font-black text-ink focus:outline-none focus:border-green" />
                      <button type="button" aria-label={`Více: ${label}`} onClick={() => update(field, clampCount(formData[field] + 1))}
                        className="w-9 h-9 rounded-lg border border-line bg-card text-ink hover:border-green/40 flex items-center justify-center"><Plus size={14} /></button>
                    </div>
                  </div>
                ))}
              </div>

              <p className="text-sm font-bold text-ink">{poolSummary({ breakfast: formData.breakfasts, lunch: formData.lunches, dinner: formData.dinners, small_meal: formData.small_meals, snack: formData.snacks })}</p>
              {totalMeals === 0 && (
                // EN: "Pick at least one meal."
                <p role="alert" className="text-sm font-bold text-paprika-strong">Vyberte alespoň jedno jídlo.</p>
              )}
              {/* EN: "No days — you cook the recipes whenever it suits you; each recipe has its own shopping list." */}
              <p className="text-xs text-muted leading-relaxed">Žádné dny — recepty uvaříte, kdy se vám to hodí. Každý recept má vlastní nákupní seznam.</p>
            </Card>
          </section>
        )}

        <div aria-live="polite" aria-atomic="true">
        {error && (
          <div role="alert" className="flex items-center gap-3 bg-paprika-soft border border-paprika/30 text-paprika-strong rounded-xl p-5 text-sm font-bold mt-8">
            <AlertCircle size={18} className="shrink-0" />
            <span>{error}</span>
          </div>
        )}
        </div>

        {/* Desktop navigation buttons */}
        <div className="hidden sm:flex items-center justify-between mt-12 gap-4">
          {step > 0 ? (
            <button type="button" onClick={back} className="flex items-center gap-3 px-8 h-14 border border-line text-ink hover:bg-kraft rounded-xl font-black uppercase text-[10px] tracking-widest transition-all">
              <ArrowLeft size={16} /> Zpět
            </button>
          ) : <div />}

          {step < STEPS.length - 1 ? (
            <button type="button" onClick={next} disabled={!canAdvance()} className="flex items-center gap-3 px-10 h-14 bg-green hover:bg-green-mid text-white rounded-xl font-black uppercase text-[10px] tracking-widest transition-all active:scale-[0.98] disabled:opacity-30 shadow-lg">
              Další krok <ArrowRight size={16} />
            </button>
          ) : (
            <button type="button" onClick={handleSubmit} disabled={mutation.isPending || !formData.prompt || totalMeals === 0} className="flex items-center gap-4 px-12 h-16 bg-green hover:bg-green-mid text-white rounded-2xl font-black text-lg uppercase tracking-widest shadow-2xl transition-all active:scale-[0.98] disabled:opacity-30">
              {mutation.isPending ? <><Loader2 className="animate-spin" size={24} /> Vytváří se...</> : <>Vygenerovat plán <ArrowRight size={20} /></>}
            </button>
          )}
        </div>

        {/* Mobile sticky bottom bar */}
        <div className="fixed bottom-0 left-0 right-0 z-50 p-4 bg-paper/95 backdrop-blur-lg border-t border-line sm:hidden">
          <div className="flex gap-3">
            {step > 0 && (
              <button type="button" onClick={back} className="flex items-center justify-center w-14 h-14 border border-line text-ink rounded-xl transition-all">
                <ArrowLeft size={20} />
              </button>
            )}
            {step < STEPS.length - 1 ? (
              <button type="button" onClick={next} disabled={!canAdvance()} className="flex-1 flex items-center justify-center gap-3 h-14 bg-green hover:bg-green-mid text-white rounded-xl font-black uppercase text-xs tracking-widest transition-all disabled:opacity-30">
                Další krok <ArrowRight size={16} />
              </button>
            ) : (
              <button type="button" onClick={handleSubmit} disabled={mutation.isPending || !formData.prompt || totalMeals === 0} className="flex-1 flex items-center justify-center gap-3 h-14 bg-green hover:bg-green-mid text-white rounded-xl font-black uppercase text-xs tracking-widest transition-all disabled:opacity-30">
                {mutation.isPending ? <><Loader2 className="animate-spin" size={20} /> Vytváří se...</> : <>Vygenerovat plán <ArrowRight size={16} /></>}
              </button>
            )}
          </div>
        </div>
      </div>
    </MainLayout>
  );
};
