// File: frontend/src/App.tsx
// Senior Refactor: Standardized Layout, Z-Index sanitization, and UI scaling fixes.

import { useState, useEffect, ReactNode } from 'react';
import { BrowserRouter, Routes, Route, Navigate, useNavigate, useSearchParams, useParams, Link, useLocation } from 'react-router-dom';
import { QueryClient, QueryClientProvider, useQuery, useMutation } from '@tanstack/react-query';
import { 
  Loader2, Zap, AlertCircle, Plus, Utensils, ShoppingCart, 
  Timer, Globe, MapPin, Check, Trash2, 
  LayoutDashboard, LogOut, ArrowRight, CheckCircle2,
  BrainCircuit, Search, ListChecks, Activity, ServerCrash, 
  Sparkles, Box, Coffee, UtensilsCrossed
} from 'lucide-react';
import axios from 'axios';

// --- API CONFIGURATION ---
const api = axios.create({ baseURL: '/api', withCredentials: true });

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token');
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;
    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true;
      const refreshToken = localStorage.getItem('refresh_token');
      if (refreshToken) {
        try {
          const res = await axios.post('/api/auth/refresh/', { refresh: refreshToken });
          const { access } = res.data;
          localStorage.setItem('access_token', access);
          api.defaults.headers.common['Authorization'] = `Bearer ${access}`;
          originalRequest.headers['Authorization'] = `Bearer ${access}`;
          return api(originalRequest);
        } catch (refreshError) {
          localStorage.clear();
          window.location.href = '/login';
        }
      } else {
        window.location.href = '/login';
      }
    }
    return Promise.reject(error);
  }
);

const queryClient = new QueryClient();

// --- LAYOUT COMPONENTS ---

const Navbar = () => {
  const navigate = useNavigate();
  const location = useLocation();
  
  const handleLogout = () => {
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    navigate('/login');
  };

  return (
    <nav className="h-20 border-b border-white/5 bg-[#0a0f1e]/80 backdrop-blur-2xl fixed top-0 left-0 right-0 z-[100]">
      <div className="max-w-7xl mx-auto px-6 h-full flex justify-between items-center">
        <Link to="/" className="flex items-center gap-3 group">
          <div className="w-10 h-10 rounded-2xl bg-blue-600/10 flex items-center justify-center text-blue-500 group-hover:bg-blue-600 group-hover:text-white transition-all shadow-lg border border-blue-500/20">
            <Zap size={20} fill="currentColor" />
          </div>
          <span className="text-xl font-black tracking-tighter text-white uppercase italic">
            DietPlanner<span className="text-blue-500 not-italic">.</span>
          </span>
        </Link>

        <div className="flex items-center gap-4">
          <div className="hidden sm:flex items-center gap-1 bg-black/40 p-1 rounded-2xl border border-white/5">
            <Link to="/" className={`px-5 py-2 rounded-xl text-[10px] font-black uppercase tracking-widest flex items-center gap-2 transition-all ${location.pathname === '/' ? 'bg-blue-600 text-white' : 'text-gray-500 hover:text-white'}`}>
              <LayoutDashboard size={14} /> Dashboard
            </Link>
            <Link to="/create" className={`px-5 py-2 rounded-xl text-[10px] font-black uppercase tracking-widest flex items-center gap-2 transition-all ${location.pathname === '/create' ? 'bg-blue-600 text-white' : 'text-gray-500 hover:text-white'}`}>
              <Plus size={14} /> Synthesize
            </Link>
          </div>
          <button onClick={handleLogout} className="w-10 h-10 rounded-2xl bg-white/5 flex items-center justify-center text-gray-500 hover:text-red-500 hover:bg-red-500/10 transition-all border border-white/5">
            <LogOut size={18} />
          </button>
        </div>
      </div>
    </nav>
  );
};

const MainLayout = ({ children }: { children: ReactNode }) => (
  <div className="min-h-screen bg-[#0a0f1e] pt-20">
    <Navbar />
    {children}
  </div>
);

// --- SHARED COMPONENTS ---

const StatusTracker = ({ statusData }: { statusData: any }) => {
  const currentStatus = statusData?.goal_status || 'pending';
  const steps = [
    { keys: ['pending', 'awaiting_payment'], label: 'Handshake', desc: 'Syncing roadmap node', icon: Sparkles },
    { keys: ['payment_confirmed', 'processing'], label: 'AI Synthesis', desc: 'Initializing models', icon: BrainCircuit },
    { keys: ['processing_meal_plan'], label: 'Mapping', desc: 'Generating nutrition', icon: Utensils },
    { keys: ['processing_shopping_list'], label: 'Market Logic', desc: 'Scanning inventory', icon: Search },
    { keys: ['validating'], label: 'Integrity', desc: 'Verifying logic', icon: ListChecks },
  ];
  const currentIdx = steps.findIndex(s => s.keys.includes(currentStatus));

  return (
    <div className="mt-12 w-full max-w-md mx-auto space-y-6">
      {steps.map((step, idx) => {
        const isDone = idx < currentIdx || currentStatus === 'completed';
        const isCurrent = idx === currentIdx;
        return (
          <div key={idx} className={`flex items-center gap-5 transition-all duration-700 ${isDone || isCurrent ? 'opacity-100' : 'opacity-20 translate-x-4'}`}>
            <div className={`w-10 h-10 rounded-2xl flex-none flex items-center justify-center transition-all ${isDone ? 'bg-green-500/20 text-green-500 border border-green-500/20' : isCurrent ? 'bg-blue-600 text-white shadow-2xl scale-110' : 'bg-white/5 text-gray-500 border border-white/5'}`}>
              {isDone ? <Check size={18} strokeWidth={3} /> : <step.icon size={18} />}
            </div>
            <div className="text-left">
              <p className={`text-[10px] font-black uppercase tracking-[0.2em] ${isCurrent ? 'text-blue-500' : isDone ? 'text-green-500' : 'text-gray-500'}`}>{step.label}</p>
              <p className="text-xs text-gray-500 font-medium leading-tight">{isCurrent ? step.desc : isDone ? 'Node Verified' : 'Locked'}</p>
            </div>
          </div>
        );
      })}
    </div>
  );
};

// --- SCREENS ---

const Dashboard = () => {
  const navigate = useNavigate();
  const { data: goals, isLoading } = useQuery({
    queryKey: ['goals'],
    queryFn: () => api.get('/goals/list/').then(res => res.data.data)
  });

  if (isLoading) return <LoadingScreen message="Linking Neural Nodes..." />;

  return (
    <MainLayout>
      <main className="max-w-7xl mx-auto px-6 py-16">
        <div className="flex flex-col md:flex-row md:items-end justify-between mb-16 gap-8">
          <div className="space-y-3">
            <div className="inline-flex items-center gap-2 bg-blue-600/10 text-blue-400 px-4 py-1.5 rounded-full border border-blue-500/20 shadow-inner">
              <Activity size={12} className="animate-pulse" />
              <span className="text-[10px] font-black uppercase tracking-widest">Active Core</span>
            </div>
            <h1 className="text-5xl font-black text-white tracking-tighter uppercase italic">Neural<span className="text-blue-600 not-italic"> Hub.</span></h1>
            <p className="text-gray-500 text-lg font-medium tracking-tight">Accessing personal nutrition strategies.</p>
          </div>
          <button onClick={() => navigate('/create')} className="btn-primary px-10 h-16 text-xs uppercase tracking-[0.2em] shadow-blue-500/10">
            <Plus size={20} strokeWidth={3} /> New Roadmap
          </button>
        </div>

        <div className="grid gap-8 md:grid-cols-2 lg:grid-cols-3">
          {goals?.length === 0 ? (
            <div className="col-span-full py-40 text-center glass-card rounded-[4rem] border-dashed border-white/10 group cursor-pointer hover:border-blue-500/40 transition-colors" onClick={() => navigate('/create')}>
              <Box size={60} className="mx-auto mb-6 text-gray-800 group-hover:text-blue-500/20 transition-colors" />
              <h3 className="text-2xl font-black text-white mb-3 uppercase tracking-tight">Empty Roadmap Buffer</h3>
              <p className="text-gray-500 mb-10 max-w-sm mx-auto font-medium">No synthesized strategies found. Initialize the engine to begin mapping.</p>
              <div className="inline-flex items-center gap-3 bg-white text-black px-8 py-4 rounded-2xl font-black text-[10px] uppercase tracking-widest shadow-2xl transition-transform active:scale-95">
                Init Genesis <ArrowRight size={14} />
              </div>
            </div>
          ) : (
            goals?.map((goal: any) => (
              <div key={goal.id} onClick={() => navigate(`/plan/${goal.id}`)} className="glass-card p-10 rounded-[3.5rem] cursor-pointer hover:translate-y-[-8px] hover:border-blue-500/40 transition-all group shadow-3xl">
                <div className="flex justify-between items-start mb-10">
                  <div className={`px-4 py-1.5 rounded-xl text-[9px] font-black uppercase tracking-widest border ${goal.status === 'completed' ? 'bg-green-500/10 text-green-500 border-green-500/20' : goal.status === 'failed' ? 'bg-red-500/10 text-red-500 border-red-500/20' : 'bg-blue-500/10 text-blue-500 border-blue-500/20'}`}>
                    {goal.status.replace(/_/g, ' ')}
                  </div>
                  <span className="text-[10px] font-bold text-gray-700 uppercase">{new Date(goal.created_at).toLocaleDateString()}</span>
                </div>
                <div className="space-y-3 mb-10">
                   <div className="flex items-center gap-2 text-gray-500 text-[10px] font-black uppercase tracking-widest">
                     <MapPin size={12} className="text-blue-500" /> {goal.country} Hub • {goal.city}
                   </div>
                   <h3 className="text-2xl font-black text-white leading-[1.1] uppercase tracking-tight group-hover:text-blue-400 transition-colors line-clamp-3">
                     {goal.prompt}
                   </h3>
                </div>
                <div className="flex items-center gap-6 pt-8 border-t border-white/5">
                  <div className="flex items-center gap-2 text-gray-500 font-black text-[10px] uppercase tracking-widest">
                    <Timer size={16} className="text-gray-700" /> {goal.num_days}D
                  </div>
                  <div className="flex items-center gap-2 text-gray-500 font-black text-[10px] uppercase tracking-widest">
                    <Globe size={16} className="text-gray-700" /> {goal.language_code.toUpperCase()}
                  </div>
                  <div className="ml-auto w-10 h-10 rounded-2xl bg-white/5 flex items-center justify-center group-hover:bg-blue-600 group-hover:text-white transition-all shadow-lg border border-white/5">
                    <ArrowRight size={20} />
                  </div>
                </div>
              </div>
            ))
          )}
        </div>
      </main>
    </MainLayout>
  );
};

const CreatePlanForm = () => {
  const navigate = useNavigate();
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
    goal_id: null as number | null
  });

  const { data: shopsData } = useQuery({
    queryKey: ['shops', formData.country],
    queryFn: () => api.get(`/shops/?country=${formData.country}`).then(res => res.data.data),
    enabled: !!formData.country
  });

  const mutation = useMutation({
    mutationFn: (data: any) => api.post('/goals/', data),
    onSuccess: (res) => navigate(`/plan/${res.data.data.goal_id}`)
  });

  const updateField = (field: string, value: any) => setFormData(prev => ({ ...prev, [field]: value }));

  return (
    <MainLayout>
      <div className="max-w-4xl mx-auto px-6 py-20">
        <header className="mb-16 text-center space-y-4">
          <p className="text-[10px] font-black text-blue-500 uppercase tracking-[0.8em]">Neural Input Phase</p>
          <h1 className="text-6xl font-black tracking-tighter uppercase italic">Genesis<span className="text-blue-600 not-italic">.</span></h1>
          <p className="text-gray-500 text-xl font-medium tracking-tight mx-auto max-w-xl">Configure parameters for roadmap synthesis.</p>
        </header>

        <form onSubmit={e => { e.preventDefault(); mutation.mutate(formData); }} className="space-y-10">
          <section className="glass-card p-10 rounded-[4rem] space-y-8 shadow-3xl">
            <label className="text-[11px] font-black uppercase tracking-[0.4em] text-blue-500 flex items-center gap-3">
              <BrainCircuit size={18} /> I. Core Objectives
            </label>
            <textarea 
              required 
              className="input-field min-h-[160px] text-xl font-bold leading-relaxed py-8 px-8 bg-black/40 border-none ring-1 ring-white/10 focus:ring-blue-500/50 rounded-[2.5rem]" 
              placeholder="e.g. Muscle building protocol for vegan athlete..." 
              value={formData.prompt} 
              onChange={e => updateField('prompt', e.target.value)} 
            />
            
            <div className="grid sm:grid-cols-2 gap-8">
              <div className="space-y-4">
                <label className="text-[10px] font-black uppercase tracking-widest text-gray-600">Regional Hub</label>
                <select 
                  className="input-field bg-[#0a0f1e] font-black uppercase tracking-widest text-xs h-16 rounded-2xl px-6" 
                  value={formData.country} 
                  onChange={e => {
                    const c = e.target.value;
                    updateField('country', c);
                    updateField('language_code', c === 'CZ' ? 'cs' : 'sk');
                  }}
                >
                  <option value="CZ">Czechia (CZK)</option>
                  <option value="SK">Slovakia (EUR)</option>
                </select>
              </div>
              <div className="space-y-4">
                <label className="text-[10px] font-black uppercase tracking-widest text-gray-600">Anchor City</label>
                <input 
                  required type="text" 
                  className="input-field font-bold h-16 rounded-2xl bg-black/20 px-6 text-lg" 
                  placeholder="e.g. Prague" 
                  value={formData.city} 
                  onChange={e => updateField('city', e.target.value)} 
                />
              </div>
            </div>
          </section>

          <section className="glass-card p-10 rounded-[4rem] space-y-12 shadow-3xl">
            <label className="text-[11px] font-black uppercase tracking-[0.4em] text-blue-500 flex items-center gap-3">
              <Utensils size={18} /> II. Meal Mapping
            </label>
            
            <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
              {[
                { id: 'breakfast', label: 'Sunrise', icon: Coffee },
                { id: 'lunch', label: 'Midday', icon: UtensilsCrossed },
                { id: 'dinner', label: 'Sunset', icon: Utensils }
              ].map((meal) => (
                <button
                  key={meal.id}
                  type="button"
                  onClick={() => updateField(meal.id, !(formData as any)[meal.id])}
                  className={`p-6 rounded-3xl border-2 flex items-center justify-between transition-all ${
                    (formData as any)[meal.id] 
                      ? 'bg-blue-600/10 border-blue-500 text-white shadow-lg' 
                      : 'bg-white/5 border-transparent text-gray-500 hover:bg-white/10'
                  }`}
                >
                  <div className="flex items-center gap-4">
                    <meal.icon size={20} className={(formData as any)[meal.id] ? 'text-blue-500' : 'text-gray-700'} />
                    <span className="font-black uppercase text-[10px] tracking-[0.2em]">{meal.label}</span>
                  </div>
                  {(formData as any)[meal.id] && <Check size={16} strokeWidth={4} />}
                </button>
              ))}
            </div>

            <div className="grid sm:grid-cols-2 gap-12">
              <div className="space-y-6">
                <div className="flex justify-between items-end">
                  <label className="text-[10px] font-black uppercase tracking-widest text-gray-600">Small Meals</label>
                  <span className="text-2xl font-black text-blue-500 tabular-nums">{formData.small_meals_per_day}</span>
                </div>
                <input type="range" min="0" max="5" className="w-full h-2 bg-white/5 rounded-full appearance-none accent-blue-600" value={formData.small_meals_per_day} onChange={e => updateField('small_meals_per_day', parseInt(e.target.value))} />
              </div>
              <div className="space-y-6">
                <div className="flex justify-between items-end">
                  <label className="text-[10px] font-black uppercase tracking-widest text-gray-600">Snacks</label>
                  <span className="text-2xl font-black text-blue-500 tabular-nums">{formData.snacks_per_day}</span>
                </div>
                <input type="range" min="0" max="3" className="w-full h-2 bg-white/5 rounded-full appearance-none accent-blue-600" value={formData.snacks_per_day} onChange={e => updateField('snacks_per_day', parseInt(e.target.value))} />
              </div>
            </div>

            <div className="space-y-6">
              <label className="text-[10px] font-black uppercase tracking-widest text-gray-600">Strategy Duration</label>
              <div className="flex flex-wrap gap-3">
                {[1, 3, 7, 14, 30].map(d => (
                  <button
                    key={d} type="button" onClick={() => updateField('num_days', d)}
                    className={`px-8 py-3 rounded-2xl font-black text-[10px] tracking-widest transition-all border-2 ${
                      formData.num_days === d ? 'bg-blue-600 border-blue-500 text-white shadow-xl' : 'bg-white/5 border-transparent text-gray-500 hover:bg-white/10'
                    }`}
                  >
                    {d} DAYS
                  </button>
                ))}
              </div>
            </div>
          </section>

          <section className="glass-card p-10 rounded-[4rem] space-y-8 shadow-3xl">
            <label className="text-[11px] font-black uppercase tracking-[0.4em] text-blue-500 flex items-center gap-3">
              <ShoppingCart size={18} /> III. Inventory Hub
            </label>
            <div className="grid sm:grid-cols-2 gap-5">
              {shopsData?.shops?.map((shop: any) => (
                <button 
                  key={shop.code} type="button" onClick={() => updateField('shop', shop.code)} 
                  className={`p-8 rounded-[2.5rem] border-2 text-left transition-all relative overflow-hidden group ${
                    formData.shop === shop.code 
                      ? 'bg-blue-600/10 border-blue-500 text-white shadow-2xl scale-[1.02]' 
                      : 'bg-white/5 border-transparent text-gray-500 hover:bg-white/10'
                  }`}
                >
                  <span className="font-black text-sm block mb-1 uppercase tracking-[0.2em]">{shop.name}</span>
                  <span className="text-[9px] uppercase font-bold tracking-widest opacity-40">Live Catalog Matching</span>
                  {formData.shop === shop.code && <div className="absolute top-8 right-8 bg-blue-500 text-white p-1 rounded-full"><Check size={14} strokeWidth={4} /></div>}
                </button>
              ))}
            </div>
          </section>

          <button 
            type="submit" 
            disabled={mutation.isPending || !formData.prompt} 
            className="w-full bg-white text-black py-10 rounded-[3rem] font-black text-2xl uppercase tracking-[0.5em] shadow-3xl hover:bg-gray-100 transition-all active:scale-[0.98] disabled:opacity-30 border-b-8 border-gray-300"
          >
            {mutation.isPending ? <div className="flex items-center justify-center gap-5"><Loader2 className="animate-spin w-10 h-10" /> Syncing</div> : "Synthesize Plan"}
          </button>
        </form>
      </div>
    </MainLayout>
  );
};

const PlanView = () => {
  const { id } = useParams();
  const navigate = useNavigate();
  const { data: statusData } = useQuery({
    queryKey: ['taskStatus', id],
    queryFn: () => api.get(`/goals/${id}/task-status/`).then(res => res.data.data),
    refetchInterval: (query: any) => query?.state?.data?.goal_status === 'completed' || query?.state?.data?.goal_status === 'failed' ? false : 2000
  });

  const { data: goalDetail } = useQuery({
    queryKey: ['plan', id],
    queryFn: () => api.get(`/goals/${id}/`).then(res => res.data.data),
    enabled: statusData?.goal_status === 'completed'
  });

  if (statusData?.goal_status === 'failed') {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center text-white bg-[#0a0f1e] p-12 text-center">
        <AlertCircle size={80} className="text-red-500 mb-10 animate-bounce" />
        <h1 className="text-6xl font-black tracking-tighter uppercase mb-6">Resolution Fault<span className="text-red-600">.</span></h1>
        <p className="text-gray-500 mb-12 max-w-lg text-lg font-medium tracking-tight leading-relaxed">The neural engine could not resolve the current parameters. Check objective feasibility and inventory hub status.</p>
        <button onClick={() => navigate('/')} className="btn-primary px-12 h-16 text-xs uppercase tracking-widest bg-white text-black hover:bg-gray-200 shadow-none border-b-4 border-gray-300">Reset System</button>
      </div>
    );
  }

  if (statusData?.goal_status !== 'completed') {
    return (
      <MainLayout>
        <LoadingScreen message="Resolving supply chain and nutritional models" status={statusData} />
      </MainLayout>
    );
  }

  const plan = goalDetail?.dietary_plan;
  if (!plan) return <LoadingScreen message="Finalizing Plan Data..." />;

  return (
    <MainLayout>
      <div className="max-w-7xl mx-auto px-6 py-20">
        <header className="flex flex-col lg:flex-row lg:items-end justify-between mb-24 gap-12">
          <div className="space-y-6 text-left">
            <h1 className="text-8xl font-black tracking-tighter uppercase leading-none italic">Outcome<span className="text-blue-600 not-italic">.</span></h1>
            <div className="flex flex-wrap gap-4">
               {[{ icon: MapPin, text: goalDetail.city }, { icon: Timer, text: `${goalDetail.num_days} Days` }, { icon: ShoppingCart, text: goalDetail.shop }].map((meta, i) => (
                 <div key={i} className="flex items-center gap-3 bg-white/5 px-5 py-3 rounded-2xl border border-white/5 text-[10px] font-black uppercase tracking-widest text-gray-500">
                    <meta.icon size={14} className="text-blue-500" /> {meta.text}
                 </div>
               ))}
            </div>
          </div>
          <div className="flex items-center gap-6 bg-white/5 p-8 rounded-[3.5rem] border border-white/5 shadow-2xl group pr-16">
             <div className="w-16 h-16 bg-green-500/10 border border-green-500/20 rounded-2xl flex items-center justify-center text-green-500 shadow-lg group-hover:scale-110 transition-transform">
               <CheckCircle2 size={36} strokeWidth={2.5} />
             </div>
             <div className="text-left space-y-1">
               <p className="text-[10px] font-black text-gray-600 uppercase tracking-widest">Plan Verified</p>
               <p className="font-black text-2xl text-green-500 tracking-tighter uppercase leading-none">Map Active</p>
             </div>
          </div>
        </header>

        <div className="grid lg:grid-cols-3 gap-20">
          <div className="lg:col-span-2 space-y-28">
            {plan.days?.map((day: any) => (
              <section key={day.day_number} className="relative">
                <div className="absolute -left-12 top-10 bottom-0 w-px bg-gradient-to-b from-blue-600/40 via-transparent to-transparent hidden xl:block" />
                <div className="flex items-center gap-8 mb-16">
                  <div className="w-16 h-16 rounded-2xl bg-white text-black flex items-center justify-center text-3xl font-black shadow-2xl italic">{day.day_number}</div>
                  <div className="text-left">
                    <h2 className="text-4xl font-black tracking-tighter uppercase leading-none mb-1">Genesis Node.</h2>
                    <p className="text-gray-500 font-black uppercase tracking-[0.4em] text-[10px]">Strategic Allocation</p>
                  </div>
                </div>
                <div className="grid gap-10">
                  {['breakfast', 'lunch', 'dinner'].map(mealKey => day[mealKey] && (
                    <div key={mealKey} className="glass-card p-12 rounded-[4.5rem] group hover:border-blue-500/30 transition-all border border-white/5 shadow-3xl text-left">
                      <div className="flex justify-between items-center mb-10">
                        <span className="px-6 py-2 rounded-xl bg-blue-600 text-white text-[10px] font-black uppercase tracking-widest shadow-xl italic">{mealKey}</span>
                        <div className="flex items-center gap-2 text-gray-600 text-[10px] font-black uppercase tracking-widest">
                           <Timer size={16} className="text-blue-500" /> {day[mealKey].preparation_time || 15}M execution
                        </div>
                      </div>
                      <h3 className="text-4xl font-black mb-6 group-hover:text-blue-400 transition-colors tracking-tight uppercase leading-[1.05]">{day[mealKey].name}</h3>
                      <p className="text-gray-400 text-xl font-medium tracking-tight leading-relaxed mb-12">{day[mealKey].description}</p>
                      
                      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
                         {Object.entries(day[mealKey].nutritional_info || {}).map(([k, v]: any) => (
                           <div key={k} className="bg-[#0a0f1e] px-6 py-5 rounded-3xl border border-white/5 shadow-inner group-hover:border-blue-500/10 transition-colors">
                             <p className="text-[9px] text-gray-600 font-black uppercase tracking-widest mb-1">{k}</p>
                             <p className="font-black text-lg text-white tracking-tighter uppercase leading-none italic">{v}</p>
                           </div>
                         ))}
                      </div>
                    </div>
                  ))}
                </div>
              </section>
            ))}
          </div>

          <aside className="relative">
            <div className="glass-card p-12 rounded-[4rem] sticky top-32 border border-blue-500/10 shadow-3xl text-left">
               <div className="flex items-center gap-6 mb-12 pb-12 border-b border-white/5">
                 <div className="w-14 h-14 rounded-2xl bg-blue-600/10 flex items-center justify-center text-blue-500 shadow-inner border border-blue-500/10"><ShoppingCart size={28} strokeWidth={2.5} /></div>
                 <div>
                    <h2 className="text-4xl font-black tracking-tighter uppercase leading-none italic">Supply.</h2>
                    <p className="text-[10px] font-black text-gray-600 uppercase tracking-widest">Live Procurement</p>
                 </div>
               </div>

               <div className="space-y-8 max-h-[450px] overflow-y-auto pr-4 custom-scrollbar mb-12">
                  {plan.shopping_list?.map((item: any, idx: number) => (
                    <div key={idx} className="group border-b border-white/5 pb-8 last:border-0 last:pb-0">
                      <div className="flex justify-between items-start mb-3">
                        <p className="font-black text-lg text-white group-hover:text-blue-400 transition-colors uppercase tracking-tight leading-none italic">{item.ingredient}</p>
                        <p className="text-base font-black text-blue-500 tabular-nums leading-none">{item.price} {item.currency}</p>
                      </div>
                      <div className="flex justify-between items-center text-[10px] font-black text-gray-600 uppercase tracking-widest">
                        <span className="bg-white/5 px-3 py-1 rounded-lg text-gray-400">{item.quantity} {item.unit}</span>
                        <span className="italic opacity-30 line-clamp-1 max-w-[140px] text-right">{item.matched_product_name}</span>
                      </div>
                    </div>
                  ))}
               </div>

               <div className="pt-10 border-t-4 border-blue-600/30 space-y-10">
                  <div className="flex justify-between items-center text-gray-600 uppercase tracking-widest text-[10px] font-black">
                     <span>Estimated Budget</span>
                     <span className="bg-blue-600/10 px-4 py-2 rounded-xl text-blue-500 border border-blue-500/20">{plan.shopping_list?.length} Nodes</span>
                  </div>
                  <div className="flex justify-between items-end">
                    <span className="text-8xl font-black tracking-tighter leading-none text-white italic">{plan.total_price}</span>
                    <span className="text-3xl font-black text-blue-500 tracking-tighter ml-2 mb-2 uppercase">{plan.currency}</span>
                  </div>
                  <button className="w-full bg-white text-black py-8 rounded-[2.5rem] font-black uppercase tracking-[0.4em] text-xs hover:bg-gray-200 transition-all flex items-center justify-center gap-5 shadow-2xl active:scale-[0.98] border-b-8 border-gray-300">
                    Sync via Retailer <ArrowRight size={20} strokeWidth={3} />
                  </button>
               </div>
            </div>
          </aside>
        </div>
      </div>
    </MainLayout>
  );
};

// --- AUTH & MISC ---

const LoginView = () => (
  <div className="min-h-screen flex items-center justify-center p-8 bg-[#0a0f1e] relative overflow-hidden">
    <div className="absolute top-0 left-0 w-full h-full pointer-events-none opacity-40">
      <div className="absolute top-[-10%] left-[-10%] w-[800px] h-[800px] bg-blue-600/10 blur-[180px] rounded-full animate-pulse" />
      <div className="absolute bottom-[-10%] right-[-10%] w-[900px] h-[900px] bg-purple-600/5 blur-[200px] rounded-full animate-pulse" />
    </div>
    <div className="max-w-md w-full glass-card rounded-[5rem] p-16 text-center relative z-10 shadow-3xl border border-white/5">
      <div className="inline-flex items-center justify-center w-28 h-28 rounded-[3rem] bg-blue-600/10 text-blue-500 mb-16 shadow-inner border border-white/5 relative group">
        <div className="absolute inset-0 bg-blue-500/20 blur-3xl animate-pulse rounded-full" />
        <Zap size={56} fill="currentColor" className="relative z-10 animate-pulse group-hover:scale-110 transition-transform" />
      </div>
      <div className="mb-20">
        <h1 className="text-6xl font-black text-white mb-6 tracking-tighter leading-[0.75] uppercase italic">Diet<br/>Planner<span className="text-blue-600 not-italic">.</span></h1>
        <p className="text-gray-500 text-[10px] font-black tracking-[0.6em] uppercase opacity-60">Neural Nutrition Interface</p>
      </div>
      <button onClick={() => window.location.href = '/api/auth/google/login/'} className="w-full bg-white hover:bg-gray-100 text-black h-20 rounded-3xl font-black transition-all flex items-center justify-center gap-6 text-xs uppercase tracking-[0.3em] shadow-3xl border-b-4 border-gray-300 active:scale-95">
        <svg className="w-7 h-7" viewBox="0 0 24 24"><path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/><path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/><path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l3.66-2.84z"/><path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 12-4.53z"/></svg>
        Sync Profile
      </button>
    </div>
  </div>
);

const LoadingScreen = ({ message, status }: { message: string, status?: any }) => (
  <div className="flex-1 flex flex-col items-center justify-center text-white p-12 text-center relative overflow-hidden min-h-[70vh]">
    <div className="relative mb-24 scale-125">
      <div className="absolute inset-0 bg-blue-600/30 blur-[80px] animate-pulse rounded-full" />
      <Loader2 className="animate-spin text-blue-500 relative z-10" size={100} strokeWidth={1} />
      <Zap size={40} className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 text-blue-400 animate-pulse z-10" />
    </div>
    <div className="space-y-4 relative z-10">
      <h2 className="text-white font-black text-6xl tracking-tighter uppercase italic leading-none">Synthesizing<span className="text-blue-600 animate-pulse not-italic">...</span></h2>
      <p className="text-gray-500 font-black uppercase tracking-[0.6em] text-[10px] opacity-60 italic">{message}</p>
    </div>
    {status && <StatusTracker statusData={status} />}
  </div>
);

const LoginSuccess = () => {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  useEffect(() => {
    const access = params.get('access');
    const refresh = params.get('refresh');
    if (access && refresh) {
      localStorage.setItem('access_token', access);
      localStorage.setItem('refresh_token', refresh);
      navigate('/', { replace: true });
    } else {
      navigate('/login?error=sync_fault');
    }
  }, [params, navigate]);
  return <LoadingScreen message="Establishing Encrypted Protocol..." />;
};

const ProtectedRoute = ({ children }: { children: any }) => {
  if (!localStorage.getItem('access_token')) return <Navigate to="/login" replace />;
  return children;
};

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<LoginView />} />
          <Route path="/login-success" element={<LoginSuccess />} />
          <Route path="/" element={<ProtectedRoute><Dashboard /></ProtectedRoute>} />
          <Route path="/create" element={<ProtectedRoute><CreatePlanForm /></ProtectedRoute>} />
          <Route path="/plan/:id" element={<ProtectedRoute><PlanView /></ProtectedRoute>} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}