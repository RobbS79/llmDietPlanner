import { useState, useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useQuery, useMutation } from '@tanstack/react-query';
import { Loader2, BrainCircuit, Coffee, UtensilsCrossed, Utensils, Check, AlertCircle, RotateCcw, ArrowRight, ArrowLeft, ShoppingCart, ChefHat, Truck, Shuffle, FileText, ChevronDown } from 'lucide-react';
import { api } from '@/lib/api';
import { MainLayout } from '@/components/layout/MainLayout';
import { Card } from '@/components/ui/Card';
import { ProtocolUpload } from '@/components/ProtocolUpload';

const STEPS = [
  { label: 'Cíle', icon: BrainCircuit },
  { label: 'Jídla', icon: ChefHat },
  { label: 'Obchod', icon: ShoppingCart },
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
    shop: 'ROHLIK',
    store_mode: 'single' as 'single' | 'mix_cost' | 'mix_trips',
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

    const goalMap: Record<string, string> = { lose_weight: 'Chci zhubnout', eat_healthy: 'Chci jíst zdravěji', save_money: 'Chci šetřit za jídlo', save_time: 'Chci šetřit čas při vaření' };
    const styleMap: Record<string, string> = { vegetarian: 'vegetariánská strava', vegan: 'veganská strava', gluten_free: 'bezlepková dieta', keto: 'keto dieta', high_protein: 'vysoko proteinová strava' };
    const allergyMap: Record<string, string> = { lactose: 'bez laktózy', gluten: 'bez lepku', nuts: 'bez ořechů', eggs: 'bez vajec', fish: 'bez ryb', soy: 'bez sóji' };
    const skillMap: Record<string, string> = { beginner: 'jednoduché recepty pro začátečníky', intermediate: 'středně náročné recepty', advanced: 'i složitější recepty' };
    const timeMap: Record<string, string> = { '15min': 'Max 15 minut na přípravu', '30min': 'Max 30 minut na přípravu', '60min': 'Max 60 minut na přípravu' };

    const parts: string[] = [];
    if (prefs.goal) parts.push(goalMap[prefs.goal] || '');
    const styles = (prefs.dietary_styles || []).filter((s: string) => s !== 'none').map((s: string) => styleMap[s]).filter(Boolean);
    if (styles.length) parts.push(styles.join(', '));
    const allergies = (prefs.allergies || []).filter((a: string) => a !== 'none').map((a: string) => allergyMap[a]).filter(Boolean);
    if (allergies.length) parts.push(allergies.join(', '));
    if (prefs.household_size) parts.push(`Pro ${prefs.household_size} ${prefs.household_size === 1 ? 'osobu' : 'osoby'}`);
    if (prefs.weekly_budget) parts.push(`Rozpočet ${prefs.weekly_budget} ${prefs.country === 'SK' ? 'EUR' : 'CZK'}/týden`);
    if (prefs.cooking_skill) parts.push(skillMap[prefs.cooking_skill] || '');
    if (prefs.cooking_time && prefs.cooking_time !== 'unlimited') parts.push(timeMap[prefs.cooking_time] || '');

    const prompt = parts.filter(Boolean).join('. ') + '.';
    const restrictions = allergies.length > 0 ? allergies.join(', ') : '';

    setFormData(prev => ({
      ...prev,
      prompt: prev.prompt || prompt,
      dietary_restrictions: prev.dietary_restrictions || restrictions,
      country: prefs.country || prev.country,
      language_code: prefs.country === 'SK' ? 'sk' : 'cs',
      shop: prefs.shop || prev.shop,
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
      shop: goal.shop || prev.shop,
      store_mode: goal.store_mode || prev.store_mode,
    }));
  };

  const { data: shopsData } = useQuery({
    queryKey: ['shops', formData.country],
    queryFn: () => api.get(`/shops/?country=${formData.country}`).then(res => res.data.data),
    enabled: !!formData.country,
  });

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

  const next = () => { if (step < 2 && canAdvance()) setStep(step + 1); };
  const back = () => { if (step > 0) setStep(step - 1); };

  const handleSubmit = () => {
    setError('');
    mutation.mutate(formData);
  };

  return (
    <MainLayout>
      <div className="max-w-4xl mx-auto px-6 py-12 w-full pb-32 sm:pb-12">
        <header className="mb-12 text-center space-y-4">
          <h1 className="text-5xl sm:text-7xl font-black text-white tracking-tighter uppercase italic leading-[0.85]">
            Nový<br /><span className="text-emerald-500 not-italic">plán.</span>
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
                  i === step ? 'text-emerald-400' : i < step ? 'text-emerald-400 cursor-pointer' : 'text-zinc-600'
                }`}
              >
                <div className={`w-8 h-8 rounded-lg flex items-center justify-center text-sm font-black transition-all ${
                  i === step ? 'bg-emerald-600 text-white shadow-lg' : i < step ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30' : 'bg-zinc-900 text-zinc-600 border border-zinc-800'
                }`}>
                  {i < step ? <Check size={14} /> : i + 1}
                </div>
                <span className="hidden sm:inline">{s.label}</span>
              </button>
            ))}
          </div>
          <div className="h-1 bg-zinc-800 rounded-full overflow-hidden">
            <div
              className="h-full bg-gradient-to-r from-emerald-600 to-emerald-400 rounded-full transition-all duration-500 ease-out"
              style={{ width: `${((step + 1) / STEPS.length) * 100}%` }}
            />
          </div>
          <p className="text-center text-[10px] font-black text-zinc-500 uppercase tracking-widest mt-3">
            Krok {step + 1} z {STEPS.length}
          </p>
        </div>

        {completedGoals.length > 0 && step === 0 && (
          <div className="mb-12 p-6 bg-zinc-900/50 border border-zinc-800 rounded-2xl text-left">
            <div className="flex items-center gap-3 mb-4">
              <RotateCcw size={16} className="text-emerald-500" />
              <span className="text-[10px] font-black uppercase tracking-widest text-zinc-500">Použít předchozí nastavení</span>
            </div>
            <div className="flex flex-wrap gap-2">
              {completedGoals.slice(0, 5).map((goal: any) => (
                <button
                  key={goal.id}
                  type="button"
                  onClick={() => prefillFrom(goal)}
                  className="px-4 py-2.5 bg-zinc-950 border border-zinc-800 rounded-xl text-xs font-bold text-zinc-400 hover:text-white hover:border-emerald-500/50 transition-all truncate max-w-[220px]"
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
            <div className="flex items-center gap-4 text-white">
              <div className="w-8 h-8 rounded-lg bg-emerald-600 flex items-center justify-center font-black italic shadow-lg">1</div>
              <h2 className="text-2xl font-black uppercase tracking-tight italic leading-none">Stravovací cíle</h2>
            </div>

            <Card className="p-8 space-y-10">
              <div className="space-y-4">
                <label className="text-[10px] font-black uppercase tracking-widest text-zinc-600 flex items-center gap-2 italic">
                  <BrainCircuit size={14} className="text-emerald-500" /> Popište své cíle
                </label>
                <textarea
                  autoFocus
                  className="w-full bg-black/40 border border-zinc-800 rounded-2xl p-6 text-lg font-bold text-white placeholder:text-zinc-600 focus:outline-none focus:ring-2 focus:ring-emerald-600/50 transition-all min-h-[220px] leading-relaxed"
                  placeholder="např. Vysoko proteinová dieta, 2400 kcal denně. Bez mléčných výrobků. Cenově dostupné suroviny v Praze..."
                  value={formData.prompt}
                  onChange={e => update('prompt', e.target.value)}
                />
              </div>

              <div className="grid grid-cols-2 gap-8">
                <div className="space-y-3">
                  <label className="text-[10px] font-black uppercase tracking-widest text-zinc-600">Země</label>
                  <select
                    className="w-full bg-zinc-950 border border-zinc-800 rounded-xl h-14 px-5 text-xs font-black text-white uppercase tracking-widest focus:outline-none appearance-none cursor-pointer"
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
                  <label className="text-[10px] font-black uppercase tracking-widest text-zinc-600">Město</label>
                  <input type="text" className="w-full bg-zinc-950 border border-zinc-800 rounded-xl h-14 px-5 text-sm font-black text-white placeholder:text-zinc-600 focus:outline-none" placeholder="např. Praha" value={formData.city} onChange={e => update('city', e.target.value)} />
                </div>
              </div>

              {/* Protocol upload section */}
              <div className="pt-8 border-t border-zinc-800">
                <button
                  type="button"
                  onClick={() => setProtocolExpanded(!protocolExpanded)}
                  className="flex items-center gap-3 w-full text-left group"
                >
                  <FileText size={16} className={formData.historic_plan_id ? 'text-emerald-500' : 'text-zinc-600'} />
                  <span className="text-[10px] font-black uppercase tracking-widest text-zinc-500 group-hover:text-zinc-400 transition-colors">
                    Máte dietní protokol od specialisty?
                  </span>
                  {formData.historic_plan_id && (
                    <span className="text-[9px] font-bold text-emerald-500 bg-emerald-500/10 px-2 py-0.5 rounded-md">
                      Připojeno
                    </span>
                  )}
                  <ChevronDown size={14} className={`text-zinc-600 ml-auto transition-transform ${protocolExpanded ? 'rotate-180' : ''}`} />
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
            <div className="flex items-center gap-4 text-white">
              <div className="w-8 h-8 rounded-lg bg-emerald-600 flex items-center justify-center font-black italic shadow-lg">2</div>
              <h2 className="text-2xl font-black uppercase tracking-tight italic leading-none">Nastavení jídel</h2>
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
                        ? 'bg-emerald-600/10 border-emerald-600 text-white shadow-xl shadow-emerald-500/10'
                        : 'bg-zinc-950 border-transparent text-zinc-600 hover:text-zinc-400 grayscale opacity-40'
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
                    <span className="text-[10px] font-black uppercase tracking-widest text-zinc-600 italic">Svačinky</span>
                    <span className="text-xl font-black text-emerald-500 italic">{formData.small_meals_per_day}/den</span>
                  </div>
                  <input type="range" min="0" max="5" className="w-full h-2 bg-zinc-800 rounded-full appearance-none accent-emerald-600 cursor-pointer" value={formData.small_meals_per_day} onChange={e => update('small_meals_per_day', parseInt(e.target.value))} />
                </div>
                <div className="space-y-6">
                  <div className="flex justify-between items-end">
                    <span className="text-[10px] font-black uppercase tracking-widest text-zinc-600 italic">Drobné snacky</span>
                    <span className="text-xl font-black text-emerald-500 italic">{formData.snacks_per_day}/den</span>
                  </div>
                  <input type="range" min="0" max="3" className="w-full h-2 bg-zinc-800 rounded-full appearance-none accent-emerald-600 cursor-pointer" value={formData.snacks_per_day} onChange={e => update('snacks_per_day', parseInt(e.target.value))} />
                </div>
              </div>

              <div className="flex flex-wrap gap-2.5 pt-8 border-t border-zinc-800">
                <span className="w-full text-[10px] font-black uppercase tracking-widest text-zinc-500 mb-2 italic">Délka plánu (dny)</span>
                {[1, 3, 7, 14, 30].map(d => (
                  <button key={d} type="button" onClick={() => update('num_days', d)} className={`px-5 py-2.5 rounded-xl text-[10px] font-black uppercase tracking-widest transition-all border border-zinc-800 ${formData.num_days === d ? 'bg-emerald-600 text-white shadow-lg border-emerald-500' : 'bg-zinc-950 text-zinc-600 hover:text-zinc-400'}`}>
                    {d}D
                  </button>
                ))}
              </div>
            </Card>
          </section>
        )}

        {/* Step 3: Preferred Store */}
        {step === 2 && (
          <section className="space-y-8 text-left animate-[fadeIn_0.3s_ease-out]">
            <div className="flex items-center gap-4 text-white">
              <div className="w-8 h-8 rounded-lg bg-emerald-600 flex items-center justify-center font-black italic shadow-lg">3</div>
              <h2 className="text-2xl font-black uppercase tracking-tight italic leading-none">Preferovaný obchod</h2>
            </div>

            <Card className="p-8 space-y-8">
              <div className="grid sm:grid-cols-2 gap-5">
                {shopsData?.shops?.map((shop: any) => (
                  <button
                    key={shop.code} type="button" onClick={() => update('shop', shop.code)}
                    className={`p-8 rounded-2xl border-2 text-left transition-all relative overflow-hidden group ${
                      formData.shop === shop.code
                        ? 'bg-emerald-600/10 border-emerald-600 text-white shadow-xl'
                        : 'bg-zinc-950 border-transparent text-zinc-600 hover:bg-zinc-900'
                    }`}
                  >
                    <span className="font-black text-base block uppercase tracking-tight italic leading-none mb-1">{shop.name}</span>
                    <div className="flex items-center gap-2 mt-1">
                      {shop.is_online_only && (
                        <span className="inline-flex items-center gap-1 text-[8px] font-black uppercase tracking-widest text-sky-400 bg-sky-400/10 px-2 py-0.5 rounded-md">
                          <Truck size={10} /> Online doručení
                        </span>
                      )}
                      {!shop.is_online_only && (
                        <span className="text-[9px] font-black uppercase tracking-widest opacity-40 italic">Kamenný obchod</span>
                      )}
                    </div>
                    {formData.shop === shop.code && <div className="absolute top-8 right-8 text-emerald-500 bg-white p-1 rounded-lg"><Check size={14} strokeWidth={4} /></div>}
                  </button>
                ))}
              </div>

              <div className="pt-6 border-t border-zinc-800">
                <div className="flex items-center gap-3 mb-4">
                  <Shuffle size={16} className="text-emerald-500" />
                  <span className="text-[10px] font-black uppercase tracking-widest text-zinc-500 italic">Nákupní režim</span>
                </div>
                <div className="flex gap-3">
                  <button
                    type="button"
                    onClick={() => update('store_mode', 'single')}
                    className={`flex-1 p-5 rounded-xl border-2 text-left transition-all ${
                      formData.store_mode === 'single'
                        ? 'bg-emerald-600/10 border-emerald-600 text-white'
                        : 'bg-zinc-950 border-transparent text-zinc-600 hover:bg-zinc-900'
                    }`}
                  >
                    <span className="font-black text-xs block uppercase tracking-tight">Jeden obchod</span>
                    <span className="text-[9px] text-zinc-500 mt-1 block">Vše z jednoho obchodu</span>
                  </button>
                  <button
                    type="button"
                    onClick={() => update('store_mode', 'mix_trips')}
                    className={`flex-1 p-5 rounded-xl border-2 text-left transition-all ${
                      formData.store_mode === 'mix_trips'
                        ? 'bg-emerald-600/10 border-emerald-600 text-white'
                        : 'bg-zinc-950 border-transparent text-zinc-600 hover:bg-zinc-900'
                    }`}
                  >
                    <span className="font-black text-xs block uppercase tracking-tight">Více obchodů</span>
                    <span className="text-[9px] text-zinc-500 mt-1 block">Nejlepší ceny z více obchodů</span>
                  </button>
                </div>
                {formData.store_mode === 'mix_trips' && (
                  <p className="text-[10px] text-zinc-500 mt-3 leading-relaxed">
                    Systém porovná ceny a vybere nejlevnější položky z různých obchodů. Nákupní seznam bude seskupen podle obchodu.
                  </p>
                )}
              </div>
            </Card>

            {/* Summary card */}
            <Card className="p-8 border-emerald-500/10">
              <h3 className="text-[10px] font-black uppercase tracking-widest text-zinc-500 mb-6">Shrnutí vašeho plánu</h3>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-sm">
                <div>
                  <p className="text-[9px] font-black text-zinc-600 uppercase tracking-widest mb-1">Město</p>
                  <p className="font-black text-white">{formData.city || '—'}</p>
                </div>
                <div>
                  <p className="text-[9px] font-black text-zinc-600 uppercase tracking-widest mb-1">Délka</p>
                  <p className="font-black text-white">{formData.num_days} dní</p>
                </div>
                <div>
                  <p className="text-[9px] font-black text-zinc-600 uppercase tracking-widest mb-1">Jídla</p>
                  <p className="font-black text-white">
                    {[formData.breakfast && 'S', formData.lunch && 'O', formData.dinner && 'V'].filter(Boolean).join('+')}
                    {formData.small_meals_per_day > 0 && ` +${formData.small_meals_per_day}sv`}
                  </p>
                </div>
                <div>
                  <p className="text-[9px] font-black text-zinc-600 uppercase tracking-widest mb-1">Obchod</p>
                  <p className="font-black text-white">{formData.shop}</p>
                  <p className="text-[9px] text-zinc-500 mt-0.5">{formData.store_mode === 'single' ? 'Jeden obchod' : 'Více obchodů'}</p>
                </div>
              </div>
            </Card>
          </section>
        )}

        <div aria-live="polite" aria-atomic="true">
        {error && (
          <div role="alert" className="flex items-center gap-3 bg-rose-500/10 border border-rose-500/20 text-rose-400 rounded-xl p-5 text-sm font-bold mt-8">
            <AlertCircle size={18} className="shrink-0" />
            <span>{error}</span>
          </div>
        )}
        </div>

        {/* Desktop navigation buttons */}
        <div className="hidden sm:flex items-center justify-between mt-12 gap-4">
          {step > 0 ? (
            <button type="button" onClick={back} className="flex items-center gap-3 px-8 h-14 border border-zinc-800 text-zinc-400 hover:text-white rounded-xl font-black uppercase text-[10px] tracking-widest transition-all">
              <ArrowLeft size={16} /> Zpět
            </button>
          ) : <div />}

          {step < 2 ? (
            <button type="button" onClick={next} disabled={!canAdvance()} className="flex items-center gap-3 px-10 h-14 bg-emerald-600 hover:bg-emerald-500 text-white rounded-xl font-black uppercase text-[10px] tracking-widest transition-all active:scale-[0.98] disabled:opacity-30 shadow-lg">
              Další krok <ArrowRight size={16} />
            </button>
          ) : (
            <button type="button" onClick={handleSubmit} disabled={mutation.isPending || !formData.prompt} className="flex items-center gap-4 px-12 h-16 bg-white text-black rounded-2xl font-black text-lg uppercase tracking-widest shadow-2xl transition-all active:scale-[0.98] disabled:opacity-30">
              {mutation.isPending ? <><Loader2 className="animate-spin" size={24} /> Vytváří se...</> : <>Vygenerovat plán <ArrowRight size={20} /></>}
            </button>
          )}
        </div>

        {/* Mobile sticky bottom bar */}
        <div className="fixed bottom-0 left-0 right-0 z-50 p-4 bg-[#09090b]/95 backdrop-blur-lg border-t border-zinc-800 sm:hidden">
          <div className="flex gap-3">
            {step > 0 && (
              <button type="button" onClick={back} className="flex items-center justify-center w-14 h-14 border border-zinc-800 text-zinc-400 rounded-xl transition-all">
                <ArrowLeft size={20} />
              </button>
            )}
            {step < 2 ? (
              <button type="button" onClick={next} disabled={!canAdvance()} className="flex-1 flex items-center justify-center gap-3 h-14 bg-emerald-600 hover:bg-emerald-500 text-white rounded-xl font-black uppercase text-xs tracking-widest transition-all disabled:opacity-30">
                Další krok <ArrowRight size={16} />
              </button>
            ) : (
              <button type="button" onClick={handleSubmit} disabled={mutation.isPending || !formData.prompt} className="flex-1 flex items-center justify-center gap-3 h-14 bg-white text-black rounded-xl font-black uppercase text-xs tracking-widest transition-all disabled:opacity-30">
                {mutation.isPending ? <><Loader2 className="animate-spin" size={20} /> Vytváří se...</> : <>Vygenerovat plán <ArrowRight size={16} /></>}
              </button>
            )}
          </div>
        </div>
      </div>
    </MainLayout>
  );
};
