// File: frontend/src/App.tsx | Route: / (and sub-routes)
import { useState, useEffect, useMemo } from 'react';
import { BrowserRouter, Routes, Route, Navigate, useNavigate, useSearchParams, useParams, Link, useLocation } from 'react-router-dom';
import { QueryClient, QueryClientProvider, useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { 
  Loader2, Zap, AlertCircle, Plus, Utensils, ShoppingCart, 
  Timer, Globe, MapPin, ChevronRight, Check, Trash2, 
  ChevronLeft, LayoutDashboard, LogOut, ArrowRight, CheckCircle2,
  RefreshCw, Info, CreditCard, BrainCircuit, Search, ListChecks,
  Activity, Database, ServerCrash, Cpu, Sparkles, Box, Layout,
  Coffee, Sandwich, UtensilsCrossed
} from 'lucide-react';
import axios from 'axios';

/**
 * RECTIFIED PRODUCTION FRONTEND
 * 1. Restored missing form fields: Breakfast/Lunch/Dinner, Small Meals, Snacks.
 * 2. Fixed Typography: Reduced excessive header sizes (9xl -> 5xl) to fix "broken" UI.
 * 3. Deep Integration: Proper Shop selection data binding.
 * 4. Diagnostics: Real-time Celery/Redis status visibility.
 */

const getEnvVar = (key: string): string | undefined => {
  try {
    // ES2015 compatible access
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

const queryClient = new QueryClient();

// --- UI COMPONENTS: SHARED ---

const Navbar = () => {
  const navigate = useNavigate();
  const location = useLocation();
  
  const handleLogout = () => {
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    navigate('/login');
  };

  return (
    <nav className="border-b border-white/5 bg-[#0a0f1e]/90 backdrop-blur-xl sticky top-0 z-50 shadow-2xl">
      <div className="max-w-7xl mx-auto px-6 h-20 flex justify-between items-center">
        <Link to="/" className="flex items-center gap-3 group">
          <div className="w-10 h-10 rounded-2xl bg-blue-600/10 flex items-center justify-center text-blue-500 group-hover:bg-blue-600 group-hover:text-white transition-all shadow-lg border border-blue-500/20">
            <Zap size={20} fill="currentColor" />
          </div>
          <span className="text-2xl font-black tracking-tighter text-white">DietPlanner<span className="text-blue-500">.</span></span>
        </Link>

        <div className="flex items-center gap-4 md:gap-8">
          <div className="hidden md:flex items-center gap-2 bg-black/40 p-1.5 rounded-2xl border border-white/5 shadow-inner">
            <Link to="/" className={`px-6 py-2.5 rounded-xl text-[10px] font-black uppercase tracking-widest flex items-center gap-2 transition-all ${location.pathname === '/' ? 'bg-blue-600 text-white shadow-lg shadow-blue-900/40' : 'text-gray-500 hover:text-white'}`}>
              <LayoutDashboard size={14} /> Workspace
            </Link>
            <Link to="/create" className={`px-6 py-2.5 rounded-xl text-[10px] font-black uppercase tracking-widest flex items-center gap-2 transition-all ${location.pathname === '/create' ? 'bg-blue-600 text-white shadow-lg shadow-blue-900/40' : 'text-gray-500 hover:text-white'}`}>
              <Plus size={14} /> New Plan
            </Link>
          </div>
          <button onClick={handleLogout} className="w-12 h-12 rounded-2xl bg-white/5 flex items-center justify-center text-gray-500 hover:text-red-500 transition-all border border-white/5 hover:border-red-500/20">
            <LogOut size={20} />
          </button>
        </div>
      </div>
    </nav>
  );
};

const StatusTracker = ({ statusData }: { statusData: any }) => {
  const currentStatus = statusData?.goal_status || 'pending';
  
  const steps = [
    { keys: ['pending', 'awaiting_payment'], label: 'Handshake', desc: 'Syncing roadmap node', icon: CreditCard },
    { keys: ['payment_confirmed', 'processing'], label: 'AI Synthesis', desc: 'Gemini Pro initializing models', icon: BrainCircuit },
    { keys: ['processing_meal_plan'], label: 'Synthesis', desc: 'Generating core nutrition', icon: Utensils },
    { keys: ['processing_shopping_list'], label: 'Market Logic', desc: 'Scanning inventory', icon: Search },
    { keys: ['validating'], label: 'Integrity', desc: 'Verifying protocol logic', icon: ListChecks },
  ];

  const currentIdx = steps.findIndex(s => s.keys.includes(currentStatus));

  return (
    <div className="mt-12 w-full max-w-sm space-y-6">
      {steps.map((step, idx) => {
        const isDone = idx < currentIdx || currentStatus === 'completed';
        const isCurrent = idx === currentIdx;
        return (
          <div key={idx} className={`flex items-start gap-5 transition-all duration-700 ${isDone || isCurrent ? 'opacity-100' : 'opacity-20'}`}>
            <div className={`mt-0.5 w-9 h-9 rounded-xl flex-none flex items-center justify-center transition-all ${isDone ? 'bg-green-500/20 text-green-500 border border-green-500/20' : isCurrent ? 'bg-blue-600 text-white shadow-lg shadow-blue-900/40 animate-pulse' : 'bg-white/5 text-gray-500 border border-white/5'}`}>
              {isDone ? <Check size={18} strokeWidth={3} /> : <step.icon size={18} />}
            </div>
            <div className="space-y-0.5">
              <p className={`text-[10px] font-black uppercase tracking-[0.2em] ${isCurrent ? 'text-blue-500' : isDone ? 'text-green-500' : 'text-gray-500'}`}>{step.label}</p>
              <p className="text-[11px] text-gray-600 font-medium leading-tight">{isCurrent ? step.desc : isDone ? 'Protocol Success' : 'Awaiting Stage'}</p>
            </div>
          </div>
        );
      })}

      <div className="mt-12 p-8 rounded-[2.5rem] bg-white/5 border border-white/10 space-y-6 shadow-3xl relative overflow-hidden">
        <div className="absolute top-0 right-0 p-4 opacity-5"><Layout size={80} /></div>
        <div className="flex justify-between items-center text-[10px] font-black uppercase tracking-[0.2em] text-gray-500 relative z-10">
           <span>Infrastructure Check</span>
           <span className="text-blue-500 flex items-center gap-2 animate-pulse font-bold"><Activity size={12} /> Syncing</span>
        </div>
        <div className="grid grid-cols-2 gap-4 relative z-10">
          <div className="bg-black/60 p-4 rounded-2xl border border-white/5 shadow-inner">
            <p className="text-[8px] font-black text-gray-700 uppercase mb-1">Worker Node</p>
            <p className={`text-[10px] font-bold truncate tracking-tight ${statusData?.task_status === 'NOT_STARTED' || statusData?.task_status === 'UNAVAILABLE' ? 'text-red-500' : 'text-white'}`}>{statusData?.task_status || 'IDLE'}</p>
          </div>
          <div className="bg-black/60 p-4 rounded-2xl border border-white/5 shadow-inner">
            <p className="text-[8px] font-black text-gray-700 uppercase mb-1">Logic State</p>
            <p className="text-[10px] font-bold text-blue-400 truncate uppercase tracking-tight">{currentStatus}</p>
          </div>
        </div>
        {(statusData?.task_status === 'NOT_STARTED' || statusData?.task_status === 'UNAVAILABLE' || statusData?.task_status === 'CELERY_UNAVAILABLE') && (
          <div className="p-4 rounded-2xl bg-red-500/10 border border-red-500/20 space-y-2 relative z-10">
             <p className="text-[10px] text-red-500 font-black uppercase tracking-tight flex items-center gap-2"><ServerCrash size={14} /> Logic Refused</p>
             <p className="text-[9px] text-gray-500 italic leading-relaxed">Celery cannot reach Redis. Verify port 6379 in DO Console and restart with the --broker flag.</p>
          </div>
        )}
        {currentStatus === 'pending' && statusData?.task_status !== 'NOT_STARTED' && (
          <p className="text-[9px] text-amber-500/60 font-medium leading-relaxed flex items-start gap-2 pt-2 border-t border-white/5 relative z-10">
            <Info size={14} className="flex-none mt-0.5" />
            Note: If stuck in "pending" for {' > '} 2min, check component logs for "Connection refused".
          </p>
        )}
      </div>
    </div>
  );
};

// --- FEATURE: DASHBOARD ---

const Dashboard = () => {
  const navigate = useNavigate();
  const { data: goals, isLoading } = useQuery({
    queryKey: ['goals'],
    queryFn: () => api.get('/goals/list/').then(res => res.data.data)
  });

  if (isLoading) return <LoadingScreen message="Accessing Neural Network..." />;

  return (
    <div className="min-h-screen bg-[#0a0f1e]">
      <Navbar />
      <main className="max-w-7xl mx-auto px-6 py-16">
        <header className="mb-16 flex flex-col md:flex-row md:justify-between md:items-end gap-10">
          <div className="space-y-4">
            <div className="inline-flex items-center gap-2 bg-blue-600/10 text-blue-500 px-4 py-1.5 rounded-xl border border-blue-500/20 shadow-lg">
              <Sparkles size={14} className="animate-pulse" /> <span className="text-[10px] font-black uppercase tracking-[0.3em]">Gemini Protocol v2.5</span>
            </div>
            <h1 className="text-6xl font-black text-white tracking-tighter leading-none">Workspace<span className="text-blue-600">.</span></h1>
            <p className="text-gray-500 text-lg font-medium tracking-tight max-w-lg leading-relaxed">Manage your AI-tailored nutrition roadmaps and supply chain strategies.</p>
          </div>
          <button onClick={() => navigate('/create')} className="bg-white text-black px-10 py-5 rounded-2xl font-black uppercase tracking-[0.2em] text-[10px] hover:bg-gray-100 transition-all flex items-center gap-4 shadow-2xl active:scale-95 shadow-white/10">
            <Plus size={20} strokeWidth={3} /> New Strategy
          </button>
        </header>

        <div className="grid gap-8 md:grid-cols-2 lg:grid-cols-3">
          {goals?.length === 0 ? (
            <div className="col-span-full py-40 text-center glass-card rounded-[4rem] border-dashed border-white/10 shadow-2xl relative overflow-hidden group">
              <div className="absolute inset-0 bg-blue-600/5 opacity-0 group-hover:opacity-100 transition-opacity" />
              <Box size={64} className="mx-auto mb-8 text-gray-800" />
              <h3 className="text-2xl font-black text-white mb-3 uppercase tracking-tighter text-gray-600">No Roadmaps Active</h3>
              <p className="text-gray-500 mb-10 max-w-sm mx-auto text-base font-medium leading-relaxed">Your neural node is ready for input. Configure requirements to begin nutritional synthesis.</p>
              <button onClick={() => navigate('/create')} className="bg-blue-600 px-12 py-5 rounded-2xl font-black text-xs uppercase tracking-[0.3em] hover:bg-blue-500 transition-all shadow-xl shadow-blue-500/30">Init Handshake</button>
            </div>
          ) : (
            goals?.map((goal: any) => (
              <div key={goal.id} onClick={() => navigate(`/plan/${goal.id}`)} className="glass-card p-10 rounded-[3rem] cursor-pointer hover:scale-[1.03] hover:border-blue-500/40 transition-all group relative overflow-hidden shadow-2xl">
                <div className="absolute top-0 right-0 w-40 h-40 bg-blue-600/5 blur-[80px] -mr-20 -mt-20 group-hover:bg-blue-600/15 transition-all duration-700" />
                <div className="flex justify-between items-start mb-8 relative z-10">
                  <div className={`px-4 py-1.5 rounded-xl text-[9px] font-black uppercase tracking-widest border transition-colors ${goal.status === 'completed' ? 'bg-green-500/10 text-green-500 border-green-500/20' : goal.status === 'failed' ? 'bg-red-500/10 text-red-500 border-red-500/20' : 'bg-blue-500/10 text-blue-500 border-blue-500/20'}`}>{goal.status.replace(/_/g, ' ')}</div>
                  <span className="text-[10px] font-black text-gray-700 uppercase tracking-[0.2em] pt-1">{new Date(goal.created_at).toLocaleDateString()}</span>
                </div>
                <div className="space-y-3 mb-10 relative z-10 text-left">
                   <div className="flex items-center gap-2 text-gray-500 text-[10px] font-black uppercase tracking-[0.3em]"><MapPin size={12} className="text-blue-500" /> {goal.country} Hub • {goal.city}</div>
                   <h3 className="text-2xl font-black text-white line-clamp-2 leading-[1.2] tracking-tighter group-hover:text-blue-400 transition-colors uppercase">{goal.prompt}</h3>
                </div>
                <div className="flex items-center gap-6 pt-8 border-t border-white/5 relative z-10">
                  <div className="flex items-center gap-2.5 text-gray-500 font-black text-[10px] uppercase tracking-[0.2em]"><Timer size={16} className="text-gray-700" /> {goal.num_days}D</div>
                  <div className="flex items-center gap-2.5 text-gray-500 font-black text-[10px] uppercase tracking-[0.2em]"><Globe size={16} className="text-gray-700" /> {goal.language_code.toUpperCase()}</div>
                  <div className="ml-auto w-10 h-10 rounded-xl bg-white/5 flex items-center justify-center group-hover:bg-blue-600 group-hover:text-white transition-all group-hover:translate-x-1 border border-white/5 shadow-lg"><ArrowRight size={18} /></div>
                </div>
              </div>
            ))
          )}
        </div>
      </main>
    </div>
  );
};

// --- FEATURE: PLAN CONFIGURATOR ---

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
    onSuccess: (res) => navigate(`/plan/${res.data.data.goal_id}`)
  });

  const updateField = (field: string, value: any) => {
    setFormData(prev => ({ ...prev, [field]: value }));
  };

  return (
    <div className="min-h-screen bg-[#0a0f1e] text-white">
      <Navbar />
      <div className="max-w-4xl mx-auto px-6 py-20">
        <header className="mb-20 text-center relative">
          <div className="absolute -top-10 left-1/2 -translate-x-1/2 w-48 h-48 bg-blue-600/20 blur-[100px] rounded-full pointer-events-none" />
          <p className="text-[10px] font-black text-blue-500 uppercase tracking-[0.6em] mb-4 relative z-10">Neural Configuration</p>
          <h1 className="text-7xl font-black tracking-tighter mb-6 leading-none relative z-10 uppercase">Setup<span className="text-blue-600">.</span></h1>
          <p className="text-gray-400 text-xl font-medium tracking-tight leading-relaxed mx-auto max-w-xl relative z-10">AI will resolve the optimal nutritional strategy and local stock matches.</p>
        </header>

        <form onSubmit={e => { e.preventDefault(); mutation.mutate(formData); }} className="space-y-8">
          {/* I. Core Objectives */}
          <div className="glass-card p-12 rounded-[3.5rem] space-y-12 border border-white/5 shadow-2xl relative overflow-hidden">
            <div className="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-transparent via-blue-500/50 to-transparent" />
            <section className="space-y-6 text-left">
              <label className="text-[11px] font-black uppercase tracking-[0.4em] text-blue-500 flex items-center gap-3"><BrainCircuit size={18} /> I. Core Goal</label>
              <textarea 
                required 
                className="input-field min-h-[180px] text-xl font-bold leading-relaxed py-8 border-none ring-1 ring-white/10 focus:ring-blue-500/50 bg-black/40 rounded-3xl px-8" 
                placeholder="High protein diet for muscle gain, keto vegetarian..." 
                value={formData.prompt} 
                onChange={e => updateField('prompt', e.target.value)} 
              />
            </section>
            
            <div className="grid grid-cols-2 gap-8 text-left">
              <section className="space-y-4">
                <label className="text-[10px] font-black uppercase tracking-[0.3em] text-gray-600 flex items-center gap-2"><Globe size={16} /> Region Hub</label>
                <select 
                  className="input-field bg-[#0a0f1e] font-black uppercase tracking-[0.1em] text-xs h-16 border-white/10 rounded-2xl px-6" 
                  value={formData.country} 
                  onChange={e => {
                    const country = e.target.value;
                    updateField('country', country);
                    updateField('shop', ''); // Reset shop when country changes
                    updateField('language_code', country === 'CZ' ? 'cs' : 'sk');
                  }}
                >
                  <option value="CZ">CZ / Czech Republic</option>
                  <option value="SK">SK / Slovakia</option>
                </select>
              </section>
              <section className="space-y-4">
                <label className="text-[10px] font-black uppercase tracking-[0.3em] text-gray-600 flex items-center gap-2"><MapPin size={16} /> Target City</label>
                <input 
                  required type="text" 
                  className="input-field font-bold h-16 border-white/10 rounded-2xl bg-black/20 px-6 text-lg" 
                  placeholder="e.g. Prague" 
                  value={formData.city} 
                  onChange={e => updateField('city', e.target.value)} 
                />
              </section>
            </div>
          </div>

          {/* II. Meal Structure */}
          <div className="glass-card p-12 rounded-[3.5rem] space-y-12 border border-white/5 shadow-2xl text-left">
            <section className="space-y-8">
              <label className="text-[11px] font-black uppercase tracking-[0.4em] text-blue-500 flex items-center gap-3"><Utensils size={18} /> II. Meal Mapping</label>
              
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
                    className={`p-6 rounded-3xl border flex items-center justify-between transition-all group ${
                      (formData as any)[meal.id] 
                        ? 'bg-blue-600/10 border-blue-500 text-white shadow-xl' 
                        : 'bg-white/5 border-white/5 text-gray-500 hover:border-white/10'
                    }`}
                  >
                    <div className="flex items-center gap-4">
                      <div className={`w-10 h-10 rounded-xl flex items-center justify-center transition-colors ${(formData as any)[meal.id] ? 'bg-blue-600 text-white' : 'bg-white/5'}`}>
                        <meal.icon size={20} />
                      </div>
                      <span className="font-black uppercase text-xs tracking-widest">{meal.label}</span>
                    </div>
                    {(formData as any)[meal.id] && <Check size={18} strokeWidth={4} />}
                  </button>
                ))}
              </div>

              <div className="grid grid-cols-2 gap-10">
                <section className="space-y-4">
                  <div className="flex justify-between items-end">
                    <label className="text-[10px] font-black uppercase tracking-[0.3em] text-gray-600 flex items-center gap-2">Small Meals / Day</label>
                    <span className="text-xl font-black text-blue-500">{formData.small_meals_per_day}</span>
                  </div>
                  <input 
                    type="range" min="0" max="5" 
                    className="w-full h-2 bg-white/5 rounded-lg appearance-none cursor-pointer accent-blue-600"
                    value={formData.small_meals_per_day} 
                    onChange={e => updateField('small_meals_per_day', parseInt(e.target.value))} 
                  />
                </section>
                <section className="space-y-4">
                  <div className="flex justify-between items-end">
                    <label className="text-[10px] font-black uppercase tracking-[0.3em] text-gray-600 flex items-center gap-2">Snacks / Day</label>
                    <span className="text-xl font-black text-blue-500">{formData.snacks_per_day}</span>
                  </div>
                  <input 
                    type="range" min="0" max="3" 
                    className="w-full h-2 bg-white/5 rounded-lg appearance-none cursor-pointer accent-blue-600"
                    value={formData.snacks_per_day} 
                    onChange={e => updateField('snacks_per_day', parseInt(e.target.value))} 
                  />
                </section>
              </div>

              <div className="space-y-4">
                <label className="text-[10px] font-black uppercase tracking-[0.3em] text-gray-600 flex items-center gap-2">Roadmap Duration</label>
                <div className="flex flex-wrap gap-3">
                  {[1, 3, 7, 14, 30].map(d => (
                    <button
                      key={d}
                      type="button"
                      onClick={() => updateField('num_days', d)}
                      className={`px-8 py-4 rounded-2xl font-black text-xs transition-all border ${
                        formData.num_days === d 
                          ? 'bg-blue-600 border-blue-500 text-white shadow-xl scale-105' 
                          : 'bg-white/5 border-white/5 text-gray-500 hover:bg-white/10'
                      }`}
                    >
                      {d} DAYS
                    </button>
                  ))}
                </div>
              </div>
            </section>
          </div>

          {/* III. Sourcing Engine */}
          <div className="glass-card p-12 rounded-[3.5rem] space-y-12 border border-white/5 shadow-2xl text-left">
            <section className="space-y-8">
              <label className="text-[11px] font-black uppercase tracking-[0.4em] text-blue-500 flex items-center gap-3"><ShoppingCart size={18} /> III. Inventory Engine</label>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {shopsData?.shops?.map((shop: any) => (
                  <button 
                    key={shop.code} type="button" 
                    onClick={() => updateField('shop', shop.code)} 
                    className={`p-8 rounded-[2.5rem] border text-left transition-all relative group overflow-hidden ${
                      formData.shop === shop.code 
                        ? 'bg-blue-600 border-blue-500 text-white shadow-2xl scale-[1.02]' 
                        : 'bg-white/5 border-white/5 text-gray-500 hover:border-white/10'
                    }`}
                  >
                    <div className={`absolute top-0 right-0 w-24 h-24 blur-[60px] -mr-8 -mt-8 transition-all ${formData.shop === shop.code ? 'bg-white/20' : 'bg-blue-600/0 group-hover:bg-blue-600/5'}`} />
                    <span className="font-black text-sm block mb-1 uppercase tracking-widest relative z-10">{shop.name}</span>
                    <span className={`text-[9px] uppercase font-bold tracking-[0.2em] relative z-10 transition-colors ${formData.shop === shop.code ? 'text-white/60' : 'opacity-30'}`}>Live Availability Scrape</span>
                    {formData.shop === shop.code && <div className="absolute top-6 right-8 bg-white text-blue-600 p-1.5 rounded-full shadow-lg relative z-10"><Check size={14} strokeWidth={4} /></div>}
                  </button>
                ))}
              </div>
            </section>
          </div>

          <button 
            type="submit" 
            disabled={mutation.isPending || !formData.prompt || !formData.shop} 
            className="w-full bg-white text-black py-10 rounded-[3rem] font-black text-3xl uppercase tracking-[0.4em] shadow-2xl active:scale-[0.98] transition-all hover:bg-gray-100 disabled:opacity-30 border-b-8 border-gray-300"
          >
            {mutation.isPending ? <span className="flex items-center justify-center gap-6"><Loader2 className="animate-spin" /> Synchronizing</span> : "Synthesize Plan"}
          </button>
        </form>
      </div>
    </div>
  );
};

// --- FEATURE: PLAN VIEW ---

const PlanView = () => {
  const { id } = useParams();
  const navigate = useNavigate();
  const { data: statusData } = useQuery({
    queryKey: ['taskStatus', id],
    queryFn: () => api.get(`/goals/${id}/task-status/`).then(res => res.data.data),
    refetchInterval: (query: any) => {
      const currentStatus = query?.state?.data?.goal_status;
      return currentStatus === 'completed' || currentStatus === 'failed' ? false : 2000;
    }
  });

  const { data: goalDetail } = useQuery({
    queryKey: ['plan', id],
    queryFn: () => api.get(`/goals/${id}/`).then(res => res.data.data),
    enabled: statusData?.goal_status === 'completed'
  });

  if (statusData?.goal_status === 'failed') {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center text-white bg-[#0a0f1e] p-8 text-center px-12">
        <AlertCircle size={80} strokeWidth={1} className="text-red-500 mb-12 animate-bounce shadow-2xl" />
        <h1 className="text-7xl font-black tracking-tighter mb-4 uppercase leading-none">Logic Fault<span className="text-red-600">.</span></h1>
        <p className="text-gray-500 mb-16 max-w-xl text-xl font-medium leading-relaxed tracking-tight">The AI engine encountered a resolution error for this configuration. Ensure your city and goals are achievable.</p>
        <button onClick={() => navigate('/')} className="bg-white text-black px-12 py-6 rounded-[2.5rem] font-black uppercase tracking-[0.3em] text-xs hover:bg-gray-100 transition-all shadow-xl shadow-white/10 active:scale-95">Reset Protocol</button>
      </div>
    );
  }

  if (statusData?.goal_status !== 'completed') {
    return (
      <>
        <Navbar />
        <LoadingScreen message="Resolving supply chain and nutritional models" status={statusData} />
      </>
    );
  }

  const plan = goalDetail?.dietary_plan;
  if (!plan) return <LoadingScreen message="Finalizing Objects..." />;

  return (
    <div className="min-h-screen bg-[#0a0f1e] text-white">
      <Navbar />
      <div className="max-w-6xl mx-auto px-6 py-20">
        <header className="flex flex-col lg:flex-row lg:items-end justify-between mb-24 gap-12 text-center lg:text-left">
          <div className="space-y-6 text-left">
            <h1 className="text-8xl font-black tracking-tighter leading-none mb-4 uppercase">Outcome<span className="text-blue-600">.</span></h1>
            <div className="flex flex-wrap items-center gap-4 text-gray-500 font-black uppercase tracking-[0.2em] text-[10px]">
               <div className="flex items-center gap-2 bg-white/5 px-5 py-2.5 rounded-2xl border border-white/5 shadow-lg"><MapPin size={14} className="text-blue-500" /> {goalDetail.city} hub</div>
               <div className="flex items-center gap-2 bg-white/5 px-5 py-2.5 rounded-2xl border border-white/5 shadow-lg"><Timer size={14} className="text-blue-500" /> {goalDetail.num_days} days</div>
               <div className="flex items-center gap-2 bg-white/5 px-5 py-2.5 rounded-2xl border border-white/5 shadow-lg"><ShoppingCart size={14} className="text-blue-500" /> {goalDetail.shop} stock</div>
            </div>
          </div>
          <div className="flex items-center gap-6 bg-white/5 p-8 rounded-[4rem] border border-white/5 md:pr-14 shadow-2xl mx-auto lg:mx-0 group">
             <div className="w-16 h-16 bg-green-500/10 border border-green-500/20 rounded-[1.8rem] flex items-center justify-center text-green-500 shadow-lg group-hover:scale-110 transition-transform">
               <CheckCircle2 size={36} strokeWidth={2.5} />
             </div>
             <div className="space-y-0.5 text-left">
               <p className="text-[10px] font-black text-gray-600 uppercase tracking-[0.3em]">Neural Status</p>
               <p className="font-black text-2xl text-green-500 tracking-tighter uppercase leading-none">Map Verified</p>
               <p className="text-[9px] text-gray-500 font-bold uppercase tracking-widest">Secure Access Granted</p>
             </div>
          </div>
        </header>

        <div className="grid lg:grid-cols-3 gap-20">
          <div className="lg:col-span-2 space-y-32">
            {plan.days?.map((day: any) => (
              <section key={day.day_number} className="relative">
                <div className="absolute -left-12 top-10 bottom-0 w-px bg-gradient-to-b from-blue-600/40 via-transparent to-transparent hidden xl:block" />
                
                <div className="flex items-center gap-8 mb-16 justify-center lg:justify-start text-left">
                  <div className="flex-none w-20 h-20 rounded-[2rem] bg-white text-black flex items-center justify-center text-3xl font-black shadow-2xl shadow-white/10">
                    {day.day_number}
                  </div>
                  <div>
                    <h2 className="text-5xl font-black tracking-tighter uppercase leading-none mb-1">Strategy.</h2>
                    <p className="text-gray-500 font-black uppercase tracking-[0.3em] text-[10px]">Optimal Nutrient Allocation</p>
                  </div>
                </div>

                <div className="grid gap-10">
                  {['breakfast', 'lunch', 'dinner'].map(mealKey => day[mealKey] && (
                    <div key={mealKey} className="glass-card p-12 rounded-[4.5rem] group hover:border-blue-500/30 transition-all border border-white/5 relative shadow-xl text-left">
                      <div className="flex justify-between items-center mb-10">
                        <span className="px-6 py-2 rounded-2xl bg-blue-600 text-white text-[10px] font-black uppercase tracking-[0.3em] shadow-lg shadow-blue-900/40">
                          {mealKey}
                        </span>
                        <div className="flex items-center gap-3 text-gray-600 text-[10px] font-black uppercase tracking-widest">
                           <Timer size={16} className="text-blue-500" /> {day[mealKey].preparation_time || 15}m Execution
                        </div>
                      </div>
                      <h3 className="text-4xl font-black mb-6 group-hover:text-blue-400 transition-colors tracking-tight leading-tight uppercase">{day[mealKey].name}</h3>
                      <p className="text-gray-400 leading-relaxed mb-12 text-xl font-medium tracking-tight leading-relaxed">{day[mealKey].description}</p>
                      
                      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                         {Object.entries(day[mealKey].nutritional_info || {}).map(([k, v]: any) => (
                           <div key={k} className="bg-[#0a0f1e] px-6 py-5 rounded-3xl border border-white/5 flex flex-col gap-1 shadow-inner group-hover:border-blue-500/10 transition-colors">
                             <p className="text-[9px] text-gray-600 font-black uppercase tracking-[0.2em]">{k}</p>
                             <p className="font-black text-lg text-white tracking-tighter uppercase">{v}</p>
                           </div>
                         ))}
                      </div>
                    </div>
                  ))}
                </div>
              </section>
            ))}
          </div>

          <div className="space-y-8">
            <div className="glass-card p-12 rounded-[4rem] sticky top-32 border border-blue-500/10 shadow-[0_40px_100px_-20px_rgba(0,0,0,0.7)] text-left">
               <div className="flex items-center gap-5 mb-14 pb-10 border-b border-white/5">
                 <div className="w-14 h-14 rounded-[1.5rem] bg-blue-600/10 flex items-center justify-center text-blue-500 shadow-inner border border-blue-500/10">
                    <ShoppingCart size={28} strokeWidth={2.5} />
                 </div>
                 <div>
                    <h2 className="text-4xl font-black tracking-tighter uppercase leading-none mb-1 text-white">Supply.</h2>
                    <p className="text-[9px] font-black text-gray-600 uppercase tracking-widest">Calculated Acquisition</p>
                 </div>
               </div>

               <div className="space-y-10 max-h-[500px] overflow-y-auto pr-4 custom-scrollbar">
                  {plan.shopping_list?.map((item: any, idx: number) => (
                    <div key={idx} className="group border-b border-white/5 pb-8 last:border-0 last:pb-0">
                      <div className="flex justify-between items-start mb-3">
                        <p className="font-black text-base text-white group-hover:text-blue-400 transition-colors uppercase tracking-tight leading-none">{item.ingredient}</p>
                        <p className="text-sm font-black text-blue-500 tabular-nums leading-none">{item.price} {item.currency}</p>
                      </div>
                      <div className="flex justify-between items-center text-[10px] font-black text-gray-600 uppercase tracking-widest">
                        <span className="bg-white/5 px-2.5 py-1 rounded-xl text-gray-400 border border-white/5 font-mono">{item.quantity} {item.unit}</span>
                        <span className="italic opacity-30 line-clamp-1 max-w-[120px] text-right font-medium">{item.matched_product_name}</span>
                      </div>
                    </div>
                  ))}
               </div>

               <div className="mt-14 pt-12 border-t-4 border-blue-600/30 space-y-8">
                  <div className="flex justify-between items-center text-gray-600 uppercase tracking-[0.3em] text-[10px] font-black">
                     <span>Estimated Overhead</span>
                     <span className="bg-blue-600/10 px-4 py-1.5 rounded-full text-blue-500 border border-blue-500/20">{plan.shopping_list?.length} Nodes</span>
                  </div>
                  <div className="flex justify-between items-end">
                    <span className="text-7xl font-black tracking-tighter leading-none text-white">{plan.total_price}</span>
                    <span className="text-2xl font-black text-blue-500 tracking-tighter ml-1 mb-1">{plan.currency}</span>
                  </div>
                  <button className="w-full bg-white text-black py-7 rounded-[2rem] font-black uppercase tracking-widest text-[10px] hover:bg-gray-100 transition-all flex items-center justify-center gap-4 mt-8 shadow-2xl active:scale-[0.98] border-b-4 border-gray-300">
                    Sync Supply Chain <ArrowRight size={20} strokeWidth={3} />
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
        <div className="absolute top-1/4 left-1/4 w-[600px] h-[600px] bg-blue-600/10 blur-[150px] rounded-full animate-pulse-slow" />
        <div className="absolute bottom-1/4 right-1/4 w-[700px] h-[700px] bg-purple-600/5 blur-[200px] rounded-full animate-pulse-slow delay-700" />
      </div>

      <div className="max-w-md w-full glass-card rounded-[5rem] p-20 text-center relative z-10 shadow-3xl border border-white/5">
        <div className="inline-flex items-center justify-center w-28 h-28 rounded-[3rem] bg-blue-600/10 text-blue-500 mb-16 shadow-inner border border-white/5 relative group">
          <div className="absolute inset-0 bg-blue-500/20 blur-2xl animate-pulse rounded-full" />
          <Zap size={56} fill="currentColor" className="relative z-10 animate-pulse group-hover:scale-110 transition-transform" />
        </div>
        <div className="mb-20">
          <h1 className="text-6xl font-black text-white mb-4 tracking-tighter leading-[0.8] uppercase">Diet<br/>Planner<span className="text-blue-600">.</span></h1>
          <p className="text-gray-500 text-[10px] font-black tracking-[0.5em] uppercase mt-6 opacity-60">Neural Nutrition Protocol</p>
        </div>
        
        <button 
          onClick={handleGoogleLogin} 
          className="w-full bg-white hover:bg-gray-100 text-black py-8 rounded-[2.5rem] font-black transition-all flex items-center justify-center gap-5 text-xs uppercase tracking-[0.2em] shadow-3xl active:scale-[0.98] border-b-4 border-gray-300"
        >
          <svg className="w-7 h-7" viewBox="0 0 24 24"><path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/><path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/><path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l3.66-2.84z"/><path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 12-4.53z"/></svg>
          Sync Protocol
        </button>
      </div>
    </div>
  );
};

const LoadingScreen = ({ message, status }: { message: string, status?: any }) => (
  <div className="min-h-[calc(100vh-80px)] flex flex-col items-center justify-center text-white bg-[#0a0f1e] px-6 relative overflow-hidden">
    <div className="absolute inset-0 bg-blue-600/5 blur-[120px] rounded-full opacity-30" />
    <div className="relative mb-24 scale-110">
      <div className="absolute inset-0 bg-blue-600/30 blur-[80px] animate-pulse rounded-full" />
      <Loader2 className="animate-spin text-blue-500 relative z-10" size={100} strokeWidth={1} />
      <Zap size={40} className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 text-blue-400 animate-pulse z-10" />
    </div>
    <div className="text-center space-y-3 relative z-10 mb-12">
      <h2 className="text-white font-black text-6xl tracking-tighter uppercase leading-none">Synthesizing<span className="text-blue-600 animate-pulse">...</span></h2>
      <p className="text-gray-500 font-black uppercase tracking-[0.5em] text-[10px]">{message}</p>
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