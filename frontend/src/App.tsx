// File: frontend/src/App.tsx
// Senior Refactor: High-End AI Dashboard Architecture.
// Focus: Layout Integrity, Motion Design, and SaaS Premium Styling.

import { useState, ReactNode, HTMLAttributes } from 'react';
import { BrowserRouter, Routes, Route, Navigate, useNavigate, useSearchParams, useParams, Link, useLocation } from 'react-router-dom';
import { QueryClient, QueryClientProvider, useQuery, useMutation } from '@tanstack/react-query';
import { 
  Loader2, Zap, AlertCircle, Plus, Utensils, ShoppingCart, 
  Timer, Globe, MapPin, Check, LayoutDashboard, LogOut, 
  ArrowRight, CheckCircle2, BrainCircuit, Search, ListChecks, 
  Activity, Sparkles, Box, Coffee, UtensilsCrossed, Download,
  ExternalLink, BarChart3, ShieldCheck
} from 'lucide-react';
import axios from 'axios';

// --- CORE CONFIG ---
const api = axios.create({ baseURL: '/api', withCredentials: true });

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token');
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

const queryClient = new QueryClient();

// --- THEME & UTILS ---
const HEADER_HEIGHT = "h-20"; // 80px

// --- SHARED UI COMPONENTS ---

interface BaseProps extends HTMLAttributes<HTMLDivElement> {
  children: ReactNode;
  className?: string;
}

const Navbar = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const isActive = (path: string) => location.pathname === path;
  
  const handleLogout = () => {
    localStorage.clear();
    navigate('/login');
  };

  return (
    <header className={`${HEADER_HEIGHT} border-b border-white/5 bg-[#09090b]/80 backdrop-blur-2xl fixed top-0 left-0 right-0 z-50 flex items-center`}>
      <div className="max-w-[1400px] mx-auto px-6 w-full flex justify-between items-center">
        <Link to="/" className="flex items-center gap-3 group">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-blue-600 to-blue-400 flex items-center justify-center text-white shadow-lg shadow-blue-500/20 group-hover:scale-105 transition-transform">
            <Zap size={22} fill="currentColor" />
          </div>
          <div className="flex flex-col leading-none">
            <span className="text-xl font-black tracking-tighter text-white uppercase italic">
              DietPlanner<span className="text-blue-500 not-italic">.</span>
            </span>
            <span className="text-[9px] font-black uppercase tracking-[0.3em] text-slate-500">Neural Core</span>
          </div>
        </Link>

        <div className="flex items-center gap-6">
          <nav className="hidden md:flex items-center gap-2">
            {[
              { path: '/', label: 'Vault', icon: LayoutDashboard },
              { path: '/create', label: 'Synthesize', icon: Sparkles },
            ].map((item) => (
              <Link 
                key={item.path}
                to={item.path} 
                className={`px-4 py-2 rounded-xl text-[11px] font-bold uppercase tracking-widest flex items-center gap-2.5 transition-all
                ${isActive(item.path) ? 'bg-white/5 text-white shadow-inner border border-white/10' : 'text-slate-500 hover:text-slate-300'}`}
              >
                <item.icon size={14} className={isActive(item.path) ? 'text-blue-500' : ''} />
                {item.label}
              </Link>
            ))}
          </nav>
          
          <div className="h-8 w-px bg-white/5 mx-2" />
          
          <button onClick={handleLogout} className="group p-2.5 rounded-xl bg-white/5 border border-white/5 text-slate-500 hover:text-red-400 hover:bg-red-400/10 transition-all">
            <LogOut size={18} />
          </button>
        </div>
      </div>
    </header>
  );
};

const MainLayout = ({ children }: { children: ReactNode }) => (
  <div className="min-h-screen bg-[#09090b] text-slate-300 flex flex-col font-sans selection:bg-blue-600/30">
    <Navbar />
    {/* Explicit Margin instead of padding to prevent scroll collisions */}
    <div className="mt-20 flex-1 flex flex-col overflow-x-hidden">
      {children}
    </div>
  </div>
);

const Card = ({ children, className = "", ...props }: BaseProps) => (
  <div 
    className={`bg-[#111114] border border-white/[0.04] rounded-[2rem] overflow-hidden ${className}`}
    {...props}
  >
    {children}
  </div>
);

const GlassCard = ({ children, className = "", ...props }: BaseProps) => (
  <div 
    className={`bg-white/[0.02] border border-white/[0.08] backdrop-blur-3xl rounded-[2.5rem] shadow-2xl ${className}`}
    {...props}
  >
    {children}
  </div>
);

const Badge = ({ children, variant = 'blue' }: { children: ReactNode, variant?: 'blue' | 'emerald' | 'amber' | 'rose' }) => {
  const colors = {
    blue: 'bg-blue-500/10 text-blue-400 border-blue-500/20',
    emerald: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
    amber: 'bg-amber-500/10 text-amber-400 border-amber-500/20',
    rose: 'bg-rose-500/10 text-rose-400 border-rose-500/20'
  };
  return (
    <span className={`px-3 py-1 rounded-full text-[10px] font-black uppercase tracking-widest border ${colors[variant]}`}>
      {children}
    </span>
  );
};

// --- CORE SCREENS ---

const Dashboard = () => {
  const navigate = useNavigate();
  const { data: goals, isLoading } = useQuery({
    queryKey: ['goals'],
    queryFn: () => api.get('/goals/list/').then(res => res.data.data)
  });

  if (isLoading) return <LoadingScreen message="Reconstructing mapping history..." />;

  return (
    <MainLayout>
      <div className="max-w-7xl mx-auto px-6 py-12 w-full">
        <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-6 mb-16">
          <div className="space-y-4">
            <div className="flex items-center gap-3 text-[10px] font-black uppercase tracking-[0.5em] text-blue-500">
              <Activity size={14} className="animate-pulse" /> Live Status: Secure
            </div>
            <h1 className="text-5xl font-black text-white tracking-tighter uppercase italic leading-none">
              Strategic<br/><span className="text-blue-500 not-italic">Vault.</span>
            </h1>
          </div>
          <button 
            onClick={() => navigate('/create')} 
            className="h-16 px-10 bg-white text-black font-black uppercase text-xs tracking-[0.2em] rounded-2xl hover:bg-slate-200 transition-all shadow-2xl active:scale-95 flex items-center gap-3"
          >
            <Plus size={20} strokeWidth={3} /> New Plan
          </button>
        </div>

        <div className="grid gap-8 sm:grid-cols-2 lg:grid-cols-3">
          {goals?.length === 0 ? (
            <div className="col-span-full py-32 flex flex-col items-center justify-center border border-white/5 rounded-[3rem] bg-white/[0.01]">
              <Box size={48} className="text-slate-800 mb-6" />
              <p className="text-slate-500 font-bold uppercase tracking-widest text-xs mb-8">System buffer empty</p>
              <button onClick={() => navigate('/create')} className="text-blue-500 font-black uppercase text-[10px] tracking-widest hover:underline flex items-center gap-2">
                Begin Synthesis <ArrowRight size={14} />
              </button>
            </div>
          ) : (
            goals?.map((goal: any) => (
              <GlassCard 
                key={goal.id} 
                className="p-8 hover:bg-white/[0.04] hover:border-blue-500/40 transition-all cursor-pointer group flex flex-col h-full"
                onClick={() => navigate(`/plan/${goal.id}`)}
              >
                <div className="flex justify-between items-start mb-10">
                  <Badge variant={goal.status === 'completed' ? 'emerald' : goal.status === 'failed' ? 'rose' : 'blue'}>
                    {goal.status.replace(/_/g, ' ')}
                  </Badge>
                  <span className="text-[10px] font-black text-slate-600 uppercase tracking-widest leading-none pt-1">
                    ID-{goal.id.toString().padStart(4, '0')}
                  </span>
                </div>
                
                <h3 className="text-2xl font-black text-white mb-6 leading-tight uppercase tracking-tight italic group-hover:text-blue-400 transition-colors line-clamp-3">
                  {goal.prompt}
                </h3>
                
                <div className="mt-auto pt-10 flex flex-col gap-4 border-t border-white/5">
                  <div className="flex items-center justify-between text-[10px] font-black uppercase tracking-widest text-slate-500">
                    <span className="flex items-center gap-2"><MapPin size={12} className="text-blue-500" /> {goal.city}</span>
                    <span className="flex items-center gap-2"><Timer size={12} className="text-blue-500" /> {goal.num_days}D Cycle</span>
                  </div>
                  <div className="flex justify-between items-center text-[9px] font-black text-slate-700 uppercase tracking-[0.3em] pt-2">
                    <span>Generated on {new Date(goal.created_at).toLocaleDateString()}</span>
                    <ArrowRight size={14} className="group-hover:translate-x-1 transition-transform group-hover:text-blue-500" />
                  </div>
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
      <div className="max-w-4xl mx-auto px-6 py-12 w-full">
        <header className="mb-20 text-center">
          <p className="text-[10px] font-black text-blue-500 uppercase tracking-[1em] mb-4">Phase I: Input Sequence</p>
          <h1 className="text-7xl font-black text-white tracking-tighter uppercase italic leading-[0.9]">
            Plan<br/><span className="text-blue-500 not-italic">Synthesis.</span>
          </h1>
        </header>

        <form onSubmit={e => { e.preventDefault(); mutation.mutate(formData); }} className="space-y-12">
          {/* Section 1: Objectives */}
          <div className="space-y-8">
            <div className="flex items-center gap-4 text-white">
              <div className="w-8 h-8 rounded-lg bg-blue-600 flex items-center justify-center font-black italic shadow-lg">1</div>
              <h2 className="text-2xl font-black uppercase tracking-tight italic">Core Objectives</h2>
            </div>
            
            <GlassCard className="p-8 space-y-8">
              <div className="space-y-4">
                <label className="text-[10px] font-black uppercase tracking-widest text-slate-500 flex items-center gap-2">
                  <BrainCircuit size={14} className="text-blue-500" /> Enter Dietary Logic
                </label>
                <textarea 
                  required 
                  className="w-full bg-black/40 border border-white/10 rounded-2xl p-6 text-xl font-bold text-white placeholder:text-slate-800 focus:outline-none focus:ring-2 focus:ring-blue-600/50 transition-all min-h-[200px] leading-relaxed"
                  placeholder="e.g. Lose 5kg in 4 weeks. High protein, intermittent fasting. Allergic to soy." 
                  value={formData.prompt} 
                  onChange={e => updateField('prompt', e.target.value)} 
                />
              </div>
              
              <div className="grid grid-cols-2 gap-8">
                <div className="space-y-3">
                  <label className="text-[10px] font-black uppercase tracking-widest text-slate-500">Region Hub</label>
                  <select 
                    className="w-full bg-white/5 border border-white/10 rounded-xl h-14 px-5 text-xs font-black text-white uppercase tracking-widest focus:outline-none" 
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
                <div className="space-y-3">
                  <label className="text-[10px] font-black uppercase tracking-widest text-slate-500">Local Anchor</label>
                  <input required type="text" className="w-full bg-white/5 border border-white/10 rounded-xl h-14 px-5 text-sm font-black text-white placeholder:text-slate-800 focus:outline-none" placeholder="e.g. Prague" value={formData.city} onChange={e => updateField('city', e.target.value)} />
                </div>
              </div>
            </GlassCard>
          </div>

          {/* Section 2: Mechanics */}
          <div className="space-y-8">
            <div className="flex items-center gap-4 text-white">
              <div className="w-8 h-8 rounded-lg bg-blue-600 flex items-center justify-center font-black italic shadow-lg">2</div>
              <h2 className="text-2xl font-black uppercase tracking-tight italic">Roadmap Mechanics</h2>
            </div>
            
            <GlassCard className="p-10 space-y-12">
              <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                {[
                  { id: 'breakfast', label: 'Breakfast', icon: Coffee },
                  { id: 'lunch', label: 'Lunch', icon: UtensilsCrossed },
                  { id: 'dinner', label: 'Dinner', icon: Utensils }
                ].map((meal) => (
                  <button
                    key={meal.id}
                    type="button"
                    onClick={() => updateField(meal.id, !(formData as any)[meal.id])}
                    className={`p-6 rounded-2xl border-2 transition-all flex flex-col items-center gap-4 ${
                      (formData as any)[meal.id] 
                        ? 'bg-blue-600/10 border-blue-600 text-white shadow-xl shadow-blue-500/10' 
                        : 'bg-white/[0.02] border-transparent text-slate-600 grayscale'
                    }`}
                  >
                    <meal.icon size={24} />
                    <span className="font-black uppercase text-[10px] tracking-[0.2em]">{meal.label}</span>
                  </button>
                ))}
              </div>

              <div className="grid sm:grid-cols-2 gap-12">
                <div className="space-y-6">
                  <div className="flex justify-between items-end">
                    <span className="text-[10px] font-black uppercase tracking-widest text-slate-600">Minor Meals</span>
                    <span className="text-xl font-black text-blue-500 italic">{formData.small_meals_per_day} Units</span>
                  </div>
                  <input type="range" min="0" max="5" className="w-full h-1.5 bg-white/10 rounded-full appearance-none accent-blue-600 cursor-pointer" value={formData.small_meals_per_day} onChange={e => updateField('small_meals_per_day', parseInt(e.target.value))} />
                </div>
                <div className="space-y-6">
                  <div className="flex justify-between items-end">
                    <span className="text-[10px] font-black uppercase tracking-widest text-slate-600">Daily Snacks</span>
                    <span className="text-xl font-black text-blue-500 italic">{formData.snacks_per_day} Units</span>
                  </div>
                  <input type="range" min="0" max="3" className="w-full h-1.5 bg-white/10 rounded-full appearance-none accent-blue-600 cursor-pointer" value={formData.snacks_per_day} onChange={e => updateField('snacks_per_day', parseInt(e.target.value))} />
                </div>
              </div>

              <div className="flex flex-wrap gap-3 pt-6 border-t border-white/5">
                <span className="w-full text-[10px] font-black uppercase tracking-widest text-slate-600 mb-2">Duration Matrix</span>
                {[1, 3, 7, 14, 30].map(d => (
                  <button key={d} type="button" onClick={() => updateField('num_days', d)} className={`px-6 py-2.5 rounded-xl text-[10px] font-black uppercase tracking-[0.2em] transition-all border-2 ${formData.num_days === d ? 'bg-blue-600 border-blue-600 text-white shadow-lg' : 'bg-white/5 border-transparent text-slate-600 hover:text-slate-400'}`}>
                    {d} Days
                  </button>
                ))}
              </div>
            </GlassCard>
          </div>

          {/* Section 3: Fulfillment */}
          <div className="space-y-8">
            <div className="flex items-center gap-4 text-white">
              <div className="w-8 h-8 rounded-lg bg-blue-600 flex items-center justify-center font-black italic shadow-lg">3</div>
              <h2 className="text-2xl font-black uppercase tracking-tight italic">Inventory Node</h2>
            </div>
            
            <GlassCard className="p-8">
              <div className="grid sm:grid-cols-2 gap-5">
                {shopsData?.shops?.map((shop: any) => (
                  <button 
                    key={shop.code} type="button" onClick={() => updateField('shop', shop.code)} 
                    className={`p-6 rounded-2xl border-2 text-left transition-all relative overflow-hidden group ${
                      formData.shop === shop.code 
                        ? 'bg-blue-600/10 border-blue-600 text-white shadow-2xl' 
                        : 'bg-white/5 border-transparent text-slate-600 hover:bg-white/[0.08]'
                    }`}
                  >
                    <span className="font-black text-sm block uppercase tracking-tight italic leading-none mb-1">{shop.name}</span>
                    <span className="text-[8px] font-black uppercase tracking-widest opacity-40">Live Matching Active</span>
                    {formData.shop === shop.code && <div className="absolute top-6 right-6 text-blue-500 bg-white p-1 rounded-lg"><Check size={14} strokeWidth={4} /></div>}
                  </button>
                ))}
              </div>
            </GlassCard>
          </div>

          <button 
            type="submit" 
            disabled={mutation.isPending || !formData.prompt} 
            className="w-full bg-white text-black h-24 rounded-[2rem] font-black text-2xl uppercase tracking-[0.5em] shadow-[0_30px_60px_-15px_rgba(255,255,255,0.1)] transition-all active:scale-[0.98] disabled:opacity-30 border-b-[12px] border-slate-300 flex items-center justify-center gap-6"
          >
            {mutation.isPending ? <div className="flex items-center gap-4"><Loader2 className="animate-spin" size={32} /> Syncing Hub</div> : "Commit Sequence"}
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
        <div className="w-20 h-20 rounded-3xl bg-rose-500/10 flex items-center justify-center text-rose-500 border border-rose-500/20 mb-8 animate-bounce">
          <AlertCircle size={40} />
        </div>
        <h1 className="text-5xl font-black tracking-tighter uppercase mb-4 italic leading-none">Logic Fault<span className="text-rose-600 not-italic">.</span></h1>
        <p className="text-slate-500 max-w-md mb-12 font-medium tracking-tight">The neural engine failed to resolve metabolic requirements against local inventory.</p>
        <button onClick={() => navigate('/')} className="px-10 h-14 bg-white text-black font-black uppercase text-xs tracking-widest rounded-2xl shadow-2xl">Return to Core</button>
      </div>
    );
  }

  if (statusData?.goal_status !== 'completed') {
    return (
      <MainLayout>
        <LoadingScreen message="Resolving strategic nutritional models with live inventory catalog..." status={statusData} />
      </MainLayout>
    );
  }

  const plan = goalDetail?.dietary_plan;
  if (!plan) return <LoadingScreen message="Unpacking data stream..." />;

  return (
    <MainLayout>
      <div className="max-w-[1400px] mx-auto px-6 py-12 w-full">
        <header className="mb-24 flex flex-col xl:flex-row xl:items-end justify-between gap-12 text-left">
          <div className="space-y-6">
            <div className="flex items-center gap-3">
              <Badge variant="emerald">Protocol Verified</Badge>
              <div className="flex items-center gap-2 text-[10px] font-black uppercase tracking-[0.4em] text-slate-600">
                <ShieldCheck size={14} className="text-blue-500" /> End-to-End Encryption
              </div>
            </div>
            <h1 className="text-8xl font-black text-white tracking-tighter uppercase italic leading-[0.8]">Outcome<span className="text-blue-500 not-italic">.</span></h1>
            <div className="flex flex-wrap gap-4 pt-4">
              {[
                { icon: MapPin, text: goalDetail.city },
                { icon: Timer, text: `${goalDetail.num_days} Day Cycle` },
                { icon: Globe, text: goalDetail.language_code.toUpperCase() }
              ].map((meta, i) => (
                <div key={i} className="flex items-center gap-3 bg-white/5 border border-white/10 px-5 py-2.5 rounded-xl text-[10px] font-black uppercase tracking-[0.2em] text-slate-400 shadow-xl">
                  <meta.icon size={14} className="text-blue-500" /> {meta.text}
                </div>
              ))}
            </div>
          </div>
          
          <div className="flex gap-4">
            <button className="flex items-center gap-3 bg-white text-black px-10 h-16 rounded-2xl font-black uppercase text-[11px] tracking-[0.2em] shadow-2xl active:scale-95 transition-all border-b-4 border-slate-300">
              <Download size={18} /> Archive Roadmap
            </button>
          </div>
        </header>

        <div className="grid xl:grid-cols-12 gap-16 items-start">
          <div className="xl:col-span-8 space-y-32">
            {plan.days?.map((day: any) => (
              <div key={day.day_number} className="relative group">
                <div className="absolute -left-10 top-0 bottom-0 w-[2px] bg-gradient-to-b from-blue-600/50 via-white/5 to-transparent hidden 2xl:block" />
                <div className="flex items-center gap-6 mb-12 text-left">
                  <div className="w-16 h-16 rounded-2xl bg-white text-black flex items-center justify-center text-4xl font-black italic shadow-[0_15px_40px_-10px_rgba(255,255,255,0.4)]">{day.day_number}</div>
                  <div>
                    <h2 className="text-4xl font-black text-white uppercase tracking-tighter italic leading-none mb-1">Genesis Node.</h2>
                    <p className="text-[10px] font-black uppercase tracking-[0.6em] text-slate-600">Cycle Phase Allocation</p>
                  </div>
                </div>
                
                <div className="grid gap-10">
                  {['breakfast', 'lunch', 'dinner'].map(m => day[m] && (
                    <GlassCard key={m} className="p-12 hover:bg-white/[0.04] hover:border-blue-500/30 transition-all text-left group/meal relative overflow-hidden">
                      <div className="absolute top-0 right-0 p-8 text-slate-800 opacity-20 pointer-events-none group-hover/meal:text-blue-500 transition-colors">
                        <UtensilsCrossed size={120} />
                      </div>
                      
                      <div className="flex justify-between items-center mb-12 relative z-10">
                        <span className="px-6 py-2 bg-blue-600 text-white rounded-xl text-[10px] font-black uppercase tracking-[0.3em] italic shadow-xl">{m} Strategy</span>
                        <div className="flex items-center gap-3 bg-black/30 px-4 py-2 rounded-xl text-[10px] font-black text-slate-500 border border-white/5 uppercase tracking-widest">
                          <Timer size={14} className="text-blue-500" /> {day[m].preparation_time || 20}M Setup
                        </div>
                      </div>
                      
                      <h3 className="text-4xl font-black text-white mb-6 tracking-tighter leading-tight uppercase italic group-hover/meal:text-blue-400 transition-colors relative z-10">{day[m].name}</h3>
                      <p className="text-slate-400 text-lg font-medium leading-relaxed mb-12 max-w-2xl relative z-10 italic">"{day[m].description}"</p>
                      
                      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 relative z-10">
                        {Object.entries(day[m].nutritional_info || {}).map(([k, v]: any) => (
                          <div key={k} className="bg-black/40 border border-white/5 p-5 rounded-2xl shadow-inner">
                            <p className="text-[9px] font-black text-slate-600 uppercase tracking-widest mb-1">{k}</p>
                            <p className="text-xl font-black text-slate-200 italic tracking-tighter leading-none">{v}</p>
                          </div>
                        ))}
                      </div>
                    </GlassCard>
                  ))}
                </div>
              </div>
            ))}
          </div>

          <aside className="xl:col-span-4 xl:sticky xl:top-28">
            <GlassCard className="p-10 border-blue-500/20 text-left shadow-[0_50px_100px_-20px_rgba(0,0,0,0.5)]">
              <div className="flex items-center gap-4 mb-16 border-b border-white/5 pb-10">
                <div className="w-14 h-14 rounded-2xl bg-blue-600/10 flex items-center justify-center text-blue-500 border border-blue-500/10 shadow-inner">
                  <ShoppingCart size={30} />
                </div>
                <div>
                  <h2 className="text-3xl font-black uppercase tracking-tighter italic text-white leading-none mb-1">Procurement.</h2>
                  <p className="text-[10px] font-black text-slate-600 uppercase tracking-widest">Live Inventory Node</p>
                </div>
              </div>

              <div className="space-y-8 max-h-[480px] overflow-y-auto pr-4 custom-scrollbar mb-16">
                {plan.shopping_list?.map((item: any, idx: number) => (
                  <div key={idx} className="group border-b border-white/5 pb-8 last:border-0 last:pb-0">
                    <div className="flex justify-between items-start mb-2">
                      <p className="text-base font-black text-white group-hover:text-blue-400 transition-colors uppercase tracking-tight italic leading-none">{item.ingredient}</p>
                      <p className="text-sm font-black text-blue-500 tabular-nums leading-none">{item.price} {item.currency}</p>
                    </div>
                    <div className="flex justify-between items-center text-[10px] font-black text-slate-600 uppercase tracking-widest">
                      <span className="bg-white/5 px-2.5 py-1 rounded-lg border border-white/5">{item.quantity} {item.unit}</span>
                      <span className="italic opacity-30 group-hover:opacity-100 transition-opacity max-w-[120px] truncate text-right">{item.matched_product_name}</span>
                    </div>
                  </div>
                ))}
              </div>

              <div className="pt-10 border-t-4 border-blue-600/30 space-y-10">
                <div className="flex justify-between items-end">
                  <div className="space-y-2">
                    <p className="text-[10px] font-black text-slate-600 uppercase tracking-[0.3em]">Matrix Overhead</p>
                    <p className="text-7xl font-black text-white italic tracking-tighter leading-none">
                      {plan.total_price}<span className="text-blue-500 text-2xl not-italic ml-2">{plan.currency}</span>
                    </p>
                  </div>
                </div>
                <button className="w-full h-20 bg-blue-600 hover:bg-blue-500 text-white rounded-2xl font-black uppercase text-xs tracking-[0.4em] shadow-blue-500/20 active:scale-[0.98] transition-all flex items-center justify-center gap-4">
                  Commit Order <ExternalLink size={18} />
                </button>
              </div>
            </GlassCard>
          </aside>
        </div>
      </div>
    </MainLayout>
  );
};

// --- SYSTEM COMPONENTS ---

const StatusTracker = ({ statusData }: { statusData: any }) => {
  const currentStatus = statusData?.goal_status || 'pending';
  const steps = [
    { label: 'Neural Handshake', keys: ['pending', 'awaiting_payment'] },
    { label: 'Synthesizing Roadmap', keys: ['payment_confirmed', 'processing', 'processing_meal_plan'] },
    { label: 'Syncing Inventory', keys: ['processing_shopping_list'] },
    { label: 'Integrity Scan', keys: ['validating'] },
    { label: 'Protocol Active', keys: ['completed'] }
  ];
  const activeStepIdx = steps.findIndex(s => s.keys.includes(currentStatus));

  return (
    <div className="space-y-6 text-left border-l border-white/5 pl-8">
      {steps.map((step, idx) => {
        const isPast = idx < activeStepIdx;
        const isCurrent = idx === activeStepIdx;
        return (
          <div key={idx} className={`relative flex items-center gap-5 transition-all duration-700 ${idx <= activeStepIdx ? 'opacity-100' : 'opacity-20'}`}>
            <div className={`w-3 h-3 rounded-full relative z-10 ${isPast ? 'bg-emerald-500 shadow-[0_0_10px_rgba(16,185,129,0.5)]' : isCurrent ? 'bg-blue-500 animate-ping' : 'bg-slate-800'}`}>
               {isCurrent && <div className="absolute inset-0 bg-blue-500 rounded-full" />}
            </div>
            <div className="flex flex-col">
              <span className={`text-[10px] font-black uppercase tracking-widest ${isCurrent ? 'text-blue-400' : isPast ? 'text-emerald-400' : 'text-slate-600'}`}>
                {step.label}
              </span>
              {isCurrent && <span className="text-[9px] font-bold text-blue-600/50 uppercase tracking-[0.2em] mt-1">Matrix Processing...</span>}
            </div>
          </div>
        );
      })}
    </div>
  );
};

const LoadingScreen = ({ message, status }: { message: string, status?: any }) => (
  <div className="flex-1 flex flex-col items-center justify-center p-12 text-center bg-[#09090b] relative overflow-hidden">
    <div className="absolute inset-0 bg-blue-600/[0.03] blur-[150px] pointer-events-none" />
    <div className="relative mb-20">
      <div className="absolute inset-0 bg-blue-500/10 blur-[100px] animate-pulse rounded-full" />
      <Loader2 className="animate-spin text-blue-500 relative z-10" size={120} strokeWidth={1} />
      <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 text-white/10 italic font-black text-xl z-10 animate-pulse">AI</div>
    </div>
    <div className="space-y-4 relative z-10 mb-20">
      <h2 className="text-6xl font-black text-white tracking-tighter uppercase italic leading-none">Mapping Node<span className="text-blue-500 animate-pulse">...</span></h2>
      <p className="text-slate-500 text-[10px] font-bold uppercase tracking-[0.4em] max-w-sm mx-auto leading-relaxed italic">{message}</p>
    </div>
    {status && <div className="max-w-xs w-full"><StatusTracker statusData={status} /></div>}
  </div>
);

const LoginView = () => (
  <div className="min-h-screen flex items-center justify-center p-6 bg-[#09090b] relative overflow-hidden">
    <div className="absolute top-0 left-0 w-full h-full pointer-events-none">
      <div className="absolute top-[-10%] left-[-10%] w-[800px] h-[800px] bg-blue-600/[0.05] blur-[200px] rounded-full" />
      <div className="absolute bottom-[-10%] right-[-10%] w-[900px] h-[900px] bg-purple-600/[0.02] blur-[250px] rounded-full" />
    </div>
    <GlassCard className="max-w-md w-full p-16 text-center relative z-10 shadow-[0_50px_100px_-20px_rgba(0,0,0,1)] border-white/[0.05]">
      <div className="inline-flex items-center justify-center w-24 h-24 rounded-[2rem] bg-gradient-to-br from-blue-600 to-blue-400 text-white mb-12 shadow-[0_0_40px_rgba(37,99,235,0.3)] group relative">
        <Zap size={48} fill="currentColor" className="relative z-10 group-hover:scale-110 transition-transform" />
      </div>
      <div className="mb-16 space-y-4">
        <h1 className="text-6xl font-black text-white tracking-tighter leading-[0.8] uppercase italic">Diet<br/><span className="text-blue-500 not-italic">Planner.</span></h1>
        <p className="text-slate-600 text-[10px] font-black tracking-[0.5em] uppercase border-t border-white/5 pt-6">Neural Metabolic Interface</p>
      </div>
      <button 
        onClick={() => window.location.href = '/api/auth/google/login/'} 
        className="w-full bg-white hover:bg-slate-200 text-black h-20 rounded-2xl font-black transition-all flex items-center justify-center gap-6 text-xs uppercase tracking-[0.2em] shadow-2xl border-b-8 border-slate-300 active:translate-y-2 active:border-b-0"
      >
        <svg className="w-7 h-7" viewBox="0 0 24 24"><path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/><path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/><path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l3.66-2.84z"/><path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 12-4.53z"/></svg>
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
  return <LoadingScreen message="Linking account to secure neural network..." />;
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