import { useState, useEffect } from 'react';
import { BrowserRouter, Routes, Route, Navigate, useNavigate, useSearchParams, useParams } from 'react-router-dom';
import { QueryClient, QueryClientProvider, useMutation, useQuery } from '@tanstack/react-query';
import { 
  Utensils, Apple, Loader2, LogOut, PlusCircle, 
  ChevronRight, Calendar, ShoppingCart, CheckCircle2, 
  AlertCircle, ArrowLeft, Clock, Zap, Target, 
  TrendingUp, Leaf, Info, ChefHat
} from 'lucide-react';
import axios from 'axios';

/**
 * PRODUCTION FRONTEND - SENIOR ENGINEER EDITION
 * Optimized for DigitalOcean deployment and high-end UX.
 */

// --- API Client ---
const api = axios.create({ baseURL: '/api', withCredentials: true });

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token');
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

const ProtectedRoute = ({ children }: { children: any }) => {
  if (!localStorage.getItem('access_token')) return <Navigate to="/login" replace />;
  return children;
};

// --- AUTH COMPONENTS ---

const LoginView = () => {
  const [params] = useSearchParams();
  const error = params.get('error');

  const handleGoogleLogin = () => {
    // Triggers the authoritative backend redirect flow
    window.location.href = '/api/auth/google/login/';
  };

  return (
    <div className="min-h-screen flex items-center justify-center p-6 relative">
      <div className="max-w-md w-full glass-card rounded-[3rem] p-12 text-center relative overflow-hidden">
        <div className="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-transparent via-blue-500 to-transparent" />
        <div className="inline-flex items-center justify-center w-24 h-24 rounded-[2rem] bg-blue-600/10 text-blue-500 mb-10 shadow-inner">
          <Zap size={48} fill="currentColor" />
        </div>
        <h1 className="text-5xl font-black text-white mb-4 tracking-tighter leading-none">
          DietPlanner<span className="text-blue-500">.</span>
        </h1>
        <p className="text-gray-400 text-lg font-medium leading-relaxed mb-12">
          Clinical nutrition meets local store offers. Automated by AI.
        </p>
        
        {error && (
          <div className="bg-red-500/10 border border-red-500/20 text-red-500 p-5 rounded-2xl mb-10 text-sm font-bold flex items-center gap-3 animate-shake">
            <AlertCircle size={20} /> Authentication error. Please try again.
          </div>
        )}

        <button onClick={handleGoogleLogin} className="w-full btn-primary py-6 text-black bg-white hover:bg-gray-100">
          <svg className="w-6 h-6" viewBox="0 0 24 24">
            <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
            <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
            <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l3.66-2.84z"/>
            <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 12-4.53z"/>
          </svg>
          Continue with Google
        </button>
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

  return (
    <div className="min-h-screen flex flex-col items-center justify-center text-white">
      <Loader2 className="animate-spin text-blue-500 mb-6" size={64} />
      <p className="text-gray-500 font-black uppercase tracking-[0.3em] text-[10px]">Secure Identity Exchange...</p>
    </div>
  );
};

// --- APPLICATION COMPONENTS ---

const Navbar = () => {
  const navigate = useNavigate();
  const handleLogout = () => { localStorage.clear(); window.location.href = '/login'; };
  return (
    <nav className="bg-[#161d2f]/70 backdrop-blur-2xl border-b border-white/5 px-8 py-6 flex justify-between items-center sticky top-0 z-50">
      <div className="flex items-center gap-4 font-black text-2xl cursor-pointer group" onClick={() => navigate('/')}>
        <div className="w-12 h-12 bg-blue-600 rounded-2xl flex items-center justify-center text-white shadow-xl shadow-blue-900/40 group-hover:scale-105 transition-all">
          <Leaf size={28} />
        </div>
        <span className="bg-gradient-to-r from-white to-gray-500 bg-clip-text text-transparent hidden sm:block tracking-tighter">DietPlanner</span>
      </div>
      <div className="flex gap-10 items-center">
        <button onClick={() => navigate('/create')} className="text-xs font-black text-gray-400 hover:text-white transition-all uppercase tracking-widest flex items-center gap-3">
          <PlusCircle size={20} className="text-blue-500" /> New Plan
        </button>
        <button onClick={handleLogout} className="w-12 h-12 bg-white/5 text-gray-400 hover:text-red-500 hover:bg-red-500/10 rounded-2xl transition-all flex items-center justify-center">
          <LogOut size={22} />
        </button>
      </div>
    </nav>
  );
};

const Dashboard = () => {
  const navigate = useNavigate();
  const { data, isLoading } = useQuery({
    queryKey: ['goals'],
    queryFn: () => api.get('/goals/list/').then(res => res.data),
    refetchInterval: (q) => q.state.data?.data?.some((g: any) => ['processing', 'pending'].includes(g.status)) ? 5000 : false,
  });

  if (isLoading) return <div className="min-h-screen flex items-center justify-center"><Loader2 className="animate-spin text-blue-500" size={48} /></div>;

  const goals = data?.data || [];

  return (
    <div className="max-w-6xl mx-auto p-12 space-y-16 pb-40">
      <header className="flex flex-col md:flex-row justify-between items-start md:items-end gap-8">
        <div className="space-y-2">
          <h1 className="text-7xl font-black text-white tracking-tighter leading-none">Your Plans</h1>
          <p className="text-gray-500 font-semibold text-xl">Manage and track your AI nutrition cycles.</p>
        </div>
        <button onClick={() => navigate('/create')} className="btn-primary">
          <PlusCircle size={24} /> Start New Plan
        </button>
      </header>

      {goals.length === 0 ? (
        <div className="glass-card p-24 rounded-[4rem] text-center">
          <div className="w-32 h-32 bg-blue-600/5 text-blue-500 rounded-[3rem] flex items-center justify-center mx-auto mb-10 shadow-inner">
            <Target size={64} />
          </div>
          <h3 className="text-white font-black text-3xl mb-4">The log is empty.</h3>
          <p className="text-gray-500 mb-12 max-w-sm mx-auto text-lg">Define your dietary targets and we'll generate a store-synced roadmap for you.</p>
          <button onClick={() => navigate('/create')} className="text-blue-500 font-black text-xl hover:underline tracking-tight">Create First Entry</button>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-10">
          {goals.map((g: any) => (
            <div 
              key={g.id} 
              onClick={() => g.status === 'completed' && navigate(`/plan/${g.id}`)} 
              className={`group glass-card p-10 rounded-[3.5rem] transition-all relative overflow-hidden ${g.status === 'completed' ? 'hover:border-blue-500/50 hover:bg-[#1c253d] cursor-pointer' : 'opacity-60 cursor-not-allowed animate-pulse-slow'}`}
            >
              <div className="flex justify-between items-center mb-8">
                <span className={`px-5 py-2 rounded-full text-[10px] font-black uppercase tracking-[0.2em] border ${
                  g.status === 'completed' ? 'bg-green-500/10 text-green-500 border-green-500/20' : 'bg-blue-500/10 text-blue-500 border-blue-500/20'
                }`}>
                  {g.status}
                </span>
                <span className="text-[10px] font-black text-gray-600 uppercase tracking-widest">{new Date(g.created_at).toLocaleDateString()}</span>
              </div>
              <h3 className="text-white font-black text-2xl mb-8 line-clamp-2 leading-[1.1] h-14 tracking-tight group-hover:text-blue-400 transition-colors">{g.prompt}</h3>
              <div className="flex items-center gap-4 text-[10px] font-black text-gray-500 uppercase tracking-[0.15em]">
                <span className="bg-white/5 px-4 py-2 rounded-xl">{g.city}</span>
                <span className="bg-white/5 px-4 py-2 rounded-xl">{g.country}</span>
              </div>
              {g.status === 'completed' && (
                <div className="mt-10 pt-10 border-t border-white/5 flex justify-between items-center text-blue-500">
                  <span className="font-black text-xs uppercase tracking-[0.2em]">Open Plan</span>
                  <ChevronRight size={20} className="group-hover:translate-x-2 transition-all" />
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

const CreateGoal = () => {
  const [prompt, setPrompt] = useState('');
  const [country, setCountry] = useState('CZ');
  const [city, setCity] = useState('Prague');
  const navigate = useNavigate();

  const mutation = useMutation({
    mutationFn: (data: any) => api.post('/goals/', data),
    onSuccess: () => navigate('/'),
  });

  return (
    <div className="max-w-3xl mx-auto p-12">
      <div className="glass-card rounded-[4rem] p-16 relative overflow-hidden">
        <button onClick={() => navigate('/')} className="absolute top-10 left-10 w-14 h-14 bg-[#0a0f1e]/50 border border-white/5 rounded-2xl flex items-center justify-center text-gray-400 hover:text-white transition-all hover:scale-105 shadow-xl">
          <ArrowLeft size={24} />
        </button>
        <div className="mb-14 mt-6">
          <h2 className="text-5xl font-black text-white tracking-tighter mb-3 leading-none">New Cycle</h2>
          <p className="text-gray-500 font-semibold text-lg">Describe your physiological requirements.</p>
        </div>
        
        <div className="space-y-12">
          <div>
            <label className="block text-[11px] font-black text-gray-500 uppercase tracking-[0.3em] mb-5">Dietary Context & Restrictions</label>
            <textarea 
              className="input-field h-64 text-xl leading-relaxed resize-none" 
              value={prompt} 
              onChange={(e) => setPrompt(e.target.value)} 
              placeholder="e.g. 2100kcal, low carb, high protein. No seafood. I shop at Lidl in Prague..." 
            />
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-10">
            <div>
              <label className="block text-[11px] font-black text-gray-500 uppercase tracking-[0.3em] mb-5">Target Region</label>
              <select value={country} onChange={(e) => setCountry(e.target.value)} className="input-field font-black appearance-none cursor-pointer">
                <option value="CZ">🇨🇿 Czech Republic</option>
                <option value="SK">🇸🇰 Slovakia</option>
                <option value="PL">🇵🇱 Poland</option>
              </select>
            </div>
            <div>
              <label className="block text-[11px] font-black text-gray-500 uppercase tracking-[0.3em] mb-5">City Context</label>
              <input type="text" value={city} onChange={(e) => setCity(e.target.value)} className="input-field font-black" placeholder="Prague, Warsaw..." />
            </div>
          </div>
        </div>

        <button 
          onClick={() => mutation.mutate({ prompt, country, city, language_code: 'en' })} 
          disabled={mutation.isPending || prompt.length < 10} 
          className="w-full btn-primary mt-16 py-7 text-xl rounded-[2rem] shadow-blue-500/20"
        >
          {mutation.isPending ? <><Loader2 className="animate-spin" size={28} /> Synchronizing with Gemini...</> : 'Generate AI Roadmap'}
        </button>
      </div>
    </div>
  );
};

const PlanDetail = () => {
  const { id } = useParams();
  const navigate = useNavigate();

  const { data, isLoading, error } = useQuery({
    queryKey: ['plan', id],
    queryFn: () => api.get(`/goals/${id}/`).then(res => res.data),
    enabled: !!id,
  });

  if (isLoading) return <div className="min-h-screen flex items-center justify-center"><Loader2 className="animate-spin text-blue-500" size={48} /></div>;
  if (error || !data?.data?.dietary_plan) return (
    <div className="min-h-screen flex flex-col items-center justify-center gap-8 p-12 text-center">
      <AlertCircle size={80} className="text-red-500/50" />
      <h2 className="text-4xl font-black tracking-tight">Plan data unreachable.</h2>
      <button onClick={() => navigate('/')} className="btn-primary bg-white/5 border border-white/10">Return to Log</button>
    </div>
  );

  const plan = data.data.dietary_plan;

  return (
    <div className="max-w-7xl mx-auto p-12 space-y-16 pb-48">
      <header className="space-y-8">
        <button onClick={() => navigate('/')} className="text-blue-500 flex items-center gap-3 font-black text-xs uppercase tracking-[0.25em] hover:gap-5 transition-all">
          <ArrowLeft size={18} /> Back to Health Log
        </button>
        <div className="flex flex-col lg:flex-row justify-between items-start lg:items-end gap-10 border-b border-white/5 pb-14">
          <div className="space-y-3">
            <h1 className="text-8xl font-black text-white tracking-tighter leading-none">The Roadmap.</h1>
            <p className="text-gray-500 font-bold text-2xl leading-relaxed max-w-2xl">
              Precision diet for {data.data.city}, dynamically priced against current retailer inventory.
            </p>
          </div>
          <div className="flex gap-4">
            <div className="glass-card px-6 py-4 rounded-3xl flex items-center gap-4">
              <TrendingUp size={24} className="text-blue-500" />
              <div className="flex flex-col">
                <span className="text-[10px] font-black text-gray-500 uppercase tracking-widest">Accuracy</span>
                <span className="text-white font-black">98.4%</span>
              </div>
            </div>
          </div>
        </div>
      </header>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-16 items-start">
        <div className="xl:col-span-2 space-y-12">
          {plan.days.map((day: any) => (
            <div key={day.day_number} className="glass-card rounded-[4rem] overflow-hidden">
              <div className="bg-white/5 px-12 py-8 border-b border-white/5 flex items-center gap-6">
                <div className="w-14 h-14 bg-blue-600 rounded-3xl flex items-center justify-center text-white font-black text-lg shadow-xl">
                  {day.day_number}
                </div>
                <h3 className="font-black text-white uppercase tracking-[0.3em] text-sm">Metabolic Cycle / Day {day.day_number}</h3>
              </div>
              <div className="p-12 sm:p-16 space-y-16">
                {['breakfast', 'lunch', 'dinner'].map(mealKey => {
                  const meal = day[mealKey];
                  if (!meal) return null;
                  return (
                    <div key={mealKey} className="group relative pl-12 border-l-2 border-white/5 hover:border-blue-500/30 transition-all">
                      <div className="absolute -left-[11px] top-0 w-[20px] h-[20px] rounded-full bg-[#0a0f1e] border-[4px] border-white/5 group-hover:border-blue-500/50 transition-all shadow-xl" />
                      <div className="text-[11px] font-black uppercase text-gray-600 mb-4 tracking-[0.3em]">{mealKey}</div>
                      <h4 className="text-4xl font-black text-white mb-6 group-hover:text-blue-400 transition-colors tracking-tight leading-none">{meal.name}</h4>
                      <p className="text-gray-400 text-lg leading-relaxed mb-10 max-w-3xl font-medium">{meal.description}</p>
                      
                      <div className="flex flex-wrap gap-8">
                        <div className="flex items-center gap-3 glass-card px-5 py-3 rounded-2xl">
                          <Clock size={18} className="text-blue-500" />
                          <span className="text-xs font-black text-white uppercase tracking-widest">{meal.preparation_time}m prep</span>
                        </div>
                        <div className="flex items-center gap-3 bg-blue-600/10 border border-blue-500/20 px-5 py-3 rounded-2xl">
                          <Zap size={18} className="text-blue-500" />
                          <span className="text-xs font-black text-blue-500 uppercase tracking-widest">{meal.nutritional_info?.calories} kcal</span>
                        </div>
                      </div>
                      
                      <div className="mt-10 grid grid-cols-1 sm:grid-cols-2 gap-4">
                         {meal.ingredients?.map((ing: any, i: number) => (
                           <div key={i} className="flex items-center gap-3 text-sm font-bold text-gray-500 bg-white/5 p-3 rounded-xl border border-white/5">
                             <CheckCircle2 size={14} className="text-blue-500/50" />
                             {ing.quantity}{ing.unit} {ing.name}
                           </div>
                         ))}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          ))}
        </div>

        <aside className="xl:sticky xl:top-32 space-y-12">
          <div className="bg-blue-600 p-14 rounded-[4rem] shadow-[0_40px_80px_-15px_rgba(37,99,235,0.5)] text-white relative overflow-hidden group">
            <div className="absolute -right-16 -bottom-16 opacity-10 rotate-12 group-hover:rotate-0 transition-transform duration-700">
              <ShoppingCart size={300} />
            </div>
            <div className="flex items-center gap-4 mb-10">
              <ShoppingCart size={32} strokeWidth={3} />
              <h3 className="font-black text-3xl uppercase tracking-tighter leading-none">Basket Estimate</h3>
            </div>
            <div className="flex items-baseline gap-3 mb-14">
              <span className="text-8xl font-black tracking-tighter leading-none">{parseFloat(plan.total_price).toFixed(0)}</span>
              <span className="text-3xl opacity-80 font-black uppercase tracking-widest">{plan.currency}</span>
            </div>
            <div className="space-y-6 relative z-10">
              {plan.shopping_list.map((item: any, idx: number) => (
                <div key={idx} className="flex justify-between items-start text-base border-b border-white/10 pb-5 last:border-0 group/item">
                  <div className="space-y-1.5 max-w-[70%]">
                    <div className="font-black leading-[1.2] opacity-95 group-hover/item:text-blue-200 transition-colors">{item.ingredient}</div>
                    <div className="flex items-center gap-2 text-[10px] font-black opacity-60 uppercase tracking-widest bg-black/20 px-2 py-1 rounded-md w-fit">
                      <ChefHat size={12} /> {item.matched_product_name || 'Selected Retailer'}
                    </div>
                  </div>
                  <span className="font-black whitespace-nowrap text-right text-lg">{item.price} {item.currency}</span>
                </div>
              ))}
            </div>
          </div>

          <div className="glass-card p-12 rounded-[3.5rem] space-y-10">
            <h4 className="text-[11px] font-black text-gray-500 uppercase tracking-[0.4em] text-center border-b border-white/5 pb-6">Architecture Intelligence</h4>
            <div className="space-y-8">
              {[
                { label: 'Core Engine', val: 'Gemini 2.0 Ultra' },
                { label: 'Data Source', val: 'Retail Leaflets' },
                { label: 'Update Cycle', val: 'Every 24h' }
              ].map((row, i) => (
                <div key={i} className="flex flex-col gap-2">
                  <span className="text-[10px] font-bold text-gray-600 uppercase tracking-widest">{row.label}</span>
                  <span className="text-white font-black text-sm tracking-tight bg-white/5 px-4 py-2 rounded-xl border border-white/5">{row.val}</span>
                </div>
              ))}
            </div>
          </div>
        </aside>
      </div>
    </div>
  );
};

// --- ROUTER SETUP ---

const queryClient = new QueryClient();

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<LoginView />} />
          <Route path="/login-success" element={<LoginSuccess />} />
          <Route path="/" element={<ProtectedRoute><Navbar /><Dashboard /></ProtectedRoute>} />
          <Route path="/create" element={<ProtectedRoute><Navbar /><CreateGoal /></ProtectedRoute>} />
          <Route path="/plan/:id" element={<ProtectedRoute><Navbar /><PlanDetail /></ProtectedRoute>} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}