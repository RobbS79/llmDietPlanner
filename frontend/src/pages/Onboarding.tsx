import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Target, Leaf, AlertTriangle, Home, ChefHat, ShoppingCart, Check, ArrowRight, ArrowLeft, X, Loader2 } from 'lucide-react';
import { api } from '@/lib/api';
import { MainLayout } from '@/components/layout/MainLayout';
import { Card } from '@/components/ui/Card';

const STEPS = [
  { label: 'Cíl', icon: Target },
  { label: 'Styl', icon: Leaf },
  { label: 'Alergie', icon: AlertTriangle },
  { label: 'Domácnost', icon: Home },
  { label: 'Vaření', icon: ChefHat },
  { label: 'Obchod', icon: ShoppingCart },
];

const GOALS = [
  { id: 'lose_weight', label: 'Chci zhubnout', icon: '🎯', desc: 'Snížit váhu zdravým způsobem' },
  { id: 'eat_healthy', label: 'Chci jíst zdravěji', icon: '🥗', desc: 'Vyvážená strava s nutričními hodnotami' },
  { id: 'save_money', label: 'Chci šetřit za jídlo', icon: '💰', desc: 'Levnější nákupy bez plýtvání' },
  { id: 'save_time', label: 'Chci šetřit čas', icon: '⏱️', desc: 'Rychlé recepty a hotový plán' },
];

const DIETARY_STYLES = [
  { id: 'none', label: 'Bez omezení' },
  { id: 'vegetarian', label: 'Vegetarián' },
  { id: 'vegan', label: 'Vegan' },
  { id: 'gluten_free', label: 'Bezlepkové' },
  { id: 'keto', label: 'Keto / Low-carb' },
  { id: 'high_protein', label: 'Vysoko proteinové' },
];

const ALLERGIES = [
  { id: 'none', label: 'Žádné alergie' },
  { id: 'lactose', label: 'Laktóza' },
  { id: 'gluten', label: 'Lepek' },
  { id: 'nuts', label: 'Ořechy' },
  { id: 'eggs', label: 'Vejce' },
  { id: 'fish', label: 'Ryby' },
  { id: 'soy', label: 'Sója' },
];

const COOKING_SKILLS = [
  { id: 'beginner', label: 'Začátečník', desc: 'Jednoduché recepty, málo ingrediencí' },
  { id: 'intermediate', label: 'Pokročilý', desc: 'Středně náročné recepty' },
  { id: 'advanced', label: 'Zkušený kuchař', desc: 'Nebojím se i složitějších receptů' },
];

const COOKING_TIMES = [
  { id: '15min', label: 'Do 15 min' },
  { id: '30min', label: 'Do 30 min' },
  { id: '60min', label: 'Do 60 min' },
  { id: 'unlimited', label: 'Čas nehraje roli' },
];

interface OnboardingData {
  goal: string;
  dietary_styles: string[];
  allergies: string[];
  household_size: number;
  weekly_budget: number;
  cooking_skill: string;
  cooking_time: string;
  country: string;
  shop: string;
}

export const Onboarding = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [step, setStep] = useState(0);
  const [showSummary, setShowSummary] = useState(false);
  const [data, setData] = useState<OnboardingData>({
    goal: '',
    dietary_styles: [],
    allergies: [],
    household_size: 2,
    weekly_budget: 1500,
    cooking_skill: '',
    cooking_time: '',
    country: 'CZ',
    shop: 'ROHLIK',
  });

  const { data: shopsData } = useQuery({
    queryKey: ['shops', data.country],
    queryFn: () => api.get(`/shops/?country=${data.country}`).then(res => res.data.data),
    enabled: step === 5,
  });

  const saveMutation = useMutation({
    mutationFn: (payload: { onboarding_completed: boolean; dietary_preferences: OnboardingData }) =>
      api.patch('/auth/profile/', payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['profile'] });
      setShowSummary(true);
    },
  });

  const skipMutation = useMutation({
    mutationFn: () => api.patch('/auth/profile/', { onboarding_completed: true, dietary_preferences: {} }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['profile'] });
      navigate('/');
    },
  });

  const update = (field: keyof OnboardingData, value: any) => setData(prev => ({ ...prev, [field]: value }));

  const toggleMulti = (field: 'dietary_styles' | 'allergies', id: string) => {
    setData(prev => {
      const current = prev[field];
      if (id === 'none') return { ...prev, [field]: current.includes('none') ? [] : ['none'] };
      const without = current.filter(v => v !== 'none');
      return { ...prev, [field]: without.includes(id) ? without.filter(v => v !== id) : [...without, id] };
    });
  };

  const canAdvance = () => {
    if (step === 0) return data.goal !== '';
    if (step === 3) return data.household_size > 0;
    if (step === 4) return data.cooking_skill !== '' && data.cooking_time !== '';
    return true;
  };

  const next = () => {
    if (step < 5 && canAdvance()) setStep(step + 1);
    else if (step === 5) saveMutation.mutate({ onboarding_completed: true, dietary_preferences: data });
  };
  const back = () => { if (step > 0) setStep(step - 1); };

  const goalLabel: Record<string, string> = { lose_weight: 'Zhubnout', eat_healthy: 'Jíst zdravěji', save_money: 'Šetřit za jídlo', save_time: 'Šetřit čas' };
  const skillLabel: Record<string, string> = { beginner: 'Začátečník', intermediate: 'Pokročilý', advanced: 'Zkušený kuchař' };
  const shopName = data.shop === 'ROHLIK' ? 'Rohlík.cz' : data.shop === 'KOSIK' ? 'Košík.cz' : data.shop;

  if (showSummary) {
    return (
      <MainLayout>
        <div className="max-w-2xl mx-auto px-6 py-16 w-full text-center">
          <div className="inline-flex items-center gap-2 bg-emerald-600/10 border border-emerald-500/20 rounded-full px-4 py-1.5 mb-8">
            <Check size={14} className="text-emerald-400" />
            <span className="text-[10px] font-black text-emerald-400 uppercase tracking-widest">Profil připraven</span>
          </div>
          <h1 className="text-4xl sm:text-5xl font-black text-white tracking-tighter uppercase italic leading-[0.85] mb-8">
            Váš personalizovaný<br /><span className="text-emerald-500 not-italic">plán.</span>
          </h1>

          <Card className="p-8 text-left mb-10 space-y-4">
            <Row label="Cíl" value={goalLabel[data.goal] || data.goal} />
            {data.dietary_styles.length > 0 && data.dietary_styles[0] !== 'none' && (
              <Row label="Styl" value={data.dietary_styles.map(s => DIETARY_STYLES.find(d => d.id === s)?.label || s).join(', ')} />
            )}
            {data.allergies.length > 0 && data.allergies[0] !== 'none' && (
              <Row label="Alergie" value={data.allergies.map(a => ALLERGIES.find(al => al.id === a)?.label || a).join(', ')} />
            )}
            <Row label="Domácnost" value={`${data.household_size} ${data.household_size === 1 ? 'osoba' : data.household_size < 5 ? 'osoby' : 'osob'}`} />
            <Row label="Rozpočet" value={`${data.weekly_budget.toLocaleString('cs-CZ')} ${data.country === 'SK' ? 'EUR' : 'CZK'}/týden`} />
            <Row label="Vaření" value={`${skillLabel[data.cooking_skill] || ''}, ${COOKING_TIMES.find(t => t.id === data.cooking_time)?.label || ''}`} />
            <Row label="Obchod" value={shopName} />
          </Card>

          <button
            onClick={() => navigate('/create', { state: { fromOnboarding: data } })}
            className="bg-white text-black px-12 py-5 rounded-2xl font-black uppercase text-sm tracking-widest shadow-2xl hover:shadow-white/10 transition-all active:scale-[0.98] inline-flex items-center gap-3"
          >
            Vytvořte si jídelníček <ArrowRight size={18} />
          </button>
          <p className="text-zinc-500 text-xs font-bold mt-6 uppercase tracking-widest">10 plánů zdarma. Bez kreditní karty.</p>
        </div>
      </MainLayout>
    );
  }

  return (
    <MainLayout>
      <div className="max-w-3xl mx-auto px-6 py-12 w-full pb-32 sm:pb-12">
        <div className="flex items-center justify-between mb-8">
          <h1 className="text-3xl sm:text-4xl font-black text-white tracking-tighter uppercase italic leading-none">
            O vás<span className="text-emerald-500 not-italic">.</span>
          </h1>
          <button onClick={() => skipMutation.mutate()} className="text-zinc-500 hover:text-zinc-300 text-xs font-bold uppercase tracking-widest transition-colors flex items-center gap-1.5">
            <X size={14} /> Přeskočit
          </button>
        </div>

        {/* Progress bar */}
        <div className="mb-12 max-w-md mx-auto">
          <div className="flex items-center justify-between mb-3">
            {STEPS.map((s, i) => (
              <button
                key={i}
                type="button"
                onClick={() => { if (i <= step) setStep(i); }}
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
            <div className="h-full bg-gradient-to-r from-emerald-600 to-emerald-400 rounded-full transition-all duration-500 ease-out" style={{ width: `${((step + 1) / STEPS.length) * 100}%` }} />
          </div>
          <p className="text-center text-[10px] font-black text-zinc-500 uppercase tracking-widest mt-3">Krok {step + 1} z {STEPS.length}</p>
        </div>

        {/* Step 0: Goal */}
        {step === 0 && (
          <section className="space-y-8 text-left animate-[fadeIn_0.3s_ease-out]">
            <StepHeader num={1} title="Jaký je váš hlavní cíl?" />
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              {GOALS.map(g => (
                <button key={g.id} type="button" onClick={() => update('goal', g.id)}
                  className={`p-6 rounded-2xl border-2 transition-all text-left ${
                    data.goal === g.id ? 'bg-emerald-600/10 border-emerald-600 text-white shadow-xl shadow-emerald-500/10' : 'bg-zinc-950 border-transparent text-zinc-500 hover:text-zinc-300'
                  }`}>
                  <span className="text-2xl mb-3 block">{g.icon}</span>
                  <span className="font-black uppercase text-sm tracking-tight block">{g.label}</span>
                  <span className="text-xs text-zinc-500 mt-1 block">{g.desc}</span>
                </button>
              ))}
            </div>
          </section>
        )}

        {/* Step 1: Dietary Style */}
        {step === 1 && (
          <section className="space-y-8 text-left animate-[fadeIn_0.3s_ease-out]">
            <StepHeader num={2} title="Jaký stravovací styl preferujete?" />
            <div className="flex flex-wrap gap-3">
              {DIETARY_STYLES.map(s => (
                <button key={s.id} type="button" onClick={() => toggleMulti('dietary_styles', s.id)}
                  className={`px-5 py-3 rounded-xl text-sm font-bold transition-all border ${
                    data.dietary_styles.includes(s.id) ? 'bg-emerald-600/10 border-emerald-500 text-emerald-400' : 'bg-zinc-950 border-zinc-800 text-zinc-500 hover:text-zinc-300'
                  }`}>
                  {data.dietary_styles.includes(s.id) && <Check size={14} className="inline mr-2" />}{s.label}
                </button>
              ))}
            </div>
          </section>
        )}

        {/* Step 2: Allergies */}
        {step === 2 && (
          <section className="space-y-8 text-left animate-[fadeIn_0.3s_ease-out]">
            <StepHeader num={3} title="Máte nějaké alergie?" />
            <div className="flex flex-wrap gap-3">
              {ALLERGIES.map(a => (
                <button key={a.id} type="button" onClick={() => toggleMulti('allergies', a.id)}
                  className={`px-5 py-3 rounded-xl text-sm font-bold transition-all border ${
                    data.allergies.includes(a.id) ? 'bg-emerald-600/10 border-emerald-500 text-emerald-400' : 'bg-zinc-950 border-zinc-800 text-zinc-500 hover:text-zinc-300'
                  }`}>
                  {data.allergies.includes(a.id) && <Check size={14} className="inline mr-2" />}{a.label}
                </button>
              ))}
            </div>
          </section>
        )}

        {/* Step 3: Household & Budget */}
        {step === 3 && (
          <section className="space-y-8 text-left animate-[fadeIn_0.3s_ease-out]">
            <StepHeader num={4} title="Domácnost a rozpočet" />
            <Card className="p-8 space-y-10">
              <div>
                <label className="text-[10px] font-black uppercase tracking-widest text-zinc-600 mb-4 block">Počet osob v domácnosti</label>
                <div className="flex flex-wrap gap-2.5">
                  {[1, 2, 3, 4, 5, 6].map(n => (
                    <button key={n} type="button" onClick={() => update('household_size', n)}
                      className={`px-5 py-2.5 rounded-xl text-[10px] font-black uppercase tracking-widest transition-all border border-zinc-800 ${
                        data.household_size === n ? 'bg-emerald-600 text-white shadow-lg border-emerald-500' : 'bg-zinc-950 text-zinc-600 hover:text-zinc-400'
                      }`}>
                      {n}{n === 6 ? '+' : ''}
                    </button>
                  ))}
                </div>
              </div>
              <div>
                <div className="flex justify-between items-end mb-4">
                  <label className="text-[10px] font-black uppercase tracking-widest text-zinc-600">Týdenní rozpočet na jídlo</label>
                  <span className="text-xl font-black text-emerald-500 italic">
                    {data.weekly_budget.toLocaleString('cs-CZ')} {data.country === 'SK' ? 'EUR' : 'CZK'}
                  </span>
                </div>
                <input type="range"
                  min={data.country === 'SK' ? 20 : 500}
                  max={data.country === 'SK' ? 200 : 5000}
                  step={data.country === 'SK' ? 5 : 100}
                  value={data.weekly_budget}
                  onChange={e => update('weekly_budget', parseInt(e.target.value))}
                  className="w-full h-2 bg-zinc-800 rounded-full appearance-none accent-emerald-600 cursor-pointer"
                />
                <div className="flex justify-between text-[9px] text-zinc-600 mt-2">
                  <span>{data.country === 'SK' ? '20 EUR' : '500 CZK'}</span>
                  <span>{data.country === 'SK' ? '200 EUR' : '5 000 CZK'}</span>
                </div>
              </div>
            </Card>
          </section>
        )}

        {/* Step 4: Cooking */}
        {step === 4 && (
          <section className="space-y-8 text-left animate-[fadeIn_0.3s_ease-out]">
            <StepHeader num={5} title="Jak rádi vaříte?" />
            <Card className="p-8 space-y-10">
              <div>
                <label className="text-[10px] font-black uppercase tracking-widest text-zinc-600 mb-4 block">Úroveň vaření</label>
                <div className="grid sm:grid-cols-3 gap-4">
                  {COOKING_SKILLS.map(s => (
                    <button key={s.id} type="button" onClick={() => update('cooking_skill', s.id)}
                      className={`p-5 rounded-2xl border-2 transition-all text-left ${
                        data.cooking_skill === s.id ? 'bg-emerald-600/10 border-emerald-600 text-white' : 'bg-zinc-950 border-transparent text-zinc-500 hover:text-zinc-300'
                      }`}>
                      <span className="font-black uppercase text-xs tracking-tight block">{s.label}</span>
                      <span className="text-[10px] text-zinc-500 mt-1 block">{s.desc}</span>
                    </button>
                  ))}
                </div>
              </div>
              <div>
                <label className="text-[10px] font-black uppercase tracking-widest text-zinc-600 mb-4 block">Kolik času máte na přípravu jídla?</label>
                <div className="flex flex-wrap gap-3">
                  {COOKING_TIMES.map(t => (
                    <button key={t.id} type="button" onClick={() => update('cooking_time', t.id)}
                      className={`px-5 py-3 rounded-xl text-sm font-bold transition-all border ${
                        data.cooking_time === t.id ? 'bg-emerald-600/10 border-emerald-500 text-emerald-400' : 'bg-zinc-950 border-zinc-800 text-zinc-500 hover:text-zinc-300'
                      }`}>
                      {t.label}
                    </button>
                  ))}
                </div>
              </div>
            </Card>
          </section>
        )}

        {/* Step 5: Store */}
        {step === 5 && (
          <section className="space-y-8 text-left animate-[fadeIn_0.3s_ease-out]">
            <StepHeader num={6} title="Kde nakupujete?" />
            <Card className="p-8 space-y-8">
              <div className="space-y-3">
                <label className="text-[10px] font-black uppercase tracking-widest text-zinc-600">Země</label>
                <select value={data.country} onChange={e => { update('country', e.target.value); update('weekly_budget', e.target.value === 'SK' ? 60 : 1500); }}
                  className="w-full bg-zinc-950 border border-zinc-800 rounded-xl h-14 px-5 text-xs font-black text-white uppercase tracking-widest focus:outline-none appearance-none cursor-pointer">
                  <option value="CZ">Česko (CZK)</option>
                  <option value="SK">Slovensko (EUR)</option>
                </select>
              </div>
              <div className="grid sm:grid-cols-2 gap-5">
                {shopsData?.shops?.map((shop: any) => (
                  <button key={shop.code} type="button" onClick={() => update('shop', shop.code)}
                    className={`p-8 rounded-2xl border-2 text-left transition-all relative overflow-hidden ${
                      data.shop === shop.code ? 'bg-emerald-600/10 border-emerald-600 text-white shadow-xl' : 'bg-zinc-950 border-transparent text-zinc-600 hover:bg-zinc-900'
                    }`}>
                    <span className="font-black text-base block uppercase tracking-tight italic leading-none mb-1">{shop.name}</span>
                    <span className="text-[9px] font-black uppercase tracking-widest opacity-40 italic">Dostupné</span>
                    {data.shop === shop.code && <div className="absolute top-8 right-8 text-emerald-500 bg-white p-1 rounded-lg"><Check size={14} strokeWidth={4} /></div>}
                  </button>
                ))}
              </div>
            </Card>
          </section>
        )}

        {/* Desktop navigation */}
        <div className="hidden sm:flex items-center justify-between mt-12 gap-4">
          {step > 0 ? (
            <button type="button" onClick={back} className="flex items-center gap-3 px-8 h-14 border border-zinc-800 text-zinc-400 hover:text-white rounded-xl font-black uppercase text-[10px] tracking-widest transition-all">
              <ArrowLeft size={16} /> Zpět
            </button>
          ) : <div />}
          <button type="button" onClick={next} disabled={!canAdvance() || saveMutation.isPending}
            className="flex items-center gap-3 px-10 h-14 bg-emerald-600 hover:bg-emerald-500 text-white rounded-xl font-black uppercase text-[10px] tracking-widest transition-all active:scale-[0.98] disabled:opacity-30 shadow-lg">
            {saveMutation.isPending ? <Loader2 size={16} className="animate-spin" /> : step === 5 ? 'Dokončit' : 'Další krok'} {!saveMutation.isPending && <ArrowRight size={16} />}
          </button>
        </div>

        {/* Mobile sticky bottom bar */}
        <div className="fixed bottom-0 left-0 right-0 z-50 p-4 bg-[#09090b]/95 backdrop-blur-lg border-t border-zinc-800 sm:hidden">
          <div className="flex gap-3">
            {step > 0 && (
              <button type="button" onClick={back} className="flex items-center justify-center w-14 h-14 border border-zinc-800 text-zinc-400 rounded-xl transition-all">
                <ArrowLeft size={20} />
              </button>
            )}
            <button type="button" onClick={next} disabled={!canAdvance() || saveMutation.isPending}
              className="flex-1 flex items-center justify-center gap-3 h-14 bg-emerald-600 hover:bg-emerald-500 text-white rounded-xl font-black uppercase text-xs tracking-widest transition-all disabled:opacity-30">
              {saveMutation.isPending ? <Loader2 size={20} className="animate-spin" /> : step === 5 ? 'Dokončit' : 'Další krok'} {!saveMutation.isPending && <ArrowRight size={16} />}
            </button>
          </div>
        </div>
      </div>
    </MainLayout>
  );
};

function StepHeader({ num, title }: { num: number; title: string }) {
  return (
    <div className="flex items-center gap-4 text-white">
      <div className="w-8 h-8 rounded-lg bg-emerald-600 flex items-center justify-center font-black italic shadow-lg">{num}</div>
      <h2 className="text-2xl font-black uppercase tracking-tight italic leading-none">{title}</h2>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between items-center py-3 border-b border-zinc-800 last:border-0">
      <span className="text-[10px] font-black text-zinc-500 uppercase tracking-widest">{label}</span>
      <span className="text-sm font-bold text-white">{value}</span>
    </div>
  );
}
