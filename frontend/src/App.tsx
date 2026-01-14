// File: frontend/src/App.tsx
// Senior Refactor: Standardized SaaS Layout Architecture for SPV/Desktop.
// Phase 8: Robust Flex Shell, Build Error Resolution, and Professional UI Optimization.

import { useState, useEffect, ReactNode, HTMLAttributes } from 'react';
import { BrowserRouter, Routes, Route, Navigate, useNavigate, useSearchParams, useParams, Link, useLocation } from 'react-router-dom';
import { QueryClient, QueryClientProvider, useQuery, useMutation } from '@tanstack/react-query';
import { 
  Loader2, Zap, AlertCircle, Plus, Utensils, ShoppingCart, 
  Timer, Globe, MapPin, Check, LayoutDashboard, LogOut, 
  ArrowRight, CheckCircle2, BrainCircuit, Search, ListChecks, 
  Activity, Sparkles, Box, Coffee, UtensilsCrossed, Download,
  ExternalLink, ShieldCheck, ChevronRight, Menu, X
} from 'lucide-react';
import axios from 'axios';

// --- CORE SYSTEM CONFIG ---
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

// --- DESIGN TOKENS ---
const CLASSES = {
  container: "max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 w-full",
  card: "bg-zinc-900/50 border border-white/[0.08] rounded-2xl shadow-xl overflow-hidden",
  input: "w-full bg-black/50 border border-white/10 rounded-xl p-4 text-white placeholder:text-zinc-600 focus:outline-none focus:ring-2 focus:ring-indigo-500/50 focus:border-indigo-500/50 transition-all",
  buttonPrimary: "inline-flex items-center justify-center gap-2 bg-indigo-600 hover:bg-indigo-500 text-white rounded-xl font-bold transition-all active:scale-95 shadow-lg shadow-indigo-500/20 px-6 py-3",
  title: "text-white font-black tracking-tight uppercase italic",
};

// --- SHARED UI COMPONENTS ---

interface BaseProps extends HTMLAttributes<HTMLDivElement> {
  children: ReactNode;
  className?: string;
}

const Navbar = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const isActive = (path: string) => location.pathname === path;
  
  const handleLogout = () => {
    localStorage.clear();
    navigate('/login');
  };

  const navLinks = [
    { path: '/', label: 'Vault', icon: LayoutDashboard },
    { path: '/create', label: 'Synthesize', icon: Sparkles },
  ];

  return (
    <header className="h-16 border-b border-white/[0.05] bg-zinc-950/90 backdrop-blur-md shrink-0 z-[100] relative">
      <div className={`${CLASSES.container} h-full flex justify-between items-center`}>
        <Link to="/" className="flex items-center gap-2.5 group">
          <div className="w-8 h-8 rounded-lg bg-indigo-600 flex items-center justify-center text-white shadow-lg">
            <Zap size={18} fill="currentColor" />
          </div>
          <span className="text-lg font-black tracking-tighter text-white uppercase italic">
            DietPlanner<span className="text-indigo-500 not-italic">.</span>
          </span>
        </Link>

        {/* Desktop Navigation */}
        <div className="hidden md:flex items-center gap-4">
          <div className="flex bg-zinc-900/50 p-1 rounded-xl border border-white/[0.05]">
            {navLinks.map((link) => (
              <Link 
                key={link.path}
                to={link.path} 
                className={`px-4 py-1.5 rounded-lg text-[10px] font-black uppercase tracking-widest flex items-center gap-2 transition-all
                ${isActive(link.path) ? 'bg-indigo-600 text-white shadow-md' : 'text-zinc-500 hover:text-zinc-300'}`}
              >
                <link.icon size={12} />
                {link.label}
              </Link>
            ))}
          </div>
          <div className="h-6 w-px bg-white/10" />
          <button onClick={handleLogout} className="p-2 text-zinc-500 hover:text-rose-500 transition-colors">
            <LogOut size={18} />
          </button>
        </div>

        {/* Mobile Toggle */}
        <button className="md:hidden p-2 text-zinc-400" onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)}>
          {isMobileMenuOpen ? <X size={20} /> : <Menu size={20} />}
        </button>
      </div>

      {/* Mobile Menu Overlay */}
      {isMobileMenuOpen && (
        <div className="md:hidden absolute top-full left-0 right-0 bg-zinc-950 border-b border-white/10 p-4 space-y-2 shadow-2xl z-50">
          {navLinks.map((link) => (
            <Link 
              key={link.path}
              to={link.path} 
              onClick={() => setIsMobileMenuOpen(false)}
              className={`flex items-center gap-3 p-4 rounded-xl font-bold uppercase text-xs tracking-widest ${isActive(link.path) ? 'bg-indigo-600 text-white' : 'text-zinc-500'}`}
            >
              <link.icon size={16} />
              {link.label}
            </Link>
          ))}
          <button onClick={handleLogout} className="flex w-full items-center gap-3 p-4 rounded-xl font-bold uppercase text-xs tracking-widest text-rose-500">
            <LogOut size={16} /> Logout
          </button>
        </div>
      )}
    </header>
  );
};

const MainLayout = ({ children }: { children: ReactNode }) => (
  <div className="h-screen flex flex-col bg-[#09090b] text-zinc-300 overflow-hidden font-sans selection:bg-indigo-500/30">
    <Navbar />
    {/* Explicit scroll area ensures content cannot overlay or underlay the header */}
    <main className="flex-1 overflow-y-auto scroll-smooth">
      {children}
    </main>
  </div>
);

const Badge = ({ children, variant = 'blue' }: { children: ReactNode, variant?: 'blue' | 'emerald' | 'amber' | 'rose' }) => {
  const colors = {
    blue: 'bg-indigo-500/10 text-indigo-400 border-indigo-500/20',
    emerald: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
    amber: 'bg-amber-500/10 text-amber-400 border-amber-500/20',
    rose: 'bg-rose-500/10 text-rose-400 border-rose-500/20'
  };
  return (
    <span className={`px-2.5 py-0.5 rounded-md text-[9px] font-black uppercase tracking-widest border ${colors[variant]}`}>
      {children}
    </span>
  );
};

const StatusTracker = ({ statusData }: { statusData: any }) => {
  const currentStatus = statusData?.goal_status || 'pending';
  const steps = [
    { label: 'Neural Link', keys: ['pending', 'awaiting_payment'] },
    { label: 'AI Synthesis', keys: ['payment_confirmed', 'processing', 'processing_meal_plan'] },
    { label: 'Catalog Sync', keys: ['processing_shopping_list'] },
    { label: 'Integrity Check', keys: ['validating'] },
    { label: 'Active Strategy', keys: ['completed'] }
  ];
  const activeIdx = steps.findIndex(s => s.keys.includes(currentStatus));

  return (
    <div className="space-y-6 text-left border-l border-zinc-800 pl-6 mt-12 max-w-xs mx-auto md:mx-0">
      {steps.map((step, idx) => {
        const isPast = idx < activeIdx;
        const isCurrent = idx === activeIdx;
        return (
          <div key={idx} className={`relative flex items-center gap-4 transition-all duration-500 ${idx <= activeIdx ? 'opacity-100' : 'opacity-20'}`}>
            <div className={`w-2 h-2 rounded-full z-10 ${isPast ? 'bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.5)]' : isCurrent ? 'bg-indigo-500 animate-pulse' : 'bg-zinc-800'}`} />
            <div className="flex flex-col">
              <span className={`text-[10px] font-black uppercase tracking-widest ${isCurrent ? 'text-indigo-400' : isPast ? 'text-emerald-400' : 'text-zinc-600'}`}>
                {step.label}
              </span>
            </div>
          </div>
        );
      })}
    </div>
  );
};

const LoadingScreen = ({ message, status }: { message: string, status?: any }) => (
  <div className="min-h-full flex flex-col items-center justify-center p-8 text-center">
    <div className="relative mb-12 flex items-center justify-center">
      <div className="absolute inset-0 bg-indigo-600/10 blur-[60px] animate-pulse rounded-full" />
      <Loader2 className="animate-spin text-indigo-500 relative z-10" size={80} strokeWidth={1.5} />
      <div className="absolute flex items-center justify-center">
        <Zap size={20} className="text-indigo-400 animate-pulse" />
      </div>
    </div>
    <div className="space-y-3 relative z-10 max-w-sm mx-auto">
      <h2 className="text-3xl font-black text-white tracking-tighter uppercase italic leading-none">Synthesizing<span className="text-indigo-500 animate-pulse">...</span></h2>
      <p className="text-zinc-500 text-[10px] font-bold uppercase tracking-widest italic leading-relaxed">{message}</p>
    </div>
    {status && <StatusTracker statusData={status} />}
  </div>
);

// --- CORE SYSTEM SCREENS ---

const Dashboard = () => {
  const navigate = useNavigate();
  const { data: goals, isLoading } = useQuery({
    queryKey: ['goals'],
    queryFn: () => api.get('/goals/list/').then(res => res.data.data)
  });

  if (isLoading) return <LoadingScreen message="Accessing encrypted vault buffer..." />;

  return (
    <MainLayout>
      <div className={`${CLASSES.container} py-12`}>
        <header className="flex flex-col sm:flex-row sm:items-end justify-between gap-8 mb-16 text-left">
          <div className="space-y-2">
            <div className="inline-flex items-center gap-2 text-[9px] font-black uppercase tracking-[0.4em] text-indigo-500 bg-indigo-500/5 px-3 py-1 rounded-lg border border-indigo-500/10">
              <Activity size={12} className="animate-pulse" /> Core: Active
            </div>
            <h1 className="text-5xl font-black text-white tracking-tighter uppercase italic leading-none">
              Strategic<br/><span className="text-indigo-500 not-italic">Vault.</span>
            </h1>
          </div>
          <button onClick={() => navigate('/create')} className={CLASSES.buttonPrimary}>
            <Plus size={20} strokeWidth={3} /> New Roadmap
          </button>
        </header>

        <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
          {goals?.length === 0 ? (
            <div className="col-span-full py-32 flex flex-col items-center justify-center border-2 border-dashed border-white/5 rounded-3xl bg-zinc-900/10 text-center">
              <Box size={48} className="text-zinc-800 mb-6" />
              <p className="text-zinc-600 font-bold uppercase tracking-widest text-[10px] mb-8 italic">Memory bank uninitialized</p>
              <button onClick={() => navigate('/create')} className="text-indigo-500 font-black uppercase text-[10px] tracking-widest hover:underline flex items-center gap-2">
                Initiate Handshake <ArrowRight size={14} />
              </button>
            </div>
          ) : (
            goals?.map((goal: any) => (
              <div 
                key={goal.id} 
                className={`${CLASSES.card} p-8 hover:bg-zinc-900 hover:border-indigo-500/30 transition-all cursor-pointer group flex flex-col text-left`}
                onClick={() => navigate(`/plan/${goal.id}`)}
              >
                <div className="flex justify-between items-start mb-10">
                  <Badge variant={goal.status === 'completed' ? 'emerald' : goal.status === 'failed' ? 'rose' : 'blue'}>
                    {goal.status.replace(/_/g, ' ')}
                  </Badge>
                  <span className="text-[10px] font-black text-zinc-700 uppercase">P-{goal.id}</span>
                </div>
                
                <h3 className="text-xl font-black text-white mb-8 leading-tight uppercase tracking-tight italic group-hover:text-indigo-400 transition-colors line-clamp-3">
                  {goal.prompt}
                </h3>
                
                <div className="mt-auto pt-8 flex flex-col gap-4 border-t border-white/[0.05]">
                  <div className="flex items-center justify-between text-[10px] font-bold uppercase tracking-widest text-zinc-500 italic">
                    <span className="flex items-center gap-2"><MapPin size={12} className="text-indigo-500" /> {goal.city}</span>
                    <span className="text-zinc-600">{goal.num_days}D Cycle</span>
                  </div>
                  <div className="flex justify-between items-center pt-2">
                    <span className="text-[8px] font-black text-zinc-800 uppercase tracking-[0.4em]">Log: {new Date(goal.created_at).toLocaleDateString()}</span>
                    <ChevronRight size={14} className="group-hover:translate-x-1 transition-transform group-hover:text-indigo-500 text-zinc-800" />
                  </div>
                </div>
              </div>
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
      <div className={`${CLASSES.container} py-12 max-w-4xl`}>
        <header className="mb-16 text-center space-y-4">
          <p className="text-[10px] font-black text-indigo-500 uppercase tracking-[1em]">Genesis Phase</p>
          <h1 className="text-6xl font-black text-white tracking-tighter uppercase italic leading-none">
            Parameter<br/><span className="text-indigo-500 not-italic">Input.</span>
          </h1>
        </header>

        <form onSubmit={e => { e.preventDefault(); mutation.mutate(formData); }} className="space-y-12">
          <section className="space-y-8 text-left">
            <h2 className="text-2xl font-black uppercase tracking-tight italic text-zinc-500 flex items-center gap-3">
              <span className="w-8 h-8 rounded-lg bg-indigo-600 flex items-center justify-center text-white not-italic text-sm italic shadow-lg">1</span>
              System Objectives
            </h2>
            
            <div className={`${CLASSES.card} p-8 space-y-8`}>
              <div className="space-y-4">
                <label className="text-[10px] font-black uppercase tracking-widest text-zinc-600 flex items-center gap-2 italic">
                  <BrainCircuit size={14} className="text-indigo-500" /> Defining Nutritional Requirements
                </label>
                <textarea 
                  required 
                  className={`${CLASSES.input} min-h-[220px] text-lg font-bold leading-relaxed`}
                  placeholder="e.g. Ketogenic roadmap for athlete. 2500 kcal baseline. Allergic to shellfish. Focus on Prague local inventory anchors..." 
                  value={formData.prompt} 
                  onChange={e => updateField('prompt', e.target.value)} 
                />
              </div>
              
              <div className="grid grid-cols-2 gap-8">
                <div className="space-y-2">
                  <label className="text-[9px] font-black uppercase tracking-widest text-zinc-600 italic">Regional Hub</label>
                  <select 
                    className="w-full bg-zinc-900 border border-white/10 rounded-xl h-14 px-5 text-[11px] font-black text-white uppercase tracking-widest focus:outline-none appearance-none cursor-pointer" 
                    value={formData.country} 
                    onChange={e => {
                      const c = e.target.value;
                      updateField('country', c);
                      updateField('language_code', c === 'CZ' ? 'cs' : 'sk');
                    }}
                  >
                    <option value="CZ">CZ HUB (CZK)</option>
                    <option value="SK">SK HUB (EUR)</option>
                  </select>
                </div>
                <div className="space-y-2">
                  <label className="text-[9px] font-black uppercase tracking-widest text-zinc-600 italic">Target City</label>
                  <input required type="text" className="w-full bg-zinc-900 border border-white/10 rounded-xl h-14 px-5 text-sm font-bold text-white placeholder:text-zinc-800 focus:outline-none" placeholder="e.g. Prague" value={formData.city} onChange={e => updateField('city', e.target.value)} />
                </div>
              </div>
            </div>
          </section>

          <section className="space-y-8 text-left">
            <h2 className="text-2xl font-black uppercase tracking-tight italic text-zinc-500 flex items-center gap-3">
              <span className="w-8 h-8 rounded-lg bg-indigo-600 flex items-center justify-center text-white not-italic text-sm italic shadow-lg">2</span>
              Roadmap Mechanics
            </h2>
            
            <div className={`${CLASSES.card} p-8 space-y-12`}>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-5">
                {[
                  { id: 'breakfast', label: 'Sunrise', icon: Coffee },
                  { id: 'lunch', label: 'Midday', icon: UtensilsCrossed },
                  { id: 'dinner', label: 'Sunset', icon: Utensils }
                ].map((meal) => (
                  <button
                    key={meal.id}
                    type="button"
                    onClick={() => updateField(meal.id, !(formData as any)[meal.id])}
                    className={`p-6 rounded-2xl border-2 transition-all flex flex-col items-center gap-4 ${
                      (formData as any)[meal.id] 
                        ? 'bg-indigo-600/10 border-indigo-600 text-white shadow-xl shadow-indigo-500/10' 
                        : 'bg-white/[0.02] border-transparent text-zinc-600 grayscale opacity-50'
                    }`}
                  >
                    <meal.icon size={24} />
                    <span className="font-black uppercase text-[10px] tracking-widest">{meal.label}</span>
                  </button>
                ))}
              </div>

              <div className="grid sm:grid-cols-2 gap-12">
                <div className="space-y-6">
                  <div className="flex justify-between items-end">
                    <span className="text-[10px] font-black uppercase tracking-widest text-zinc-600 italic">Minor Intervals</span>
                    <span className="text-xl font-black text-indigo-500 italic">{formData.small_meals_per_day} U/D</span>
                  </div>
                  <input type="range" min="0" max="5" className="w-full h-1.5 bg-white/10 rounded-full appearance-none accent-indigo-600 cursor-pointer" value={formData.small_meals_per_day} onChange={e => updateField('small_meals_per_day', parseInt(e.target.value))} />
                </div>
                <div className="space-y-6">
                  <div className="flex justify-between items-end">
                    <span className="text-[10px] font-black uppercase tracking-widest text-zinc-600 italic">Snack Density</span>
                    <span className="text-xl font-black text-indigo-500 italic">{formData.snacks_per_day} U/D</span>
                  </div>
                  <input type="range" min="0" max="3" className="w-full h-1.5 bg-white/10 rounded-full appearance-none accent-indigo-600 cursor-pointer" value={formData.snacks_per_day} onChange={e => updateField('snacks_per_day', parseInt(e.target.value))} />
                </div>
              </div>

              <div className="flex flex-wrap gap-2 pt-8 border-t border-white/[0.05]">
                <span className="w-full text-[9px] font-black uppercase tracking-widest text-zinc-700 mb-3 italic">Strategy Duration Matrix</span>
                {[1, 3, 7, 14, 30].map(d => (
                  <button key={d} type="button" onClick={() => updateField('num_days', d)} className={`px-5 py-2.5 rounded-xl text-[10px] font-black uppercase tracking-widest transition-all border border-white/5 ${formData.num_days === d ? 'bg-indigo-600 text-white shadow-lg border-indigo-500' : 'bg-white/[0.02] text-zinc-600 hover:text-zinc-400'}`}>
                    {d}D
                  </button>
                ))}
              </div>
            </div>
          </section>

          <section className="space-y-8 text-left">
            <h2 className="text-2xl font-black uppercase tracking-tight italic text-zinc-500 flex items-center gap-3">
              <span className="w-8 h-8 rounded-lg bg-indigo-600 flex items-center justify-center text-white not-italic text-sm italic shadow-lg">3</span>
              Fulfillment Anchor
            </h2>
            
            <div className={`${CLASSES.card} p-8`}>
              <div className="grid sm:grid-cols-2 gap-5">
                {shopsData?.shops?.map((shop: any) => (
                  <button 
                    key={shop.code} type="button" onClick={() => updateField('shop', shop.code)} 
                    className={`p-6 rounded-2xl border-2 text-left transition-all relative overflow-hidden group ${
                      formData.shop === shop.code 
                        ? 'bg-indigo-600/10 border-indigo-600 text-white shadow-xl' 
                        : 'bg-white/[0.02] border-transparent text-zinc-600 hover:bg-white/[0.05]'
                    }`}
                  >
                    <span className="font-black text-sm block uppercase tracking-tight italic mb-1">{shop.name}</span>
                    <span className="text-[8px] font-black uppercase tracking-widest opacity-30 italic leading-none">Catalog Sync Active</span>
                    {formData.shop === shop.code && <div className="absolute top-6 right-6 text-indigo-500 bg-white p-1 rounded-lg"><Check size={14} strokeWidth={4} /></div>}
                  </button>
                ))}
              </div>
            </div>
          </section>

          <button 
            type="submit" 
            disabled={mutation.isPending || !formData.prompt} 
            className="w-full h-24 bg-white text-black rounded-2xl font-black text-2xl uppercase tracking-[0.5em] shadow-[0_40px_80px_rgba(0,0,0,0.5)] transition-all active:scale-[0.98] disabled:opacity-30 border-b-8 border-zinc-300 flex items-center justify-center gap-6"
          >
            {mutation.isPending ? <div className="flex items-center gap-4"><Loader2 className="animate-spin" size={32} /> Synchronizing</div> : "Commit Sequence"}
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
      <div className="flex-1 flex flex-col items-center justify-center p-12 text-center bg-[#09090b] text-white">
        <div className="w-24 h-24 rounded-[2.5rem] bg-rose-500/10 flex items-center justify-center text-rose-500 border border-rose-500/20 mb-10 animate-bounce">
          <AlertCircle size={48} />
        </div>
        <h1 className="text-5xl font-black tracking-tighter uppercase mb-4 italic leading-none">Logic Error<span className="text-rose-600 not-italic">.</span></h1>
        <p className="text-zinc-600 max-w-sm mb-12 font-medium tracking-tight leading-relaxed italic opacity-80">System failed to reconcile nutritional logic with local inventory supply chains.</p>
        <button onClick={() => navigate('/')} className="px-10 h-14 bg-white text-black font-black uppercase text-[10px] tracking-widest rounded-2xl shadow-2xl">Return to Hub</button>
      </div>
    );
  }

  if (statusData?.goal_status !== 'completed') {
    return (
      <MainLayout>
        <LoadingScreen message="Cross-referencing metabolic Requirements with live supply inventory..." status={statusData} />
      </MainLayout>
    );
  }

  const plan = goalDetail?.dietary_plan;
  if (!plan) return <LoadingScreen message="Initializing data matrix..." />;

  return (
    <MainLayout>
      <div className={`${CLASSES.container} py-12`}>
        <header className="mb-24 flex flex-col lg:flex-row lg:items-end justify-between gap-12 text-left">
          <div className="space-y-6">
            <div className="flex items-center gap-3">
              <Badge variant="emerald">Strategic Output Ready</Badge>
              <div className="flex items-center gap-2 text-[10px] font-black uppercase tracking-[0.4em] text-zinc-700">
                <ShieldCheck size={14} className="text-indigo-500" /> Neural Handshake Success
              </div>
            </div>
            <h1 className="text-7xl sm:text-8xl font-black text-white tracking-tighter uppercase italic leading-[0.85]">Plan<br/>Outcome<span className="text-indigo-500 not-italic">.</span></h1>
            <div className="flex flex-wrap gap-4 pt-6">
              {[
                { icon: MapPin, text: goalDetail.city },
                { icon: Timer, text: `${goalDetail.num_days} Day Cycle` },
                { icon: Globe, text: goalDetail.language_code.toUpperCase() }
              ].map((meta, i) => (
                <div key={i} className="flex items-center gap-3 bg-zinc-900/50 border border-white/5 px-5 py-3 rounded-xl text-[10px] font-black uppercase tracking-[0.2em] text-zinc-500">
                  <meta.icon size={14} className="text-indigo-500" /> {meta.text}
                </div>
              ))}
            </div>
          </div>
          <button className="flex items-center gap-4 bg-white text-black px-10 h-16 rounded-2xl font-black uppercase text-[11px] tracking-[0.2em] shadow-2xl active:scale-95 border-b-4 border-zinc-300">
            <Download size={20} /> Archive PDF
          </button>
        </header>

        <div className="grid lg:grid-cols-12 gap-20 items-start">
          <div className="lg:col-span-8 space-y-32">
            {plan.days?.map((day: any) => (
              <div key={day.day_number} className="relative group text-left">
                <div className="absolute -left-10 top-0 bottom-0 w-[1px] bg-gradient-to-b from-indigo-600/50 via-white/5 to-transparent hidden 2xl:block" />
                <div className="flex items-center gap-6 mb-12">
                  <div className="w-14 h-14 rounded-2xl bg-white text-black flex items-center justify-center text-3xl font-black italic shadow-2xl">{day.day_number}</div>
                  <div>
                    <h2 className="text-3xl font-black text-white uppercase tracking-tighter italic leading-none mb-1">Cycle phase.</h2>
                    <p className="text-[10px] font-black uppercase tracking-[0.6em] text-zinc-700 italic">Temporal Allocation</p>
                  </div>
                </div>
                
                <div className="grid gap-10">
                  {['breakfast', 'lunch', 'dinner'].map(m => day[m] && (
                    <div key={m} className={`${CLASSES.card} p-10 hover:bg-zinc-900/80 hover:border-indigo-500/20 transition-all group/meal relative overflow-hidden text-left`}>
                      <div className="absolute top-0 right-0 p-8 text-zinc-900 opacity-20 pointer-events-none group-hover/meal:text-zinc-800 transition-colors">
                        <UtensilsCrossed size={120} />
                      </div>
                      
                      <div className="flex justify-between items-center mb-10 relative z-10">
                        <span className="px-5 py-1.5 bg-indigo-600 text-white rounded-lg text-[9px] font-black uppercase tracking-[0.3em] italic shadow-xl">{m} Sequence</span>
                        <div className="flex items-center gap-2 bg-black/30 px-3 py-1.5 rounded-lg text-[9px] font-black text-zinc-600 border border-white/5 uppercase tracking-widest italic">
                          <Timer size={14} className="text-indigo-500" /> {day[m].preparation_time || 20}M execution
                        </div>
                      </div>
                      
                      <h3 className="text-4xl font-black text-white mb-6 tracking-tighter leading-tight uppercase italic group-hover/meal:text-indigo-400 transition-colors relative z-10">{day[m].name}</h3>
                      <p className="text-zinc-500 text-lg font-medium leading-relaxed mb-12 max-w-2xl relative z-10 italic leading-relaxed">"{day[m].description}"</p>
                      
                      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 relative z-10">
                        {Object.entries(day[m].nutritional_info || {}).map(([k, v]: any) => (
                          <div key={k} className="bg-black/40 border border-white/5 p-5 rounded-2xl">
                            <p className="text-[8px] font-black text-zinc-600 uppercase tracking-widest mb-1 italic">{k}</p>
                            <p className="text-xl font-black text-zinc-300 italic tracking-tighter leading-none">{v}</p>
                          </div>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>

          <aside className="lg:col-span-4 lg:sticky lg:top-24 mb-12 lg:mb-0">
            <div className={`${CLASSES.card} p-10 border-indigo-500/10 text-left shadow-[0_50px_100px_-20px_rgba(0,0,0,0.8)]`}>
              <div className="flex items-center gap-4 mb-14 border-b border-white/5 pb-10">
                <div className="w-12 h-12 rounded-xl bg-indigo-600/10 flex items-center justify-center text-indigo-500 border border-indigo-500/10 shadow-inner">
                  <ShoppingCart size={28} />
                </div>
                <div>
                  <h2 className="text-2xl font-black uppercase tracking-tighter italic text-white leading-none mb-1">Inventory.</h2>
                  <p className="text-[9px] font-black text-zinc-700 uppercase tracking-widest italic">Procurement Stream</p>
                </div>
              </div>

              <div className="space-y-6 max-h-[450px] overflow-y-auto pr-4 custom-scrollbar mb-14">
                {plan.shopping_list?.map((item: any, idx: number) => (
                  <div key={idx} className="group border-b border-white/5 pb-6 last:border-0 last:pb-0">
                    <div className="flex justify-between items-start mb-2">
                      <p className="text-base font-black text-white group-hover:text-indigo-400 transition-colors uppercase tracking-tight italic leading-none">{item.ingredient}</p>
                      <p className="text-sm font-black text-indigo-500 tabular-nums leading-none">{item.price} {item.currency}</p>
                    </div>
                    <div className="flex justify-between items-center text-[10px] font-black text-zinc-600 uppercase tracking-widest">
                      <span className="bg-white/5 px-2.5 py-1 rounded-lg border border-white/5 italic">{item.quantity} {item.unit}</span>
                      <span className="italic opacity-30 group-hover:opacity-100 transition-opacity max-w-[120px] truncate text-right">{item.matched_product_name}</span>
                    </div>
                  </div>
                ))}
              </div>

              <div className="pt-10 border-t-2 border-indigo-600/30 space-y-10">
                <div className="flex justify-between items-end">
                  <div className="space-y-2 text-left">
                    <p className="text-[9px] font-black text-zinc-700 uppercase tracking-[0.3em] italic leading-none">Total Matrix Overhead</p>
                    <p className="text-6xl font-black text-white italic tracking-tighter leading-none">
                      {plan.total_price}<span className="text-blue-500 text-xl not-italic ml-2 uppercase leading-none">{plan.currency}</span>
                    </p>
                  </div>
                </div>
                <button className="w-full h-16 bg-indigo-600 hover:bg-indigo-500 text-white rounded-xl font-black uppercase text-xs tracking-[0.3em] shadow-indigo-500/20 active:scale-[0.98] transition-all flex items-center justify-center gap-4">
                  Commit Sync <ExternalLink size={16} />
                </button>
              </div>
            </div>
          </aside>
        </div>
      </div>
    </MainLayout>
  );
};

// --- AUTH & SYSTEM ---

const LoginView = () => (
  <div className="min-h-screen flex items-center justify-center p-6 bg-[#09090b] relative overflow-hidden">
    <div className="absolute top-0 left-0 w-full h-full pointer-events-none">
      <div className="absolute top-[-15%] left-[-15%] w-[800px] h-[800px] bg-indigo-600/[0.04] blur-[180px] rounded-full animate-pulse" />
      <div className="absolute bottom-[-15%] right-[-15%] w-[900px] h-[900px] bg-purple-600/[0.02] blur-[220px] rounded-full animate-pulse delay-1000" />
    </div>
    <div className="max-w-md w-full p-16 text-center relative z-10 bg-zinc-900/50 border border-white/[0.05] rounded-[3rem] shadow-[0_50px_100px_-20px_rgba(0,0,0,1)]">
      <div className="inline-flex items-center justify-center w-24 h-24 rounded-[2rem] bg-gradient-to-br from-indigo-600 to-indigo-400 text-white mb-12 shadow-[0_0_40px_rgba(37,99,235,0.3)] group relative">
        <Zap size={48} fill="currentColor" className="relative z-10 group-hover:scale-110 transition-transform" />
      </div>
      <div className="mb-16 space-y-4">
        <h1 className="text-6xl font-black text-white tracking-tighter leading-[0.8] uppercase italic">Diet<br/><span className="text-indigo-500 not-italic">Planner.</span></h1>
        <p className="text-zinc-700 text-[10px] font-black tracking-[0.5em] uppercase border-t border-white/5 pt-6 italic">Neural Metabolic System</p>
      </div>
      <button 
        onClick={() => window.location.href = '/api/auth/google/login/'} 
        className="w-full bg-white hover:bg-zinc-100 text-black h-16 rounded-2xl font-black transition-all flex items-center justify-center gap-5 text-xs uppercase tracking-[0.2em] shadow-2xl border-b-8 border-zinc-300 active:translate-y-2 active:border-b-0"
      >
        <svg className="w-6 h-6" viewBox="0 0 24 24"><path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/><path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/><path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l3.66-2.84z"/><path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 12-4.53z"/></svg>
        Secure Sync
      </button>
    </div>
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
  return <LoadingScreen message="Linking encrypted account to neural matrix..." />;
};

const ProtectedRoute = ({ children }: { children: any }) => {
  if (!localStorage.getItem('access_token')) return <Navigate to="/login" replace />;
  return children;
};

// --- ROOT APP ---

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