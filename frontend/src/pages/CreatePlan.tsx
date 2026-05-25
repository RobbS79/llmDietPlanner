import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery, useMutation } from '@tanstack/react-query';
import { Loader2, BrainCircuit, Coffee, UtensilsCrossed, Utensils, Check, AlertCircle, RotateCcw } from 'lucide-react';
import { api } from '@/lib/api';
import { MainLayout } from '@/components/layout/MainLayout';
import { Card } from '@/components/ui/Card';

export const CreatePlan = () => {
  const navigate = useNavigate();
  const [error, setError] = useState('');
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
    goal_id: null as number | null,
  });

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
    onError: (err: any) => setError(err.response?.data?.error || 'Failed to create plan. Please try again.'),
  });

  const update = (field: string, value: any) => setFormData(prev => ({ ...prev, [field]: value }));

  return (
    <MainLayout>
      <div className="max-w-4xl mx-auto px-6 py-12 w-full">
        <header className="mb-20 text-center space-y-4">
          <p className="text-[10px] font-black text-indigo-500 uppercase tracking-[1em]">Krok 1: Nastaveni</p>
          <h1 className="text-7xl font-black text-white tracking-tighter uppercase italic leading-[0.85]">
            Novy<br /><span className="text-indigo-500 not-italic">plan.</span>
          </h1>
        </header>

        {completedGoals.length > 0 && (
          <div className="mb-12 p-6 bg-zinc-900/50 border border-zinc-800 rounded-2xl text-left">
            <div className="flex items-center gap-3 mb-4">
              <RotateCcw size={16} className="text-indigo-500" />
              <span className="text-[10px] font-black uppercase tracking-widest text-zinc-500">Pouzit predchozi nastaveni</span>
            </div>
            <div className="flex flex-wrap gap-2">
              {completedGoals.slice(0, 5).map((goal: any) => (
                <button
                  key={goal.id}
                  type="button"
                  onClick={() => prefillFrom(goal)}
                  className="px-4 py-2.5 bg-zinc-950 border border-zinc-800 rounded-xl text-xs font-bold text-zinc-400 hover:text-white hover:border-indigo-500/50 transition-all truncate max-w-[220px]"
                  title={goal.prompt}
                >
                  {goal.city} · {goal.num_days}d — {goal.prompt?.slice(0, 30)}{goal.prompt?.length > 30 ? '...' : ''}
                </button>
              ))}
            </div>
          </div>
        )}

        <form onSubmit={e => { e.preventDefault(); setError(''); mutation.mutate(formData); }} className="space-y-12">
          {/* Dietary Goals */}
          <section className="space-y-8 text-left">
            <div className="flex items-center gap-4 text-white">
              <div className="w-8 h-8 rounded-lg bg-indigo-600 flex items-center justify-center font-black italic shadow-lg">1</div>
              <h2 className="text-2xl font-black uppercase tracking-tight italic leading-none">Stravovaci cile</h2>
            </div>

            <Card className="p-8 space-y-10">
              <div className="space-y-4">
                <label className="text-[10px] font-black uppercase tracking-widest text-zinc-600 flex items-center gap-2 italic">
                  <BrainCircuit size={14} className="text-indigo-500" /> Popiste sve cile
                </label>
                <textarea
                  required
                  className="w-full bg-black/40 border border-zinc-800 rounded-2xl p-6 text-lg font-bold text-white placeholder:text-zinc-600 focus:outline-none focus:ring-2 focus:ring-indigo-600/50 transition-all min-h-[220px] leading-relaxed"
                  placeholder="napr. Vysoko proteinova dieta, 2400 kcal denne. Bez mlecnych vyrobku. Cenove dostupne suroviny v Praze..."
                  value={formData.prompt}
                  onChange={e => update('prompt', e.target.value)}
                />
              </div>

              <div className="grid grid-cols-2 gap-8">
                <div className="space-y-3">
                  <label className="text-[10px] font-black uppercase tracking-widest text-zinc-600">Zeme</label>
                  <select
                    className="w-full bg-zinc-950 border border-zinc-800 rounded-xl h-14 px-5 text-xs font-black text-white uppercase tracking-widest focus:outline-none appearance-none cursor-pointer"
                    value={formData.country}
                    onChange={e => {
                      const c = e.target.value;
                      update('country', c);
                      update('language_code', c === 'CZ' ? 'cs' : 'sk');
                    }}
                  >
                    <option value="CZ">Cesko (CZK)</option>
                    <option value="SK">Slovensko (EUR)</option>
                  </select>
                </div>
                <div className="space-y-3">
                  <label className="text-[10px] font-black uppercase tracking-widest text-zinc-600">Mesto</label>
                  <input required type="text" className="w-full bg-zinc-950 border border-zinc-800 rounded-xl h-14 px-5 text-sm font-black text-white placeholder:text-zinc-600 focus:outline-none" placeholder="napr. Praha" value={formData.city} onChange={e => update('city', e.target.value)} />
                </div>
              </div>
            </Card>
          </section>

          {/* Meal Settings */}
          <section className="space-y-8 text-left">
            <div className="flex items-center gap-4 text-white">
              <div className="w-8 h-8 rounded-lg bg-indigo-600 flex items-center justify-center font-black italic shadow-lg">2</div>
              <h2 className="text-2xl font-black uppercase tracking-tight italic leading-none">Nastaveni jidel</h2>
            </div>

            <Card className="p-8 space-y-12">
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-5">
                {[
                  { id: 'breakfast', label: 'Snidane', icon: Coffee },
                  { id: 'lunch', label: 'Obed', icon: UtensilsCrossed },
                  { id: 'dinner', label: 'Vecere', icon: Utensils },
                ].map((meal) => (
                  <button
                    key={meal.id}
                    type="button"
                    onClick={() => update(meal.id, !(formData as any)[meal.id])}
                    className={`p-6 rounded-2xl border-2 transition-all flex flex-col items-center gap-4 ${
                      (formData as any)[meal.id]
                        ? 'bg-indigo-600/10 border-indigo-600 text-white shadow-xl shadow-indigo-500/10'
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
                    <span className="text-[10px] font-black uppercase tracking-widest text-zinc-600 italic">Svacinky</span>
                    <span className="text-xl font-black text-indigo-500 italic">{formData.small_meals_per_day}/den</span>
                  </div>
                  <input type="range" min="0" max="5" className="w-full h-1.5 bg-zinc-800 rounded-full appearance-none accent-indigo-600 cursor-pointer" value={formData.small_meals_per_day} onChange={e => update('small_meals_per_day', parseInt(e.target.value))} />
                </div>
                <div className="space-y-6">
                  <div className="flex justify-between items-end">
                    <span className="text-[10px] font-black uppercase tracking-widest text-zinc-600 italic">Drobne snacky</span>
                    <span className="text-xl font-black text-indigo-500 italic">{formData.snacks_per_day}/den</span>
                  </div>
                  <input type="range" min="0" max="3" className="w-full h-1.5 bg-zinc-800 rounded-full appearance-none accent-indigo-600 cursor-pointer" value={formData.snacks_per_day} onChange={e => update('snacks_per_day', parseInt(e.target.value))} />
                </div>
              </div>

              <div className="flex flex-wrap gap-2.5 pt-8 border-t border-zinc-800">
                <span className="w-full text-[10px] font-black uppercase tracking-widest text-zinc-500 mb-2 italic">Delka planu (dny)</span>
                {[1, 3, 7, 14, 30].map(d => (
                  <button key={d} type="button" onClick={() => update('num_days', d)} className={`px-5 py-2.5 rounded-xl text-[10px] font-black uppercase tracking-widest transition-all border border-zinc-800 ${formData.num_days === d ? 'bg-indigo-600 text-white shadow-lg border-indigo-500' : 'bg-zinc-950 text-zinc-600 hover:text-zinc-400'}`}>
                    {d}D
                  </button>
                ))}
              </div>
            </Card>
          </section>

          {/* Preferred Store */}
          <section className="space-y-8 text-left">
            <div className="flex items-center gap-4 text-white">
              <div className="w-8 h-8 rounded-lg bg-indigo-600 flex items-center justify-center font-black italic shadow-lg">3</div>
              <h2 className="text-2xl font-black uppercase tracking-tight italic leading-none">Preferovany obchod</h2>
            </div>

            <Card className="p-8">
              <div className="grid sm:grid-cols-2 gap-5">
                {shopsData?.shops?.map((shop: any) => (
                  <button
                    key={shop.code} type="button" onClick={() => update('shop', shop.code)}
                    className={`p-8 rounded-2xl border-2 text-left transition-all relative overflow-hidden group ${
                      formData.shop === shop.code
                        ? 'bg-indigo-600/10 border-indigo-600 text-white shadow-xl'
                        : 'bg-zinc-950 border-transparent text-zinc-600 hover:bg-zinc-900'
                    }`}
                  >
                    <span className="font-black text-base block uppercase tracking-tight italic leading-none mb-1">{shop.name}</span>
                    <span className="text-[9px] font-black uppercase tracking-widest opacity-40 italic">Dostupne</span>
                    {formData.shop === shop.code && <div className="absolute top-8 right-8 text-indigo-500 bg-white p-1 rounded-lg"><Check size={14} strokeWidth={4} /></div>}
                  </button>
                ))}
              </div>
            </Card>
          </section>

          {error && (
            <div className="flex items-center gap-3 bg-rose-500/10 border border-rose-500/20 text-rose-400 rounded-xl p-5 text-sm font-bold">
              <AlertCircle size={18} className="shrink-0" />
              <span>{error}</span>
            </div>
          )}

          <button
            type="submit"
            disabled={mutation.isPending || !formData.prompt}
            className="w-full h-24 bg-white text-black rounded-[2rem] font-black text-2xl uppercase tracking-[0.5em] shadow-[0_30px_60px_rgba(255,255,255,0.05)] transition-all active:scale-[0.98] disabled:opacity-30 border-b-[12px] border-zinc-300 flex items-center justify-center gap-6"
          >
            {mutation.isPending ? <div className="flex items-center gap-4"><Loader2 className="animate-spin" size={32} /> Vytvari se...</div> : "Vygenerovat plan"}
          </button>
        </form>
      </div>
    </MainLayout>
  );
};
