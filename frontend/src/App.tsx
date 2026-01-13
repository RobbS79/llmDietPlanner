// File: frontend/src/App.tsx | Route: / (and sub-routes)
import { useState, useEffect, useMemo } from 'react';
import { BrowserRouter, Routes, Route, Navigate, useNavigate, useSearchParams, useParams } from 'react-router-dom';
import { QueryClient, QueryClientProvider, useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { 
  Loader2, Zap, AlertCircle, Plus, Utensils, ShoppingCart, 
  Timer, Globe, MapPin, ChevronRight, Check, Trash2, 
  ChevronLeft, LayoutDashboard, LogOut, ArrowRight, CheckCircle2,
  RefreshCw, Info
} from 'lucide-react';
import axios from 'axios';

/**
 * UPDATED INTEGRATION PLAN:
 * 1. Global Navbar: Persistent navigation across all authenticated routes.
 * 2. Status Tracker: Detailed multi-step progress indicator for the AI engine.
 * 3. Stuck Detection: Visual cues when a task remains in 'pending' for too long.
 */

const getEnvVar = (key: string): string | undefined => {
  try {
    // @ts-ignore
    return import.meta.env[key];
  } catch (e) {
    return undefined;
  }
};

const GOOGLE_CLIENT_ID = getEnvVar('VITE_GOOGLE_CLIENT_ID');
const api = axios.create({ baseURL: '/api', withCredentials: true });

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token');
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});

// --- REUSABLE NAVIGATION ---

const Navbar = () => {
  const navigate = useNavigate();
  const handleLogout = () => {
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    navigate('/login');
  };

  return (
    <nav className="border-b border-white/5 bg-[#0a0f1e]/80 backdrop-blur-md sticky top-0 z-50">
      <div className="max-w-7xl mx-auto px-6 h-20 flex justify-between items-center">
        <div className="flex items-center gap-2 cursor-pointer group" onClick={() => navigate('/')}>
          <div className="w-10 h-10 rounded-xl bg-blue-600/10 flex items-center justify-center text-blue-500 group-hover:bg-blue-600 group-hover:text-white transition-all">
            <Zap size={20} fill="currentColor" />
          </div>
          <span className="text-xl font-black tracking-tighter">DietPlanner.</span>
        </div>
        <div className="flex items-center gap-8">
          <button 
            onClick={() => navigate('/')} 
            className="text-gray-400 hover:text-white transition-colors text-[10px] font-black uppercase tracking-widest flex items-center gap-2"
          >
            <LayoutDashboard size={16} /> Dashboard
          </button>
          <button 
            onClick={() => navigate('/create')} 
            className="text-gray-400 hover:text-white transition-colors text-[10px] font-black uppercase tracking-widest flex items-center gap-2"
          >
            <Plus size={16} /> Create
          </button>
          <div className="w-px h-6 bg-white/10 mx-2" />
          <button onClick={handleLogout} className="text-gray-500 hover:text-red-500 transition-colors">
            <LogOut size={20} />
          </button>
        </div>
      </div>
    </nav>
  );
};

// --- ENHANCED STATUS TRACKER ---

const StatusTracker = ({ currentStatus }: { currentStatus: string }) => {
  const steps = [
    { key: 'pending', label: 'Task Queued', desc: 'Waiting for worker availability', icon: Timer },
    { key: 'processing', label: 'AI Synthesis', desc: 'Gemini 2.0 is mapping nutrition', icon: Zap },
    { key: 'validating', label: 'Validation', desc: 'Verifying prices and constraints', icon: CheckCircle2 },
    { key: 'completed', label: 'Finalizing', desc: 'Reconstructing plan objects', icon: Check },
  ];

  // Map backend multi-processing states to our steps
  const normalizedStatus = useMemo(() => {
    if (currentStatus.includes('processing')) return 'processing';
    if (currentStatus.includes('validating')) return 'validating';
    return currentStatus;
  }, [currentStatus]);

  const currentIdx = steps.findIndex(s => s.key === normalizedStatus);

  return (
    <div className="mt-12 w-full max-w-sm space-y-6">
      {steps.map((step, idx) => {
        const isDone = idx < currentIdx || currentStatus === 'completed';
        const isCurrent = idx === currentIdx;
        return (
          <div key={step.key} className={`flex items-start gap-4 transition-all duration-700 ${isDone || isCurrent ? 'opacity-100' : 'opacity-20'}`}>
            <div className={`mt-0.5 w-8 h-8 rounded-xl flex-none flex items-center justify-center transition-all ${isDone ? 'bg-green-500/20 text-green-500' : isCurrent ? 'bg-blue-600 text-white shadow-lg shadow-blue-900/40 animate-pulse' : 'bg-white/5 text-gray-500'}`}>
              {isDone ? <Check size={16} strokeWidth={3} /> : <step.icon size={16} />}
            </div>
            <div className="space-y-1">
              <p className={`text-[10px] font-black uppercase tracking-[0.15em] ${isCurrent ? 'text-blue-500' : isDone ? 'text-green-500' : 'text-gray-500'}`}>
                {step.label} {isCurrent && '...'}
              </p>
              <p className="text-[10px] text-gray-600 font-medium lowercase italic">
                {isCurrent ? step.desc : isDone ? 'success' : 'waiting'}
              </p>
            </div>
          </div>
        );
      })}

      {currentStatus === 'pending' && (
        <div className="mt-12 p-4 rounded-2xl bg-amber-500/5 border border-amber-500/10 flex items-start gap-3">
          <Info size={16} className="text-amber-500 flex-none mt-0.5" />
          <p className="text-[10px] text-amber-500/60 font-medium leading-relaxed">
            Note: If stuck here for more than 2 minutes, the Celery worker might need a restart or the Redis queue is full.
          </p>
        </div>
      )}
    </div>
  );
};

// --- HELPER SCREENS ---

const LoadingScreen = ({ message, status }: { message: string, status?: string }) => (
  <div className="min-h-[calc(100vh-80px)] flex flex-col items-center justify-center text-white bg-[#0a0f1e] px-6">
    <div className="relative mb-12">
      <div className="absolute inset-0 bg-blue-600/20 blur-[60px] animate-pulse rounded-full" />
      <Loader2 className="animate-spin text-blue-500 relative z-10" size={80} strokeWidth={1} />
      <Zap size={32} className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 text-blue-400 animate-pulse z-10" />
    </div>
    <div className="text-center space-y-2 relative z-10">
      <p className="text-white font-black text-2xl tracking-tighter">AI Processing.</p>
      <p className="text-gray-500 font-black uppercase tracking-[0.3em] text-[10px]">{message}</p>
    </div>
    
    {status && <StatusTracker currentStatus={status} />}
  </div>
);

// --- FEATURE: DASHBOARD ---

const Dashboard = () => {
  const navigate = useNavigate();
  
  const { data: goals, isLoading } = useQuery({
    queryKey: ['goals'],
    queryFn: () => api.get('/goals/list/').then(res => res.data.data)
  });

  if (isLoading) return <LoadingScreen message="Accessing Secure Vault..." />;

  return (
    <div className="min-h-screen bg-[#0a0f1e]">
      <Navbar />
      <main className="max-w-7xl mx-auto px-6 py-12">
        <div className="mb-12 flex justify-between items-end">
          <div className="space-y-1">
            <p className="text-[10px] font-black text-blue-500 uppercase tracking-[0.4em] mb-2">User Intelligence</p>
            <h1 className="text-5xl font-black text-white tracking-tighter">Workspace.</h1>
          </div>
          <button 
            onClick={() => navigate('/create')}
            className="bg-white text-black px-8 py-3.5 rounded-2xl font-black uppercase tracking-widest text-[10px] hover:bg-gray-200 transition-all flex items-center gap-2 shadow-xl shadow-white/5"
          >
            <Plus size={18} /> Initiate New Plan
          </button>
        </div>

        <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
          {goals?.length === 0 ? (
            <div className="col-span-full py-32 text-center glass-card rounded-[3rem] border-dashed border-white/10">
              <Utensils size={48} className="mx-auto mb-6 text-gray-800" />
              <h3 className="text-xl font-bold text-white mb-2 uppercase tracking-tighter">Empty Roadmap Cache</h3>
              <p className="text-gray-600 mb-10 max-w-xs mx-auto text-sm font-medium">Start by defining your dietary constraints for the AI engine.</p>
              <button onClick={() => navigate('/create')} className="bg-blue-600 px-10 py-4 rounded-2xl font-black text-[10px] uppercase tracking-[0.2em] hover:bg-blue-500 transition-all">Generate First Plan</button>
            </div>
          ) : (
            goals?.map((goal: any) => (
              <div 
                key={goal.id} 
                onClick={() => navigate(`/plan/${goal.id}`)}
                className="glass-card p-8 rounded-[2.5rem] cursor-pointer hover:scale-[1.02] hover:border-blue-500/30 transition-all group relative overflow-hidden"
              >
                <div className="absolute top-0 right-0 w-32 h-32 bg-blue-600/5 blur-3xl -mr-16 -mt-16 group-hover:bg-blue-600/10 transition-colors" />
                
                <div className="flex justify-between items-start mb-6">
                  <div className={`px-3 py-1 rounded-lg text-[9px] font-black uppercase tracking-widest ${
                    goal.status === 'completed' ? 'bg-green-500/10 text-green-500 border border-green-500/20' : 
                    goal.status === 'failed' ? 'bg-red-500/10 text-red-500 border border-red-500/20' : 
                    'bg-blue-500/10 text-blue-500 border border-blue-500/20'
                  }`}>
                    {goal.status.replace(/_/g, ' ')}
                  </div>
                  <span className="text-[10px] font-bold text-gray-700 uppercase tracking-tighter">
                    {new Date(goal.created_at).toLocaleDateString()}
                  </span>
                </div>

                <div className="space-y-1 mb-8">
                   <div className="flex items-center gap-1.5 text-gray-500 text-[10px] font-black uppercase tracking-widest">
                     <MapPin size={10} className="text-blue-500" /> {goal.country} Plan: {goal.city}
                   </div>
                   <h3 className="text-xl font-bold text-white line-clamp-1 leading-tight">{goal.prompt}</h3>
                </div>

                <div className="flex items-center gap-4 pt-6 border-t border-white/5">
                  <div className="flex items-center gap-1.5 text-gray-500 font-black text-[10px] uppercase tracking-wider">
                    <Timer size={14} className="text-gray-600" /> {goal.num_days}d
                  </div>
                  <div className="flex items-center gap-1.5 text-gray-500 font-black text-[10px] uppercase tracking-wider">
                    <Globe size={14} className="text-gray-600" /> {goal.language_code}
                  </div>
                  <ArrowRight size={18} className="ml-auto text-gray-800 group-hover:text-blue-500 group-hover:translate-x-1 transition-all" />
                </div>
              </div>
            ))
          )}
        </div>
      </main>
    </div>
  );
};

// --- FEATURE: PLAN GENERATOR ---

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
    shop: 'ROHLIK'
  });

  const { data: shopsData } = useQuery({
    queryKey: ['shops', formData.country],
    queryFn: () => api.get(`/shops/?country=${formData.country}`).then(res => res.data.data),
    enabled: !!formData.country
  });

  const mutation = useMutation({
    mutationFn: (data: any) => api.post('/goals/', data),
    onSuccess: (res) => {
      navigate(`/plan/${res.data.data.goal_id}`);
    }
  });

  return (
    <div className="min-h-screen bg-[#0a0f1e] text-white">
      <Navbar />
      <div className="max-w-3xl mx-auto px-6 py-12">
        <header className="mb-16">
          <h1 className="text-6xl font-black tracking-tighter mb-4">Setup.</h1>
          <p className="text-gray-400 text-xl font-medium tracking-tight">AI will optimize your roadmap based on real-world stock availability.</p>
        </header>

        <form onSubmit={e => { e.preventDefault(); mutation.mutate(formData); }} className="space-y-6">
          <div className="glass-card p-12 rounded-[3.5rem] space-y-10 border border-white/5 shadow-3xl shadow-blue-950/20">
            <section className="space-y-4">
              <label className="text-[10px] font-black uppercase tracking-[0.3em] text-blue-500">I. CORE OBJECTIVE</label>
              <textarea 
                required
                className="input-field min-h-[180px] text-xl font-bold leading-relaxed py-6"
                placeholder="Target kcal, macro-split, or specific diet type (keto, vegan)..."
                value={formData.prompt}
                onChange={e => setFormData({...formData, prompt: e.target.value})}
              />
            </section>

            <div className="grid grid-cols-2 gap-8">
              <section className="space-y-3">
                <label className="text-[10px] font-black uppercase tracking-[0.3em] text-gray-600">Location Strategy</label>
                <select 
                  className="input-field bg-[#0a0f1e] font-bold"
                  value={formData.country}
                  onChange={e => setFormData({...formData, country: e.target.value, shop: '', language_code: e.target.value === 'CZ' ? 'cs' : 'sk'})}
                >
                  <option value="CZ">Czech Republic (Kč)</option>
                  <option value="SK">Slovakia (€)</option>
                </select>
              </section>
              <section className="space-y-3">
                <label className="text-[10px] font-black uppercase tracking-[0.3em] text-gray-600">City Hub</label>
                <input 
                  required
                  type="text" className="input-field font-bold" placeholder="e.g. Prague"
                  value={formData.city}
                  onChange={e => setFormData({...formData, city: e.target.value})}
                />
              </section>
            </div>

            <section className="space-y-4">
              <label className="text-[10px] font-black uppercase tracking-[0.3em] text-blue-500">II. SUPPLY SOURCE</label>
              <div className="grid grid-cols-2 gap-4">
                {shopsData?.shops?.map((shop: any) => (
                  <button
                    key={shop.code} type="button"
                    onClick={() => setFormData({...formData, shop: shop.code})}
                    className={`p-6 rounded-[2rem] border text-left transition-all relative ${
                      formData.shop === shop.code 
                      ? 'bg-blue-600/10 border-blue-500 text-white ring-1 ring-blue-500' 
                      : 'bg-white/5 border-white/5 text-gray-500 hover:border-white/20'
                    }`}
                  >
                    <span className="font-black text-xs block mb-1 uppercase tracking-widest">{shop.name}</span>
                    <span className="text-[9px] uppercase opacity-40 font-bold tracking-[0.2em]">Real-time Matching</span>
                    {formData.shop === shop.code && <div className="absolute top-4 right-6 bg-blue-500 p-1 rounded-full"><Check size={12} className="text-white"/></div>}
                  </button>
                ))}
              </div>
            </section>
          </div>

          <button 
            type="submit" 
            disabled={mutation.isPending || !formData.prompt}
            className="w-full bg-blue-600 hover:bg-blue-500 disabled:opacity-30 text-white py-10 rounded-3xl font-black text-xl uppercase tracking-[0.3em] shadow-2xl shadow-blue-500/20 active:scale-[0.98] transition-all"
          >
            {mutation.isPending ? (
              <span className="flex items-center justify-center gap-4"><Loader2 className="animate-spin" /> Synchronizing Engine</span>
            ) : (
              "Synthesize Roadmap"
            )}
          </button>
        </form>
      </div>
    </div>
  );
};

// --- FEATURE: PLAN VIEW & POLLING ---

const PlanView = () => {
  const { id } = useParams();
  const navigate = useNavigate();
  
  const { data: statusData } = useQuery({
    queryKey: ['taskStatus', id],
    queryFn: () => api.get(`/goals/${id}/task-status/`).then(res => res.data.data),
    refetchInterval: (query: any) => {
      const currentStatus = query?.state?.data?.goal_status;
      return currentStatus === 'completed' || currentStatus === 'failed' ? false : 3000;
    }
  });

  const { data: goalDetail } = useQuery({
    queryKey: ['plan', id],
    queryFn: () => api.get(`/goals/${id}/`).then(res => res.data.data),
    enabled: statusData?.goal_status === 'completed'
  });

  if (statusData?.goal_status === 'failed') {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center text-white bg-[#0a0f1e] p-8">
        <AlertCircle size={64} className="text-red-500 mb-8" />
        <h1 className="text-4xl font-black tracking-tighter mb-4 leading-none">Logic Failure.</h1>
        <p className="text-gray-500 mb-12 max-w-md text-center text-sm font-medium">The AI model was unable to resolve supply chain data or dietary constraints for this configuration.</p>
        <button onClick={() => navigate('/')} className="bg-white text-black px-10 py-4 rounded-2xl font-black uppercase tracking-widest text-[10px]">Back to Workspace</button>
      </div>
    );
  }

  if (statusData?.goal_status !== 'completed') {
    return (
      <>
        <Navbar />
        <LoadingScreen 
          message="Executing nutrition synthesis protocols" 
          status={statusData?.goal_status} 
        />
      </>
    );
  }

  const plan = goalDetail?.dietary_plan;
  if (!plan) return <LoadingScreen message="Syncing generated plan objects..." />;

  return (
    <div className="min-h-screen bg-[#0a0f1e] text-white">
      <Navbar />
      <div className="max-w-6xl mx-auto px-6 py-16">
        <header className="flex flex-col md:flex-row md:items-end justify-between mb-20 gap-8">
          <div className="space-y-4">
            <h1 className="text-7xl font-black tracking-tighter leading-none">Result.</h1>
            <div className="flex items-center gap-4 text-gray-500 font-black uppercase tracking-widest text-[10px]">
               <MapPin size={14} /> {goalDetail.city} hub • {goalDetail.num_days} day roadmap
            </div>
          </div>
          <div className="flex items-center gap-4 bg-white/5 p-4 rounded-[2rem] border border-white/5 pr-10">
             <div className="w-14 h-14 bg-green-500/10 border border-green-500/20 rounded-2xl flex items-center justify-center text-green-500 shadow-lg">
               <CheckCircle2 size={32} />
             </div>
             <div>
               <p className="text-[9px] font-black text-gray-600 uppercase tracking-[0.2em] mb-1">Status Protocol</p>
               <p className="font-black text-sm text-green-500 tracking-tight uppercase">Verified Secure</p>
             </div>
          </div>
        </header>

        <div className="grid lg:grid-cols-3 gap-16">
          <div className="lg:col-span-2 space-y-20">
            {plan.days?.map((day: any) => (
              <section key={day.day_number} className="relative">
                <div className="absolute -left-12 top-0 bottom-0 w-px bg-gradient-to-b from-blue-500/30 via-transparent to-transparent hidden xl:block" />
                
                <div className="flex items-center gap-6 mb-12">
                  <div className="flex-none w-16 h-16 rounded-[1.5rem] bg-blue-600 flex items-center justify-center text-2xl font-black shadow-2xl shadow-blue-900/30">
                    {day.day_number}
                  </div>
                  <h2 className="text-4xl font-black tracking-tight uppercase">Strategy Overview</h2>
                </div>

                <div className="grid gap-8">
                  {['breakfast', 'lunch', 'dinner'].map(mealKey => day[mealKey] && (
                    <div key={mealKey} className="glass-card p-12 rounded-[3.5rem] group hover:border-blue-500/20 transition-all border border-white/5 relative">
                      <div className="flex justify-between items-center mb-8">
                        <span className="px-4 py-1.5 rounded-full bg-blue-600/10 text-blue-500 text-[9px] font-black uppercase tracking-[0.2em] border border-blue-500/20">
                          {mealKey}
                        </span>
                        <div className="flex items-center gap-2 text-gray-600 text-[10px] font-black uppercase tracking-widest">
                           <Timer size={14} className="text-gray-700" /> {day[mealKey].preparation_time || 15}m PREP
                        </div>
                      </div>
                      <h3 className="text-3xl font-black mb-4 group-hover:text-blue-400 transition-colors tracking-tight">{day[mealKey].name}</h3>
                      <p className="text-gray-400 leading-relaxed mb-10 text-lg font-medium">{day[mealKey].description}</p>
                      
                      <div className="space-y-6">
                        <div className="flex flex-wrap gap-4">
                           {Object.entries(day[mealKey].nutritional_info || {}).map(([k, v]: any) => (
                             <div key={k} className="bg-[#0a0f1e] px-5 py-3 rounded-2xl border border-white/5 flex flex-col gap-1">
                               <p className="text-[8px] text-gray-600 font-black uppercase tracking-widest">{k}</p>
                               <p className="font-black text-sm text-white">{v}</p>
                             </div>
                           ))}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </section>
            ))}
          </div>

          <div className="space-y-8">
            <div className="glass-card p-10 rounded-[3.5rem] sticky top-28 border border-blue-500/10 shadow-3xl shadow-blue-950/40">
               <div className="flex items-center gap-4 mb-12 pb-8 border-b border-white/5">
                 <div className="w-12 h-12 rounded-2xl bg-blue-600/10 flex items-center justify-center text-blue-500 shadow-inner">
                    <ShoppingCart size={24} />
                 </div>
                 <h2 className="text-3xl font-black tracking-tighter uppercase leading-none">Supply.</h2>
               </div>

               <div className="space-y-8 max-h-[450px] overflow-y-auto pr-4 custom-scrollbar">
                  {plan.shopping_list?.map((item: any, idx: number) => (
                    <div key={idx} className="group pb-6 border-b border-white/5 last:border-0 last:pb-0">
                      <div className="flex justify-between items-start mb-2">
                        <p className="font-black text-sm text-white group-hover:text-blue-400 transition-colors uppercase tracking-tight">{item.ingredient}</p>
                        <p className="text-xs font-black text-blue-500 tabular-nums">{item.price} {item.currency}</p>
                      </div>
                      <div className="flex justify-between items-center text-[9px] font-black text-gray-600 uppercase tracking-widest">
                        <span>{item.quantity} {item.unit}</span>
                        <span className="italic opacity-30 line-clamp-1 max-w-[100px] text-right">{item.matched_product_name}</span>
                      </div>
                    </div>
                  ))}
               </div>

               <div className="mt-12 pt-10 border-t-4 border-blue-600/20 space-y-6">
                  <div className="flex justify-between items-center text-gray-600 uppercase tracking-[0.2em] text-[10px] font-black">
                     <span>Estimated Overhead</span>
                     <span className="bg-blue-600/10 px-3 py-1 rounded-full text-blue-500">{plan.shopping_list?.length} Nodes</span>
                  </div>
                  <div className="flex justify-between items-end">
                    <span className="text-6xl font-black tracking-tighter leading-none">{plan.total_price}</span>
                    <span className="text-2xl font-black text-blue-500 tracking-tighter">{plan.currency}</span>
                  </div>
                  <button className="w-full bg-white text-black py-6 rounded-2xl font-black uppercase tracking-widest text-[10px] hover:bg-gray-200 transition-all flex items-center justify-center gap-3 mt-6">
                    Sync to Retailer <ArrowRight size={18} />
                  </button>
               </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

// --- AUTH COMPONENTS ---

const LoginView = () => {
  const handleGoogleLogin = () => window.location.href = '/api/auth/google/login/';
  return (
    <div className="min-h-screen flex items-center justify-center p-6 bg-[#0a0f1e] overflow-hidden">
      <div className="absolute top-0 left-0 w-full h-full pointer-events-none opacity-50">
        <div className="absolute top-1/4 left-1/4 w-[500px] h-[500px] bg-blue-600/10 blur-[120px] rounded-full animate-pulse-slow" />
        <div className="absolute bottom-1/4 right-1/4 w-[600px] h-[600px] bg-purple-600/5 blur-[150px] rounded-full animate-pulse-slow delay-700" />
      </div>

      <div className="max-w-md w-full glass-card rounded-[4rem] p-16 text-center relative z-10 shadow-3xl border border-white/5">
        <div className="inline-flex items-center justify-center w-24 h-24 rounded-[2.5rem] bg-blue-600/10 text-blue-500 mb-12 shadow-inner border border-white/5">
          <Zap size={48} fill="currentColor" className="animate-pulse" />
        </div>
        <div className="mb-16">
          <h1 className="text-6xl font-black text-white mb-4 tracking-tighter leading-none">DietPlanner.</h1>
          <p className="text-gray-500 text-lg font-bold tracking-tight uppercase tracking-[0.2em] text-[10px]">AI-Native Nutrition Engine.</p>
        </div>
        
        <button 
          onClick={handleGoogleLogin} 
          className="w-full bg-white hover:bg-gray-100 text-black py-7 rounded-[2rem] font-black transition-all flex items-center justify-center gap-4 text-xs uppercase tracking-widest shadow-2xl active:scale-[0.98]"
        >
          <svg className="w-6 h-6" viewBox="0 0 24 24"><path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/><path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/><path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l3.66-2.84z"/><path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 12-4.53z"/></svg>
          Sync with Google
        </button>
        
        <div className="mt-16 flex items-center justify-center gap-10 opacity-30">
           <div className="text-center">
             <p className="text-[9px] font-black text-white uppercase tracking-widest mb-1">CEE Reach</p>
             <p className="text-[10px] font-bold text-gray-400">CZ / SK</p>
           </div>
           <div className="w-px h-6 bg-white/10" />
           <div className="text-center">
             <p className="text-[9px] font-black text-white uppercase tracking-widest mb-1">Protocol</p>
             <p className="text-[10px] font-bold text-gray-400">HTTPS / JWT</p>
           </div>
        </div>
      </div>
    </div>
  );
};

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
      navigate('/login?error=sync_failed');
    }
  }, [params, navigate]);

  return <LoadingScreen message="Establishing Encrypted Protocol..." />;
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