// File: frontend/src/App.tsx
// Senior Refactor: Standardized Layout Shell, Stacking Context Fix, and SaaS Design Tokens.
// Phase 5 Fix: Resolved TypeScript prop-type errors, removed duplicate declarations, and polished layout stability.

import { useState, useEffect, ReactNode, HTMLAttributes } from 'react';
import { BrowserRouter, Routes, Route, Navigate, useNavigate, useSearchParams, useParams, Link, useLocation } from 'react-router-dom';
import { QueryClient, QueryClientProvider, useQuery, useMutation } from '@tanstack/react-query';
import { 
  Loader2, Zap, AlertCircle, Plus, Utensils, ShoppingCart, 
  Timer, Globe, MapPin, Check, Trash2, 
  LayoutDashboard, LogOut, ArrowRight, CheckCircle2,
  BrainCircuit, Search, ListChecks, Activity, ServerCrash, 
  Sparkles, Box, Coffee, UtensilsCrossed, Settings, ChevronRight
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

// --- SHARED UI PRIMITIVES ---

const Navbar = () => {
  const navigate = useNavigate();
  const location = useLocation();
  
  const handleLogout = () => {
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    navigate('/login');
  };

  return (
    <header className="h-16 border-b border-white/[0.06] bg-[#0a0f1e]/80 backdrop-blur-xl fixed top-0 left-0 right-0 z-50">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 h-full flex justify-between items-center">
        <Link to="/" className="flex items-center gap-2 group">
          <div className="w-8 h-8 rounded-lg bg-blue-600 flex items-center justify-center text-white shadow-[0_0_15px_rgba(37,99,235,0.4)]">
            <Zap size={18} fill="currentColor" />
          </div>
          <span className="text-lg font-bold tracking-tight text-white uppercase italic">
            DietPlanner<span className="text-blue-500 not-italic">AI</span>
          </span>
        </Link>

        <div className="flex items-center gap-3">
          <nav className="hidden md:flex items-center gap-1 bg-white/[0.03] p-1 rounded-xl border border-white/[0.05]">
            <Link to="/" className={`px-4 py-1.5 rounded-lg text-[11px] font-semibold uppercase tracking-wider flex items-center gap-2 transition-all ${location.pathname === '/' ? 'bg-blue-600 text-white shadow-lg' : 'text-slate-400 hover:text-white hover:bg-white/[0.05]'}`}>
              <LayoutDashboard size={14} /> Dash
            </Link>
            <Link to="/create" className={`px-4 py-1.5 rounded-lg text-[11px] font-semibold uppercase tracking-wider flex items-center gap-2 transition-all ${location.pathname === '/create' ? 'bg-blue-600 text-white shadow-lg' : 'text-slate-400 hover:text-white hover:bg-white/[0.05]'}`}>
              <Plus size={14} /> New Plan
            </Link>
          </nav>
          <div className="h-6 w-px bg-white/[0.08] mx-1 hidden md:block" />
          <button onClick={handleLogout} className="w-9 h-9 rounded-lg bg-white/[0.03] flex items-center justify-center text-slate-400 hover:text-red-400 hover:bg-red-400/10 transition-all border border-white/[0.05]">
            <LogOut size={16} />
          </button>
        </div>
      </div>
    </header>
  );
};

const MainLayout = ({ children }: { children: ReactNode }) => (
  <div className="min-h-screen bg-[#0a0f1e] text-slate-200 selection:bg-blue-500/30 flex flex-col">
    <Navbar />
    {/* pt-20 provides exact clearance for the fixed header + extra spacing to ensure top cards are fully visible. */}
    <main className="pt-20 flex-1 flex flex-col relative z-0">
      {children}
    </main>
  </div>
);

interface GlassCardProps extends HTMLAttributes<HTMLDivElement> {
  children: ReactNode;
  className?: string;
}

const GlassCard = ({ children, className = "", ...props }: GlassCardProps) => (
  <div 
    className={`bg-white/[0.02] border border-white/[0.06] backdrop-blur-sm rounded-3xl shadow-xl ${className}`}
    {...props}
  >
    {children}
  </div>
);

const Badge = ({ children, variant = 'default' }: { children: ReactNode, variant?: 'default' | 'success' | 'warning' | 'error' }) => {
  const styles = {
    default: 'bg-blue-500/10 text-blue-400 border-blue-500/20',
    success: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
    warning: 'bg-amber-500/10 text-amber-400 border-amber-500/20',
    error: 'bg-red-500/10 text-red-400 border-red-500/20'
  };
  return (
    <span className={`px-2.5 py-1 rounded-md text-[10px] font-bold uppercase tracking-widest border ${styles[variant]}`}>
      {children}
    </span>
  );
};

const StatusTracker = ({ statusData }: { statusData: any }) => {
  const currentStatus = statusData?.goal_status || 'pending';
  const steps = [
    { label: 'Initialising', keys: ['pending', 'awaiting_payment'] },
    { label: 'AI Synthesis', keys: ['payment_confirmed', 'processing', 'processing_meal_plan'] },
    { label: 'Market Sync', keys: ['processing_shopping_list'] },
    { label: 'Integrity Check', keys: ['validating'] },
    { label: 'Map Active', keys: ['completed'] }
  ];
  const activeStepIdx = steps.findIndex(s => s.keys.includes(currentStatus));

  return (
    <div className="space-y-4 text-left">
      {steps.map((step, idx) => (
        <div key={idx} className={`flex items-center gap-3 transition-opacity duration-500 ${idx <= activeStepIdx ? 'opacity-100' : 'opacity-20'}`}>
          <div className={`w-2 h-2 rounded-full ${idx < activeStepIdx ? 'bg-emerald-500' : idx === activeStepIdx ? 'bg-blue-500 animate-pulse' : 'bg-slate-700'}`} />
          <span className={`text-[10px] font-bold uppercase tracking-widest ${idx === activeStepIdx ? 'text-blue-400' : 'text-slate-500'}`}>{step.label}</span>
        </div>
      ))}
    </div>
  );
};

const LoadingScreen = ({ message, status }: { message: string, status?: any }) => (
  <div className="flex-1 flex flex-col items-center justify-center p-12 text-center bg-[#0a0f1e] relative overflow-hidden">
    <div className="relative mb-16 flex items-center justify-center">
      <div className="absolute inset-0 bg-blue-600/20 blur-[100px] animate-pulse rounded-full" />
      <Loader2 className="animate-spin text-blue-500 relative z-10" size={80} strokeWidth={1} />
      <Zap size={32} className="absolute text-blue-400 animate-pulse z-10" />
    </div>
    <div className="space-y-2 relative z-10">
      <h2 className="text-3xl font-black text-white tracking-tighter uppercase italic leading-none">Synthesizing<span className="text-blue-600 animate-pulse">...</span></h2>
      <p className="text-slate-600 text-[10px] font-bold uppercase tracking-[0.3em] max-w-sm mx-auto leading-relaxed">{message}</p>
    </div>
    {status && <div className="mt-12 w-full max-w-xs mx-auto"><StatusTracker statusData={status} /></div>}
  </div>
);

// --- FEATURE COMPONENTS ---

const Dashboard = () => {
  const navigate = useNavigate();
  const { data: goals, isLoading } = useQuery({
    queryKey: ['goals'],
    queryFn: () => api.get('/goals/list/').then(res => res.data.data)
  });

  if (isLoading) return <LoadingScreen message="Accessing encrypted roadmap buffer..." />;

  return (
    <MainLayout>
      <div className="max-w-7xl mx-auto px-4 sm:px-6 py-6 w-full">
        <header className="flex flex-col md:flex-row md:items-center justify-between gap-6 mb-10">
          <div className="space-y-1 text-left">
            <h1 className="text-3xl font-bold tracking-tight text-white uppercase italic">Neural Hub<span className="text-blue-500 not-italic">.</span></h1>
            <p className="text-slate-500 text-sm">Monitor and manage your synthesized nutritional strategies.</p>
          </div>
          <button onClick={() => navigate('/create')} className="bg-blue-600 hover:bg-blue-500 text-white px-6 h-12 rounded-xl font-bold text-sm transition-all shadow-[0_10px_20px_-5px_rgba(37,99,235,0.4)] flex items-center gap-2 active:scale-95">
            <Plus size={18} /> New Roadmap
          </button>
        </header>

        <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
          {goals?.length === 0 ? (
            <div className="col-span-full py-20 flex flex-col items-center justify-center border-2 border-dashed border-white/[0.05] rounded-[2rem] bg-white/[0.01]">
              <Box size={40} className="text-slate-700 mb-4" />
              <p className="text-slate-500 font-medium mb-6 uppercase tracking-widest text-[11px]">No roadmaps generated</p>
              <button onClick={() => navigate('/create')} className="text-blue-500 font-bold hover:underline">Begin Genesis Phase →</button>
            </div>
          ) : (
            goals?.map((goal: any) => (
              <GlassCard 
                key={goal.id} 
                className="p-6 hover:border-blue-500/30 transition-all cursor-pointer group text-left" 
                onClick={() => navigate(`/plan/${goal.id}`)}
              >
                <div className="flex justify-between items-start mb-6">
                  <Badge variant={goal.status === 'completed' ? 'success' : goal.status === 'failed' ? 'error' : 'default'}>
                    {goal.status.replace(/_/g, ' ')}
                  </Badge>
                  <span className="text-[10px] font-medium text-slate-500 uppercase">{new Date(goal.created_at).toLocaleDateString()}</span>
                </div>
                <h3 className="text-lg font-bold text-white mb-4 line-clamp-2 leading-tight group-hover:text-blue-400 transition-colors uppercase tracking-tight italic">
                  {goal.prompt}
                </h3>
                <div className="flex items-center gap-4 text-slate-500 text-[10px] font-bold uppercase tracking-wider mb-6">
                  <span className="flex items-center gap-1.5"><MapPin size={12} className="text-blue-500" /> {goal.city}</span>
                  <span className="flex items-center gap-1.5"><Timer size={12} className="text-blue-500" /> {goal.num_days}D</span>
                </div>
                <div className="pt-4 border-t border-white/[0.05] flex justify-between items-center group-hover:translate-x-1 transition-transform">
                  <span className="text-[9px] font-black text-slate-600 uppercase tracking-[0.2em]">View Analysis</span>
                  <ArrowRight size={14} className="text-slate-600 group-hover:text-blue-500" />
                </div>
              </GlassCard>
            ))
          )}
        </div>
      </div>
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
      <div className="max-w-4xl mx-auto px-4 sm:px-6 py-4 w-full">
        <header className="mb-8 text-center">
          <p className="text-[10px] font-black text-blue-500 uppercase tracking-[0.6em] mb-2">Protocol Initialisation</p>
          <h1 className="text-4xl font-black text-white tracking-tighter uppercase italic leading-none">Genesis Phase<span className="text-blue-500 not-italic">.</span></h1>
        </header>

        <form onSubmit={e => { e.preventDefault(); mutation.mutate(formData); }} className="space-y-6">
          <GlassCard className="p-6 sm:p-8 space-y-6 text-left">
            <div className="space-y-3">
              <label className="text-[11px] font-bold uppercase tracking-widest text-slate-500 flex items-center gap-2">
                <BrainCircuit size={16} className="text-blue-500" /> Core Objectives
              </label>
              <textarea 
                required 
                className="w-full bg-black/40 border border-white/[0.08] rounded-2xl p-5 text-base font-medium text-white placeholder:text-slate-600 focus:outline-none focus:ring-2 focus:ring-blue-600/50 focus:border-blue-600/50 transition-all min-h-[140px] leading-relaxed"
                placeholder="Target: Hypertrophy macro-cycle. Constraint: High protein, gluten-free, local ingredients..." 
                value={formData.prompt} 
                onChange={e => updateField('prompt', e.target.value)} 
              />
            </div>
            
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <label className="text-[10px] font-bold uppercase tracking-widest text-slate-600">Regional Hub</label>
                <select 
                  className="w-full bg-white/[0.03] border border-white/[0.08] rounded-xl h-12 px-4 text-xs font-bold text-white uppercase tracking-wider focus:outline-none" 
                  value={formData.country} 
                  onChange={e => {
                    const c = e.target.value;
                    updateField('country', c);
                    updateField('language_code', c === 'CZ' ? 'cs' : 'sk');
                  }}
                >
                  <option value="CZ">Czech Republic Hub</option>
                  <option value="SK">Slovakia Hub</option>
                </select>
              </div>
              <div className="space-y-2">
                <label className="text-[10px] font-bold uppercase tracking-widest text-slate-600">Target City</label>
                <input required type="text" className="w-full bg-white/[0.03] border border-white/[0.08] rounded-xl h-12 px-4 text-sm font-bold text-white placeholder:text-slate-700 focus:outline-none" placeholder="e.g. Prague" value={formData.city} onChange={e => updateField('city', e.target.value)} />
              </div>
            </div>
          </GlassCard>

          <GlassCard className="p-6 sm:p-8 space-y-8 text-left">
            <div className="flex items-center justify-between border-b border-white/[0.05] pb-4">
              <label className="text-[11px] font-bold uppercase tracking-widest text-slate-500 flex items-center gap-2">
                <Utensils size={16} className="text-blue-500" /> Roadmap Logic
              </label>
              <div className="flex gap-1">
                {[1, 3, 7, 14].map(d => (
                  <button key={d} type="button" onClick={() => updateField('num_days', d)} className={`px-3 py-1 rounded-md text-[9px] font-black uppercase transition-all ${formData.num_days === d ? 'bg-blue-600 text-white shadow-lg' : 'bg-white/[0.05] text-slate-500 hover:text-slate-300'}`}>
                    {d}D
                  </button>
                ))}
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {[
                { id: 'breakfast', label: 'Sunrise', icon: Coffee },
                { id: 'lunch', label: 'Midday', icon: UtensilsCrossed },
                { id: 'dinner', label: 'Sunset', icon: Utensils }
              ].map((meal) => (
                <button
                  key={meal.id}
                  type="button"
                  onClick={() => updateField(meal.id, !(formData as any)[meal.id])}
                  className={`p-4 rounded-xl border-2 transition-all flex items-center gap-3 ${
                    (formData as any)[meal.id] 
                      ? 'bg-blue-600/10 border-blue-600 text-white shadow-lg shadow-blue-500/10' 
                      : 'bg-white/[0.02] border-transparent text-slate-500 grayscale'
                  }`}
                >
                  <meal.icon size={18} />
                  <span className="font-bold uppercase text-[10px] tracking-widest">{meal.label}</span>
                </button>
              ))}
            </div>

            <div className="grid sm:grid-cols-2 gap-8">
              <div className="space-y-4">
                <div className="flex justify-between">
                  <span className="text-[10px] font-bold uppercase text-slate-600">Small Meals</span>
                  <span className="text-xs font-black text-blue-500">{formData.small_meals_per_day} units</span>
                </div>
                <input type="range" min="0" max="5" className="w-full h-1.5 bg-white/[0.05] rounded-full appearance-none accent-blue-600" value={formData.small_meals_per_day} onChange={e => updateField('small_meals_per_day', parseInt(e.target.value))} />
              </div>
              <div className="space-y-4">
                <div className="flex justify-between">
                  <span className="text-[10px] font-bold uppercase text-slate-600">Auxiliary Snacks</span>
                  <span className="text-xs font-black text-blue-500">{formData.snacks_per_day} units</span>
                </div>
                <input type="range" min="0" max="3" className="w-full h-1.5 bg-white/[0.05] rounded-full appearance-none accent-blue-600" value={formData.snacks_per_day} onChange={e => updateField('snacks_per_day', parseInt(e.target.value))} />
              </div>
            </div>
          </GlassCard>

          <GlassCard className="p-6 sm:p-8 space-y-5 text-left">
            <label className="text-[11px] font-bold uppercase tracking-widest text-slate-500 flex items-center gap-2">
              <ShoppingCart size={16} className="text-blue-500" /> Catalog Mapping
            </label>
            <div className="grid sm:grid-cols-2 gap-4">
              {shopsData?.shops?.map((shop: any) => (
                <button 
                  key={shop.code} type="button" onClick={() => updateField('shop', shop.code)} 
                  className={`p-5 rounded-2xl border-2 text-left transition-all relative ${
                    formData.shop === shop.code 
                      ? 'bg-blue-600/10 border-blue-600 text-white shadow-xl' 
                      : 'bg-white/[0.02] border-transparent text-slate-600'
                  }`}
                >
                  <span className="font-bold text-sm block uppercase tracking-tight leading-none mb-1">{shop.name}</span>
                  <span className="text-[8px] font-black uppercase opacity-40">Live Inventory Match</span>
                  {formData.shop === shop.code && <Check size={14} className="absolute top-5 right-5 text-blue-500" />}
                </button>
              ))}
            </div>
          </GlassCard>

          <button 
            type="submit" 
            disabled={mutation.isPending || !formData.prompt} 
            className="w-full bg-white text-black h-16 rounded-2xl font-black text-lg uppercase tracking-[0.4em] shadow-2xl transition-all active:scale-[0.98] disabled:opacity-30 border-b-4 border-slate-300"
          >
            {mutation.isPending ? "Synthesizing Node..." : "Initiate Mapping"}
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
    refetchInterval: (query: any) => query?.state?.data?.goal_status === 'completed' || query?.state?.data?.goal_status === 'failed' ? false : 2500
  });

  const { data: goalDetail } = useQuery({
    queryKey: ['plan', id],
    queryFn: () => api.get(`/goals/${id}/`).then(res => res.data.data),
    enabled: statusData?.goal_status === 'completed'
  });

  if (statusData?.goal_status === 'failed') {
    return (
      <div className="flex-1 flex flex-col items-center justify-center p-12 text-center bg-[#0a0f1e] text-white">
        <AlertCircle size={64} className="text-red-500 mb-6" />
        <h1 className="text-4xl font-black tracking-tighter uppercase mb-4 italic">Analysis Failed<span className="text-red-500 not-italic">.</span></h1>
        <p className="text-slate-500 max-w-md mb-10 font-medium">Neural engine could not resolve roadmap for the specified city inventory.</p>
        <button onClick={() => navigate('/')} className="px-8 h-12 bg-white text-black font-black uppercase text-xs tracking-widest rounded-xl shadow-xl">Return to Hub</button>
      </div>
    );
  }

  if (statusData?.goal_status !== 'completed') {
    return (
      <MainLayout>
        <LoadingScreen message="Cross-referencing live market data with metabolic requirements..." status={statusData} />
      </MainLayout>
    );
  }

  const plan = goalDetail?.dietary_plan;
  if (!plan) return <LoadingScreen message="Formatting output stream..." />;

  return (
    <MainLayout>
      <div className="max-w-7xl mx-auto px-4 sm:px-6 py-10 w-full">
        <header className="mb-16 flex flex-col md:flex-row md:items-end justify-between gap-8">
          <div className="space-y-4 text-left">
            <Badge variant="success">Protocol Verified</Badge>
            <h1 className="text-6xl font-black text-white tracking-tighter uppercase italic leading-none">Outcome<span className="text-blue-600 not-italic">.</span></h1>
            <div className="flex gap-3 text-left">
              <span className="flex items-center gap-1.5 bg-white/[0.03] px-3 py-1.5 rounded-lg text-[10px] font-bold text-slate-500 uppercase tracking-widest"><MapPin size={12} /> {goalDetail.city}</span>
              <span className="flex items-center gap-1.5 bg-white/[0.03] px-3 py-1.5 rounded-lg text-[10px] font-bold text-slate-500 uppercase tracking-widest"><Timer size={12} /> {goalDetail.num_days}D Cycle</span>
            </div>
          </div>
          <button className="flex items-center gap-3 bg-white text-black px-6 h-14 rounded-2xl font-black uppercase text-xs tracking-[0.2em] shadow-2xl active:scale-95 border-b-4 border-slate-300">
            Download PDF <ArrowRight size={16} />
          </button>
        </header>

        <div className="grid lg:grid-cols-12 gap-12 items-start">
          <div className="lg:col-span-8 space-y-16">
            {plan.days?.map((day: any) => (
              <div key={day.day_number} className="relative">
                <div className="absolute -left-6 top-0 bottom-0 w-px bg-white/[0.05] hidden xl:block" />
                <div className="flex items-center gap-4 mb-8">
                  <div className="w-10 h-10 rounded-xl bg-white text-black flex items-center justify-center font-black italic shadow-lg">{day.day_number}</div>
                  <h2 className="text-2xl font-black uppercase tracking-tight text-left">Cycle Phase</h2>
                </div>
                
                <div className="grid gap-6">
                  {['breakfast', 'lunch', 'dinner'].map(m => day[m] && (
                    <GlassCard key={m} className="p-8 group hover:bg-white/[0.03] transition-all text-left">
                      <div className="flex justify-between items-start mb-6">
                        <span className="text-[10px] font-black text-blue-500 uppercase tracking-[0.3em] italic">{m} Protocol</span>
                        <div className="flex items-center gap-1 text-slate-600 text-[9px] font-bold uppercase tracking-widest">
                          <Timer size={12} /> {day[m].preparation_time || 20}M
                        </div>
                      </div>
                      <h3 className="text-2xl font-bold text-white mb-3 tracking-tight leading-tight uppercase italic">{day[m].name}</h3>
                      <p className="text-slate-500 text-sm leading-relaxed mb-8 max-w-2xl">{day[m].description}</p>
                      
                      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 pt-6 border-t border-white/[0.05]">
                        {Object.entries(day[m].nutritional_info || {}).map(([k, v]: any) => (
                          <div key={k} className="space-y-0.5">
                            <p className="text-[8px] font-black text-slate-600 uppercase tracking-widest">{k}</p>
                            <p className="text-sm font-black text-slate-300 italic">{v}</p>
                          </div>
                        ))}
                      </div>
                    </GlassCard>
                  ))}
                </div>
              </div>
            ))}
          </div>

          <aside className="lg:col-span-4 lg:sticky lg:top-24">
            <GlassCard className="p-8 space-y-10 border-blue-500/20 text-left">
              <div className="flex items-center gap-3">
                <ShoppingCart size={24} className="text-blue-500" />
                <div>
                  <h2 className="text-xl font-black uppercase tracking-tighter italic leading-none mb-1 text-white">Market List</h2>
                  <p className="text-[9px] font-bold text-slate-600 uppercase tracking-widest">Live Procurement Inventory</p>
                </div>
              </div>

              <div className="space-y-5 max-h-[400px] overflow-y-auto pr-3 custom-scrollbar">
                {plan.shopping_list?.map((item: any, idx: number) => (
                  <div key={idx} className="flex justify-between items-center group">
                    <div className="space-y-0.5">
                      <p className="text-xs font-bold text-white uppercase tracking-tight italic leading-none">{item.ingredient}</p>
                      <p className="text-[9px] font-medium text-slate-600 uppercase">{item.quantity} {item.unit}</p>
                    </div>
                    <div className="text-right">
                      <p className="text-xs font-black text-blue-500 tabular-nums leading-none mb-0.5">{item.price} {item.currency}</p>
                      <p className="text-[8px] font-bold text-slate-700 italic max-w-[80px] truncate">{item.matched_product_name}</p>
                    </div>
                  </div>
                ))}
              </div>

              <div className="pt-8 border-t-2 border-white/[0.05] space-y-6">
                <div className="flex justify-between items-end">
                  <div className="space-y-1">
                    <p className="text-[9px] font-black text-slate-600 uppercase tracking-[0.2em]">Estimated Overhead</p>
                    <p className="text-3xl font-black text-white italic leading-none">{plan.total_price} <span className="text-blue-500 text-sm not-italic uppercase ml-1">{plan.currency}</span></p>
                  </div>
                </div>
                <button className="w-full bg-blue-600 hover:bg-blue-500 text-white h-14 rounded-xl font-black uppercase text-[10px] tracking-[0.2em] shadow-xl active:scale-95 transition-all">
                  Procure via {goalDetail.shop}
                </button>
              </div>
            </GlassCard>
          </aside>
        </div>
      </div>
    </MainLayout>
  );
};

// --- AUTH & SYSTEM ---

const LoginView = () => (
  <div className="min-h-screen flex items-center justify-center p-6 bg-[#0a0f1e] relative overflow-hidden">
    <div className="absolute top-0 left-0 w-full h-full pointer-events-none opacity-40">
      <div className="absolute top-[-20%] left-[-20%] w-[1000px] h-[1000px] bg-blue-600/[0.08] blur-[180px] rounded-full" />
      <div className="absolute bottom-[-20%] right-[-20%] w-[1100px] h-[1100px] bg-purple-600/[0.04] blur-[220px] rounded-full" />
    </div>
    <GlassCard className="max-w-md w-full p-12 text-center relative z-10 shadow-[0_40px_100px_-20px_rgba(0,0,0,0.5)] border-white/[0.04]">
      <div className="inline-flex items-center justify-center w-24 h-24 rounded-3xl bg-blue-600/10 text-blue-500 mb-12 shadow-inner border border-blue-500/10 relative group">
        <div className="absolute inset-0 bg-blue-500/10 blur-3xl rounded-full group-hover:bg-blue-500/20 transition-all" />
        <Zap size={48} fill="currentColor" className="relative z-10 animate-pulse" />
      </div>
      <div className="mb-16 space-y-2">
        <h1 className="text-5xl font-black text-white tracking-tighter leading-[0.8] uppercase italic">Diet<br/><span className="text-blue-600 not-italic">Planner</span></h1>
        <p className="text-slate-600 text-[10px] font-black tracking-[0.4em] uppercase pt-4">Neural Nutrition Protocol</p>
      </div>
      <button onClick={() => window.location.href = '/api/auth/google/login/'} className="w-full bg-white hover:bg-slate-100 text-black h-16 rounded-2xl font-black transition-all flex items-center justify-center gap-4 text-xs uppercase tracking-[0.15em] shadow-xl border-b-4 border-slate-300 active:scale-95 active:border-b-0 active:translate-y-1">
        <svg className="w-6 h-6" viewBox="0 0 24 24"><path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/><path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/><path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l3.66-2.84z"/><path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 12-4.53z"/></svg>
        Sync Profile
      </button>
    </GlassCard>
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
  return <LoadingScreen message="Establishing secure neural handshake..." />;
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