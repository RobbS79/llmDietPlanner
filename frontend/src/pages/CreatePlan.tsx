import { useState, useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useQuery, useMutation } from '@tanstack/react-query';
import { Loader2, BrainCircuit, Coffee, UtensilsCrossed, Utensils, Check, AlertCircle, RotateCcw, ArrowRight, ArrowLeft, ChefHat, FileText, ChevronDown } from 'lucide-react';
import { api } from '@/lib/api';
import { MainLayout } from '@/components/layout/MainLayout';
import { Card } from '@/components/ui/Card';
import { ProtocolUpload } from '@/components/ProtocolUpload';
import { buildPreferencesPrompt } from '@/lib/preferences';

const STEPS = [
  { label: 'Cíle', icon: BrainCircuit },
  { label: 'Jídla', icon: ChefHat },
];

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
    num_days: 7,
    breakfast: true,
    lunch: true,
    dinner: true,
    small_meals_per_day: 2,
    snacks_per_day: 1,
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
      num_days: goal.num_days ?? prev.num_days,
      breakfast: goal.breakfast ?? prev.breakfast,
      lunch: goal.lunch ?? prev.lunch,
      dinner: goal.dinner ?? prev.dinner,
      small_meals_per_day: goal.small_meals_per_day ?? prev.small_meals_per_day,
      snacks_per_day: goal.snacks_per_day ?? prev.snacks_per_day,
    }));
  };

  const mutation = useMutation({
    mutationFn: (data: any) => api.post('/goals/', data),
    onSuccess: (res) => { setError(''); navigate(`/plan/${res.data.data.goal_id}`); },
    onError: (err: any) => setError(err.response?.data?.error || 'Nepodařilo se vytvořit plán. Zkuste to znovu.'),
  });

  const update = (field: string, value: any) => setFormData(prev => ({ ...prev, [field]: value }));

  const canAdvance = () => {
    if (step === 0) return formData.prompt.trim().length > 0 && formData.city.trim().length > 0;
    return true;
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
                  {goal.city} · {goal.num_days}d — {goal.prompt?.slice(0, 30)}{goal.prompt?.length > 30 ? '...' : ''}
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

            <Card className="p-8 space-y-12">
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-5">
                {[
                  { id: 'breakfast', label: 'Snídaně', icon: Coffee },
                  { id: 'lunch', label: 'Oběd', icon: UtensilsCrossed },
                  { id: 'dinner', label: 'Večeře', icon: Utensils },
                ].map((meal) => (
                  <button
                    key={meal.id}
                    type="button"
                    onClick={() => update(meal.id, !(formData as any)[meal.id])}
                    className={`p-6 rounded-2xl border-2 transition-all flex flex-col items-center gap-4 ${
                      (formData as any)[meal.id]
                        ? 'bg-green-soft border-green text-ink shadow-xl shadow-green/10'
                        : 'bg-paper border-transparent text-muted hover:text-ink grayscale opacity-40'
                    }`}
                  >
                    <meal.icon size={28} />
                    <span className="font-black uppercase text-[10px] tracking-widest leading-none">{meal.label}</span>
                  </button>
                ))}
              </div>

              <div className="grid sm:grid-cols-2 gap-12">
                <div className="space-y-6">
                  <div className="flex justify-between items-end">
                    <span className="text-[10px] font-black uppercase tracking-widest text-muted italic">Svačinky</span>
                    <span className="text-xl font-black text-green italic">{formData.small_meals_per_day}/den</span>
                  </div>
                  <input type="range" min="0" max="5" className="w-full h-2 bg-kraft rounded-full appearance-none accent-green cursor-pointer" value={formData.small_meals_per_day} onChange={e => update('small_meals_per_day', parseInt(e.target.value))} />
                </div>
                <div className="space-y-6">
                  <div className="flex justify-between items-end">
                    <span className="text-[10px] font-black uppercase tracking-widest text-muted italic">Drobné snacky</span>
                    <span className="text-xl font-black text-green italic">{formData.snacks_per_day}/den</span>
                  </div>
                  <input type="range" min="0" max="3" className="w-full h-2 bg-kraft rounded-full appearance-none accent-green cursor-pointer" value={formData.snacks_per_day} onChange={e => update('snacks_per_day', parseInt(e.target.value))} />
                </div>
              </div>

              <div className="flex flex-wrap gap-2.5 pt-8 border-t border-line">
                <span className="w-full text-[10px] font-black uppercase tracking-widest text-muted mb-2 italic">Délka plánu (dny)</span>
                {[1, 3, 7, 14, 30].map(d => (
                  <button key={d} type="button" onClick={() => update('num_days', d)} className={`px-5 py-2.5 rounded-xl text-[10px] font-black uppercase tracking-widest transition-all border border-line ${formData.num_days === d ? 'bg-green text-white shadow-lg border-green/40' : 'bg-paper text-muted hover:text-ink'}`}>
                    {d}D
                  </button>
                ))}
              </div>
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
            <button type="button" onClick={handleSubmit} disabled={mutation.isPending || !formData.prompt} className="flex items-center gap-4 px-12 h-16 bg-green hover:bg-green-mid text-white rounded-2xl font-black text-lg uppercase tracking-widest shadow-2xl transition-all active:scale-[0.98] disabled:opacity-30">
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
              <button type="button" onClick={handleSubmit} disabled={mutation.isPending || !formData.prompt} className="flex-1 flex items-center justify-center gap-3 h-14 bg-green hover:bg-green-mid text-white rounded-xl font-black uppercase text-xs tracking-widest transition-all disabled:opacity-30">
                {mutation.isPending ? <><Loader2 className="animate-spin" size={20} /> Vytváří se...</> : <>Vygenerovat plán <ArrowRight size={16} /></>}
              </button>
            )}
          </div>
        </div>
      </div>
    </MainLayout>
  );
};
