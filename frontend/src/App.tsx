// File: frontend/src/App.tsx | Route: / (and sub-routes)
import { useState, useEffect, useMemo } from 'react';
import { BrowserRouter, Routes, Route, Navigate, useNavigate, useSearchParams, useParams } from 'react-router-dom';
import { QueryClient, QueryClientProvider, useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { 
  Loader2, Zap, AlertCircle, Plus, Utensils, ShoppingCart, 
  Timer, Globe, MapPin, ChevronRight, Check, Trash2, 
  ChevronLeft, LayoutDashboard, LogOut, ArrowRight
} from 'lucide-react';
import axios from 'axios';

/**
 * ARCHITECTURAL PLAN:
 * 1. Auth: Handle Google OAuth redirection and JWT sync.
 * 2. Dashboard: List existing DietaryGoals from /api/goals/list/.
 * 3. Create: Dynamic form fetching shops based on country (/api/shops/).
 * 4. Detail: Poll /api/goals/:id/task-status/ for Celery completion, then render.
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

// Global API Interceptor
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

// --- HELPER COMPONENTS ---

const LoadingScreen = ({ message }: { message: string }) => (
  <div className="min-h-screen flex flex-col items-center justify-center text-white bg-[#0a0f1e]">
    <div className="relative mb-8">
      <Loader2 className="animate-spin text-blue-500" size={64} />
      <Zap size={24} className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 text-blue-400 animate-pulse" />
    </div>
    <p className="text-gray-500 font-black uppercase tracking-[0.3em] text-[10px]">{message}</p>
  </div>
);

// --- FEATURE: DASHBOARD ---

const Dashboard = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  
  const { data: goals, isLoading } = useQuery({
    queryKey: ['goals'],
    queryFn: () => api.get('/goals/list/').then(res => res.data.data)
  });

  const handleLogout = () => {
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    navigate('/login');
  };

  if (isLoading) return <LoadingScreen message="Accessing Secure Vault..." />;

  return (
    <div className="min-h-screen bg-[#0a0f1e]">
      <nav className="border-b border-white/5 bg-[#0a0f1e]/80 backdrop-blur-md sticky top-0 z-10">
        <div className="max-w-7xl mx-auto px-6 h-20 flex justify-between items-center">
          <div className="flex items-center gap-2">
            <Zap size={24} className="text-blue-500" fill="currentColor" />
            <span className="text-xl font-black tracking-tighter">DietPlanner.</span>
          </div>
          <div className="flex items-center gap-6">
             <button onClick={handleLogout} className="text-gray-500 hover:text-white transition-colors">
               <LogOut size={20} />
             </button>
             <button 
                onClick={() => navigate('/create')}
                className="bg-blue-600 hover:bg-blue-500 text-white px-6 py-2.5 rounded-xl font-bold flex items-center gap-2 transition-all"
             >
               <Plus size={18} /> New Plan
             </button>
          </div>
        </div>
      </nav>

      <main className="max-w-7xl mx-auto px-6 py-12">
        <div className="mb-12">
          <h1 className="text-4xl font-black text-white mb-2">Workspace.</h1>
          <p className="text-gray-400">Track and manage your AI-tailored dietary strategies.</p>
        </div>

        <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
          {goals?.length === 0 ? (
            <div className="col-span-full py-32 text-center glass-card rounded-[3rem] border-dashed border-white/10">
              <Utensils size={48} className="mx-auto mb-6 text-gray-700" />
              <h3 className="text-xl font-bold text-white mb-2">No Plans Generated</h3>
              <p className="text-gray-500 mb-8 max-w-xs mx-auto">Start by describing your goals and let the AI map your nutrition.</p>
              <button onClick={() => navigate('/create')} className="btn-primary inline-flex">Create Plan <Plus size={18}/></button>
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
                    {goal.status.replace('_', ' ')}
                  </div>
                  <span className="text-[10px] font-bold text-gray-600 uppercase tracking-tighter">
                    {new Date(goal.created_at).toLocaleDateString()}
                  </span>
                </div>

                <div className="space-y-1 mb-6">
                   <div className="flex items-center gap-1.5 text-gray-500 text-[10px] font-black uppercase tracking-widest">
                     <MapPin size={10} /> {goal.country} • {goal.city}
                   </div>
                   <h3 className="text-xl font-bold text-white line-clamp-1">{goal.prompt}</h3>
                </div>

                <div className="flex items-center gap-4 pt-6 border-t border-white/5">
                  <div className="flex items-center gap-1.5 text-gray-400 font-bold text-xs">
                    <Timer size={14} className="text-blue-500" /> {goal.num_days} Days
                  </div>
                  <div className="flex items-center gap-1.5 text-gray-400 font-bold text-xs">
                    <Globe size={14} className="text-blue-500" /> {goal.language_code.toUpperCase()}
                  </div>
                  <ArrowRight size={16} className="ml-auto text-gray-700 group-hover:text-blue-500 transition-colors" />
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
      const goalId = res.data.data.goal_id;
      navigate(`/plan/${goalId}`);
    }
  });

  return (
    <div className="min-h-screen bg-[#0a0f1e] text-white overflow-x-hidden">
      <div className="max-w-3xl mx-auto px-6 py-12">
        <button onClick={() => navigate('/')} className="mb-8 flex items-center gap-2 text-gray-500 hover:text-white transition-colors font-bold text-sm">
          <ChevronLeft size={20} /> Back to Dashboard
        </button>
        
        <header className="mb-12">
          <h1 className="text-5xl font-black tracking-tighter mb-4">New Roadmap.</h1>
          <p className="text-gray-400 text-lg">Define your goals. We'll handle the logistics.</p>
        </header>

        <form onSubmit={e => { e.preventDefault(); mutation.mutate(formData); }} className="space-y-6">
          <div className="glass-card p-10 rounded-[3rem] space-y-8">
            <section className="space-y-4">
              <label className="text-xs font-black uppercase tracking-widest text-blue-500">1. Describe your dietary goal</label>
              <textarea 
                required
                className="input-field min-h-[160px] text-lg"
                placeholder="Example: I am training for a marathon and need 3000kcal/day with high complex carbs. I live in Prague..."
                value={formData.prompt}
                onChange={e => setFormData({...formData, prompt: e.target.value})}
              />
            </section>

            <div className="grid grid-cols-2 gap-6">
              <section className="space-y-2">
                <label className="text-xs font-black uppercase tracking-widest text-blue-500">Country</label>
                <select 
                  className="input-field bg-[#0a0f1e]"
                  value={formData.country}
                  onChange={e => setFormData({...formData, country: e.target.value, shop: '', language_code: e.target.value === 'CZ' ? 'cs' : 'sk'})}
                >
                  <option value="CZ">Czech Republic</option>
                  <option value="SK">Slovakia</option>
                </select>
              </section>
              <section className="space-y-2">
                <label className="text-xs font-black uppercase tracking-widest text-blue-500">City</label>
                <input 
                  required
                  type="text" className="input-field" placeholder="e.g. Prague"
                  value={formData.city}
                  onChange={e => setFormData({...formData, city: e.target.value})}
                />
              </section>
            </div>

            <section className="space-y-4">
              <label className="text-xs font-black uppercase tracking-widest text-blue-500">2. Choose Sourcing Engine</label>
              <div className="grid grid-cols-2 gap-4">
                {shopsData?.shops?.map((shop: any) => (
                  <button
                    key={shop.code} type="button"
                    onClick={() => setFormData({...formData, shop: shop.code})}
                    className={`p-6 rounded-3xl border text-left transition-all relative ${
                      formData.shop === shop.code 
                      ? 'bg-blue-600/10 border-blue-500 text-white ring-1 ring-blue-500' 
                      : 'bg-white/5 border-white/5 text-gray-500 hover:border-white/20'
                    }`}
                  >
                    <span className="font-black text-sm block mb-1">{shop.name}</span>
                    <span className="text-[10px] uppercase opacity-60 tracking-widest">Real-time Scrape</span>
                    {formData.shop === shop.code && <div className="absolute top-4 right-4 bg-blue-500 p-1 rounded-full"><Check size={12} className="text-white"/></div>}
                  </button>
                ))}
              </div>
            </section>
          </div>

          <div className="glass-card p-10 rounded-[3rem] space-y-8">
             <section className="space-y-4">
               <label className="text-xs font-black uppercase tracking-widest text-blue-500">3. Meal Structure</label>
               <div className="flex gap-8">
                 {['breakfast', 'lunch', 'dinner'].map((meal: any) => (
                   <label key={meal} className="flex items-center gap-3 cursor-pointer group">
                     <div className={`w-6 h-6 rounded-lg border-2 flex items-center justify-center transition-all ${
                       (formData as any)[meal] ? 'bg-blue-600 border-blue-600' : 'border-white/10 bg-white/5 group-hover:border-white/20'
                     }`}>
                        {(formData as any)[meal] && <Check size={14} />}
                     </div>
                     <input 
                       type="checkbox" className="hidden"
                       checked={(formData as any)[meal]}
                       onChange={e => setFormData({...formData, [meal]: e.target.checked})}
                     />
                     <span className={`text-sm font-black uppercase tracking-tighter ${ (formData as any)[meal] ? 'text-white' : 'text-gray-600'}`}>{meal}</span>
                   </label>
                 ))}
               </div>
             </section>

             <div className="grid grid-cols-2 gap-8">
                <section className="space-y-2">
                   <label className="text-[10px] font-black uppercase tracking-widest text-gray-500">Small Meals / Day</label>
                   <div className="flex items-center gap-4">
                      <input 
                        type="range" min="0" max="5" step="1"
                        className="flex-1 accent-blue-600"
                        value={formData.small_meals_per_day}
                        onChange={e => setFormData({...formData, small_meals_per_day: parseInt(e.target.value)})}
                      />
                      <span className="w-8 text-center font-black text-blue-500 text-xl">{formData.small_meals_per_day}</span>
                   </div>
                </section>
                <section className="space-y-2">
                   <label className="text-[10px] font-black uppercase tracking-widest text-gray-500">Plan Duration (Days)</label>
                   <select 
                     className="input-field text-sm font-bold"
                     value={formData.num_days}
                     onChange={e => setFormData({...formData, num_days: parseInt(e.target.value)})}
                   >
                     {[1,3,7,14,30].map(d => <option key={d} value={d}>{d} Days</option>)}
                   </select>
                </section>
             </div>
          </div>

          <button 
            type="submit" 
            disabled={mutation.isPending || !formData.prompt}
            className="w-full btn-primary py-8 text-xl font-black tracking-tighter shadow-blue-500/20"
          >
            {mutation.isPending ? (
              <><Loader2 className="animate-spin" /> Synchronizing AI...</>
            ) : (
              <>Initiate Generation <Plus size={24} className="ml-2" /></>
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
  
  // Polling status
  const { data: statusData } = useQuery({
    queryKey: ['taskStatus', id],
    queryFn: () => api.get(`/goals/${id}/task-status/`).then(res => res.data.data),
    refetchInterval: (query: any) => {
      const currentStatus = query?.state?.data?.goal_status;
      return currentStatus === 'completed' || currentStatus === 'failed' ? false : 3000;
    }
  });

  // Fetch data on complete
  const { data: goalDetail } = useQuery({
    queryKey: ['plan', id],
    queryFn: () => api.get(`/goals/${id}/`).then(res => res.data.data),
    enabled: statusData?.goal_status === 'completed'
  });

  if (statusData?.goal_status === 'failed') {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center text-white bg-[#0a0f1e] p-8">
        <AlertCircle size={64} className="text-red-500 mb-8" />
        <h1 className="text-3xl font-black mb-4">Processing Error.</h1>
        <p className="text-gray-500 mb-12 max-w-md text-center">The AI model was unable to parse requirements or shop data for this specific configuration.</p>
        <button onClick={() => navigate('/')} className="btn-primary">Return to Dashboard</button>
      </div>
    );
  }

  if (statusData?.goal_status !== 'completed') {
    const step = statusData?.goal_status?.replace(/_/g, ' ') || 'initializing';
    return <LoadingScreen message={`AI Roadmap Generation: ${step}...`} />;
  }

  const plan = goalDetail?.dietary_plan;
  if (!plan) return <LoadingScreen message="Reconstructing plan objects..." />;

  return (
    <div className="min-h-screen bg-[#0a0f1e] text-white">
      <div className="max-w-6xl mx-auto px-6 py-12">
        <header className="flex flex-col md:flex-row md:items-end justify-between mb-16 gap-6">
          <div className="space-y-4">
            <button onClick={() => navigate('/')} className="flex items-center gap-2 text-gray-500 hover:text-white transition-colors font-bold text-xs uppercase tracking-widest">
              <ChevronLeft size={16} /> All Roadmaps
            </button>
            <h1 className="text-6xl font-black tracking-tighter">Plan Outcome.</h1>
          </div>
          <div className="flex items-center gap-4">
             <div className="text-right">
               <p className="text-[10px] font-black text-gray-600 uppercase tracking-[0.3em] mb-1">Generated Plan ID</p>
               <p className="font-mono text-xs text-blue-500">{id}</p>
             </div>
             <div className="w-12 h-12 bg-green-500/10 border border-green-500/20 rounded-2xl flex items-center justify-center text-green-500 shadow-lg shadow-green-900/10">
               <Check size={24} />
             </div>
          </div>
        </header>

        <div className="grid lg:grid-cols-3 gap-12">
          {/* Main Meal Content */}
          <div className="lg:col-span-2 space-y-12">
            {plan.days?.map((day: any) => (
              <section key={day.day_number} className="relative">
                <div className="absolute -left-12 top-0 bottom-0 w-px bg-gradient-to-b from-blue-500/50 via-transparent to-transparent hidden xl:block" />
                
                <div className="flex items-center gap-4 mb-8">
                  <span className="flex-none w-14 h-14 rounded-2xl bg-blue-600 flex items-center justify-center text-xl font-black shadow-xl shadow-blue-900/20">
                    {day.day_number}
                  </span>
                  <h2 className="text-3xl font-black tracking-tight">Day Strategy</h2>
                </div>

                <div className="grid gap-6">
                  {['breakfast', 'lunch', 'dinner'].map(mealKey => day[mealKey] && (
                    <div key={mealKey} className="glass-card p-10 rounded-[3rem] group hover:border-white/10 transition-all border border-white/5">
                      <div className="flex justify-between items-start mb-4">
                        <span className="text-[10px] font-black uppercase tracking-[0.2em] text-blue-500">{mealKey}</span>
                        <div className="flex items-center gap-2 text-gray-600 text-xs font-bold">
                           <Timer size={14} /> {day[mealKey].preparation_time || 15}m
                        </div>
                      </div>
                      <h3 className="text-2xl font-bold mb-4 group-hover:text-blue-400 transition-colors">{day[mealKey].name}</h3>
                      <p className="text-gray-400 leading-relaxed mb-8">{day[mealKey].description}</p>
                      
                      <div className="space-y-4">
                        <p className="text-[10px] font-black uppercase tracking-widest text-gray-600">Nutritional Blueprint</p>
                        <div className="flex gap-6">
                           {Object.entries(day[mealKey].nutritional_info || {}).map(([k, v]: any) => (
                             <div key={k} className="bg-white/5 px-4 py-2 rounded-xl border border-white/5">
                               <p className="text-[10px] text-gray-500 font-bold uppercase">{k}</p>
                               <p className="font-black text-sm">{v}</p>
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

          {/* Sidebar: Shopping List */}
          <div className="space-y-8">
            <div className="glass-card p-8 rounded-[3rem] sticky top-28 border border-blue-500/20 shadow-2xl shadow-blue-950/20">
               <div className="flex items-center gap-3 mb-10 pb-6 border-b border-white/5">
                 <div className="w-10 h-10 rounded-xl bg-blue-600/20 flex items-center justify-center text-blue-500">
                    <ShoppingCart size={20} />
                 </div>
                 <h2 className="text-2xl font-black tracking-tight">Supply List</h2>
               </div>

               <div className="space-y-6 max-h-[500px] overflow-y-auto pr-2 custom-scrollbar">
                  {plan.shopping_list?.map((item: any, idx: number) => (
                    <div key={idx} className="group border-b border-white/5 pb-4 last:border-0">
                      <div className="flex justify-between items-start mb-1">
                        <p className="font-black text-sm text-white group-hover:text-blue-400 transition-colors capitalize">{item.ingredient}</p>
                        <p className="text-xs font-black text-blue-500">{item.price} {item.currency}</p>
                      </div>
                      <div className="flex justify-between items-center text-[10px] font-bold text-gray-500 uppercase tracking-tighter">
                        <span>{item.quantity} {item.unit}</span>
                        <span className="italic opacity-40 line-clamp-1 max-w-[120px]">{item.matched_product_name}</span>
                      </div>
                    </div>
                  ))}
               </div>

               <div className="mt-10 pt-8 border-t-2 border-white/5 space-y-4">
                  <div className="flex justify-between items-center text-gray-500 uppercase tracking-widest text-[10px] font-black">
                     <span>Estimated Total</span>
                     <span className="bg-blue-600/10 px-2 py-1 rounded text-blue-500">{plan.shopping_list?.length} Items</span>
                  </div>
                  <div className="flex justify-between items-baseline">
                    <span className="text-4xl font-black tracking-tighter">{plan.total_price}</span>
                    <span className="text-xl font-black text-blue-500 ml-1">{plan.currency}</span>
                  </div>
                  <button className="w-full bg-white text-black py-4 rounded-2xl font-black uppercase tracking-widest text-xs hover:bg-gray-200 transition-all mt-4 flex items-center justify-center gap-2">
                    Sync to Mobile <Globe size={14} />
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
  const handleGoogleLogin = () => {
    console.log("[AUTH] Redirecting to authoritative backend initiator...");
    window.location.href = '/api/auth/google/login/';
  };

  return (
    <div className="min-h-screen flex items-center justify-center p-6 bg-[#0a0f1e] overflow-hidden">
      <div className="absolute top-0 left-0 w-full h-full pointer-events-none opacity-50">
        <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-blue-600/20 blur-[100px] rounded-full animate-pulse-slow" />
        <div className="absolute bottom-1/4 right-1/4 w-96 h-96 bg-purple-600/10 blur-[120px] rounded-full animate-pulse-slow delay-700" />
      </div>

      <div className="max-w-md w-full glass-card rounded-[4rem] p-16 text-center relative z-10 shadow-2xl border border-white/5">
        <div className="inline-flex items-center justify-center w-24 h-24 rounded-[2.5rem] bg-blue-600/10 text-blue-500 mb-12 shadow-inner border border-white/5">
          <Zap size={48} fill="currentColor" className="animate-pulse" />
        </div>
        <div className="mb-12">
          <h1 className="text-6xl font-black text-white mb-4 tracking-tighter leading-none">DietPlanner.</h1>
          <p className="text-gray-400 text-lg font-medium tracking-tight">Professional Grade AI Nutrition.</p>
        </div>
        
        <button 
          onClick={handleGoogleLogin} 
          className="w-full bg-white hover:bg-gray-100 text-black py-6 rounded-3xl font-black transition-all flex items-center justify-center gap-4 text-sm uppercase tracking-widest shadow-xl shadow-white/5 active:scale-[0.98]"
        >
          <svg className="w-6 h-6" viewBox="0 0 24 24"><path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/><path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/><path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l3.66-2.84z"/><path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 12-4.53z"/></svg>
          Continue with Google
        </button>
        
        <div className="mt-12 flex items-center justify-center gap-6">
           <div className="text-center">
             <p className="text-[10px] font-black text-gray-600 uppercase tracking-widest mb-1">Scale</p>
             <p className="text-xs font-bold text-gray-400">100k+ Users</p>
           </div>
           <div className="w-px h-8 bg-white/5" />
           <div className="text-center">
             <p className="text-[10px] font-black text-gray-600 uppercase tracking-widest mb-1">Engine</p>
             <p className="text-xs font-bold text-gray-400">Gemini 2.0</p>
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

  return <LoadingScreen message="Establishing Encrypted Session..." />;
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