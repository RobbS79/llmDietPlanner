import { useState, useEffect } from 'react';
import { BrowserRouter, Routes, Route, Navigate, useNavigate, useSearchParams, useParams } from 'react-router-dom';
import { QueryClient, QueryClientProvider, useMutation, useQuery } from '@tanstack/react-query';
import { Utensils, Apple, Loader2, LogOut, PlusCircle, ChevronRight, Calendar, ShoppingCart, CheckCircle2, AlertCircle, ArrowLeft, Clock, Zap } from 'lucide-react';
import axios from 'axios';

/**
 * PRODUCTION FRONTEND - Consolidating all logic for stability.
 * Lives in: frontend/src/App.tsx
 */

// --- API Client Configuration ---
const api = axios.create({
  baseURL: '/api',
  withCredentials: true,
});

// Interceptor to attach JWT tokens to every request
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// --- Auth Guard ---
const ProtectedRoute = ({ children }: { children: any }) => {
  const isAuthenticated = !!localStorage.getItem('access_token');
  if (!isAuthenticated) return <Navigate to="/login" replace />;
  return children;
};

// --- Navbar Component ---
const Navbar = () => {
  const navigate = useNavigate();
  const handleLogout = () => {
    localStorage.clear();
    window.location.href = '/login';
  };

  return (
    <nav className="bg-[#161d2f]/90 backdrop-blur-xl border-b border-white/5 px-6 py-4 flex justify-between items-center sticky top-0 z-50">
      <div className="flex items-center gap-2 font-black text-2xl cursor-pointer" onClick={() => navigate('/')}>
        <div className="w-10 h-10 bg-blue-600 rounded-xl flex items-center justify-center text-white shadow-lg shadow-blue-900/40">
          <Utensils size={24} />
        </div>
        <span className="bg-gradient-to-r from-white to-gray-400 bg-clip-text text-transparent hidden sm:block">DietPlanner AI</span>
      </div>
      <div className="flex gap-4 sm:gap-8 items-center">
        <button onClick={() => navigate('/create')} className="text-sm font-bold text-gray-400 hover:text-white transition-colors flex items-center gap-2">
          <PlusCircle size={18} /> <span className="hidden sm:inline">New Goal</span>
        </button>
        <button onClick={handleLogout} className="p-2.5 bg-white/5 text-gray-400 hover:text-red-500 hover:bg-red-500/10 rounded-xl transition-all">
          <LogOut size={20} />
        </button>
      </div>
    </nav>
  );
};

// --- LOGIN VIEW ---
const LoginView = () => {
  const handleGoogleLogin = () => {
    window.location.href = '/api/auth/google/login/';
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-[#0a0f1e] p-6 selection:bg-blue-500/30">
      <div className="max-w-md w-full bg-[#161d2f] border border-white/5 rounded-[2.5rem] p-12 shadow-2xl text-center relative overflow-hidden">
        <div className="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-transparent via-blue-500 to-transparent opacity-50" />
        <div className="inline-flex items-center justify-center w-24 h-24 rounded-3xl bg-blue-600/10 text-blue-500 mb-10 shadow-inner">
          <Zap size={48} fill="currentColor" />
        </div>
        <h1 className="text-4xl font-black text-white mb-4 tracking-tight">Nutrition, <br/>Personalized.</h1>
        <p className="text-gray-400 text-base leading-relaxed mb-12">Automatically map your clinical dietary needs to local supermarket offers using AI.</p>
        
        <button 
          onClick={handleGoogleLogin}
          className="w-full flex items-center justify-center gap-4 bg-white text-black font-black py-5 rounded-[1.25rem] hover:bg-gray-100 transition-all active:scale-[0.98] shadow-xl"
        >
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

// --- LOGIN SUCCESS ---
const LoginSuccess = () => {
  const [params] = useSearchParams();
  const navigate = useNavigate();

  useEffect(() => {
    const access = params.get('access');
    const refresh = params.get('refresh');
    if (access && refresh) {
      localStorage.setItem('access_token', access);
      localStorage.setItem('refresh_token', refresh);
      navigate('/');
    }
  }, [params, navigate]);

  return (
    <div className="min-h-screen flex flex-col items-center justify-center bg-[#0a0f1e] text-white">
      <Loader2 className="animate-spin text-blue-500 mb-4" size={48} />
      <p className="text-gray-400 font-medium">Starting AI Engine...</p>
    </div>
  );
};

// --- DASHBOARD / GOAL LIST ---
const Dashboard = () => {
  const navigate = useNavigate();
  const { data, isLoading } = useQuery({
    queryKey: ['goals'],
    queryFn: () => api.get('/goals/list/').then(res => res.data),
    refetchInterval: (query) => {
      const hasProcessing = query.state.data?.data?.some((g: any) => ['processing', 'pending', 'payment_pending'].includes(g.status));
      return hasProcessing ? 5000 : false;
    }
  });

  if (isLoading) return <div className="min-h-screen flex items-center justify-center bg-[#0a0f1e]"><Loader2 className="animate-spin text-blue-500" size={40} /></div>;

  const goals = data?.data || [];

  return (
    <div className="max-w-6xl mx-auto p-6 sm:p-12 space-y-12 bg-[#0a0f1e] min-h-screen">
      <header className="flex flex-col sm:flex-row justify-between items-start sm:items-end gap-6">
        <div>
          <h1 className="text-5xl font-black text-white tracking-tighter mb-2">My Plans</h1>
          <p className="text-gray-500 font-medium">Your personalized path to better health.</p>
        </div>
        <button onClick={() => navigate('/create')} className="bg-blue-600 px-8 py-4 rounded-[1.25rem] font-black text-white hover:bg-blue-500 transition-all shadow-lg shadow-blue-900/20 flex items-center gap-2">
          <PlusCircle size={20} /> Create New
        </button>
      </header>

      {goals.length === 0 ? (
        <div className="bg-[#161d2f] border border-white/5 p-16 rounded-[3rem] text-center">
          <div className="w-24 h-24 bg-blue-600/5 text-blue-500 rounded-[2rem] flex items-center justify-center mx-auto mb-8">
            <Apple size={48} />
          </div>
          <h3 className="text-white font-black text-2xl mb-3">No plans yet</h3>
          <p className="text-gray-500 mb-10 max-w-sm mx-auto leading-relaxed">Tell us your goals and we'll scan the local stores to find the best deals for your diet.</p>
          <button onClick={() => navigate('/create')} className="text-blue-500 font-black hover:underline text-lg">Start Your First Plan</button>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
          {goals.map((g: any) => (
            <div 
              key={g.id}
              onClick={() => g.status === 'completed' && navigate(`/plan/${g.id}`)}
              className={`group bg-[#161d2f] border border-white/5 p-8 rounded-[2.5rem] transition-all relative overflow-hidden ${g.status === 'completed' ? 'hover:border-blue-500/50 hover:bg-[#1c253d] cursor-pointer shadow-xl' : 'opacity-80'}`}
            >
              <div className="flex justify-between items-center mb-6">
                <span className={`px-4 py-1.5 rounded-full text-[10px] font-black uppercase tracking-[0.15em] border ${
                  g.status === 'completed' ? 'bg-green-500/10 text-green-500 border-green-500/20' : 
                  'bg-blue-500/10 text-blue-500 border-blue-500/20 animate-pulse'
                }`}>
                  {g.status}
                </span>
                <span className="text-[10px] font-bold text-gray-500">{new Date(g.created_at).toLocaleDateString()}</span>
              </div>
              <h3 className="text-white font-black text-xl mb-4 line-clamp-3 leading-tight tracking-tight">{g.prompt}</h3>
              <div className="flex items-center gap-3 text-[10px] font-bold text-gray-400 uppercase tracking-widest">
                <span className="bg-white/5 px-3 py-1.5 rounded-lg">{g.city}</span>
                <span className="bg-white/5 px-3 py-1.5 rounded-lg">{g.country}</span>
              </div>
              {g.status === 'completed' && (
                <div className="mt-8 pt-8 border-t border-white/5 flex justify-between items-center text-blue-500">
                  <span className="font-black text-xs uppercase tracking-widest">View Results</span>
                  <ChevronRight size={18} className="group-hover:translate-x-1 transition-transform" />
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

// --- CREATE GOAL FORM ---
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
    <div className="max-w-2xl mx-auto p-6 sm:p-12">
      <div className="bg-[#161d2f] border border-white/5 rounded-[3rem] p-12 shadow-2xl relative">
        <button onClick={() => navigate('/')} className="absolute -top-4 -left-4 w-12 h-12 bg-[#161d2f] border border-white/10 rounded-2xl flex items-center justify-center text-gray-400 hover:text-white transition-colors shadow-lg">
          <ArrowLeft size={20} />
        </button>
        <h2 className="text-3xl font-black mb-8 flex items-center gap-3 text-white tracking-tighter">New Goal</h2>
        
        <div className="space-y-8">
          <div>
            <label className="block text-[10px] font-black text-gray-500 uppercase tracking-[0.2em] mb-3">Dietary Context</label>
            <textarea 
              className="w-full bg-[#0a0f1e] border border-white/10 rounded-[1.5rem] p-6 text-white h-56 focus:ring-2 focus:ring-blue-600 outline-none transition-all resize-none leading-relaxed"
              placeholder="Describe your health goals, calories, allergies, and typical shopping preferences..."
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
            />
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
            <div>
              <label className="block text-[10px] font-black text-gray-500 uppercase tracking-[0.2em] mb-3">Target Country</label>
              <select 
                value={country} 
                onChange={(e) => setCountry(e.target.value)}
                className="w-full bg-[#0a0f1e] border border-white/10 rounded-2xl p-4 text-white font-bold outline-none cursor-pointer"
              >
                <option value="CZ">Czech Republic</option>
                <option value="SK">Slovakia</option>
                <option value="PL">Poland</option>
              </select>
            </div>
            <div>
              <label className="block text-[10px] font-black text-gray-500 uppercase tracking-[0.2em] mb-3">Target City</label>
              <input 
                type="text" 
                value={city}
                onChange={(e) => setCity(e.target.value)}
                className="w-full bg-[#0a0f1e] border border-white/10 rounded-2xl p-4 text-white font-bold outline-none"
              />
            </div>
          </div>
        </div>

        <button 
          onClick={() => mutation.mutate({ prompt, country, city, language_code: 'en', num_days: 7 })}
          disabled={mutation.isPending || prompt.length < 10}
          className="w-full bg-blue-600 mt-12 py-5 rounded-[1.5rem] font-black text-white hover:bg-blue-500 transition-all shadow-2xl shadow-blue-900/30 disabled:opacity-50 flex items-center justify-center gap-3"
        >
          {mutation.isPending ? <><Loader2 className="animate-spin" /> Analyzing Requirements...</> : 'Generate AI Plan'}
        </button>
      </div>
    </div>
  );
};

// --- PLAN DETAIL VIEW ---
const PlanDetail = () => {
  const { id } = useParams();
  const navigate = useNavigate();

  const { data, isLoading, error } = useQuery({
    queryKey: ['plan', id],
    queryFn: () => api.get(`/goals/${id}/`).then(res => res.data),
    enabled: !!id,
  });

  if (isLoading) return <div className="min-h-screen flex items-center justify-center bg-[#0a0f1e]"><Loader2 className="animate-spin text-blue-500" size={40} /></div>;
  if (error || !data?.data?.dietary_plan) return <div className="text-center text-red-500 p-20 flex flex-col items-center gap-4 min-h-screen bg-[#0a0f1e]"><AlertCircle size={48} /><span>Plan not found.</span><button onClick={() => navigate('/')} className="text-white underline">Back home</button></div>;

  const plan = data.data.dietary_plan;

  return (
    <div className="max-w-6xl mx-auto p-6 sm:p-12 space-y-12 pb-32 bg-[#0a0f1e]">
      <header className="space-y-4">
        <button onClick={() => navigate('/')} className="text-blue-500 flex items-center gap-2 font-black text-xs uppercase tracking-widest hover:gap-3 transition-all">
          <ArrowLeft size={14} /> Back to Plans
        </button>
        <h1 className="text-5xl font-black text-white tracking-tighter">Your Weekly Plan</h1>
        <p className="text-gray-500 font-medium">Synced with local supermarket inventory.</p>
      </header>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-12 items-start">
        <div className="lg:col-span-2 space-y-10">
          {plan.days.map((day: any) => (
            <div key={day.day_number} className="bg-[#161d2f] border border-white/5 rounded-[2.5rem] overflow-hidden shadow-xl">
              <div className="bg-blue-600/10 px-8 py-5 border-b border-white/5 flex items-center gap-4">
                <div className="w-8 h-8 bg-blue-600 rounded-lg flex items-center justify-center text-white font-black text-xs shadow-lg">
                  {day.day_number}
                </div>
                <h3 className="font-black text-white uppercase tracking-widest text-xs">Day {day.day_number}</h3>
              </div>
              <div className="p-10 space-y-10">
                {['breakfast', 'lunch', 'dinner'].map(mealKey => {
                  const meal = day[mealKey];
                  if (!meal) return null;
                  return (
                    <div key={mealKey} className="group relative pl-8 border-l-2 border-white/5 hover:border-blue-500/50 transition-all">
                      <div className="absolute -left-[9px] top-0 w-4 h-4 rounded-full bg-[#161d2f] border-2 border-white/10 group-hover:border-blue-500/50 transition-all" />
                      <div className="text-[10px] font-black uppercase text-gray-500 mb-2 tracking-[0.2em]">{mealKey}</div>
                      <h4 className="text-2xl font-black text-white mb-3 group-hover:text-blue-400 transition-colors tracking-tight">{meal.name}</h4>
                      <p className="text-gray-400 text-sm leading-relaxed mb-6">{meal.description}</p>
                      <div className="flex gap-4 text-[10px] font-bold text-gray-500 uppercase tracking-widest">
                        <span className="flex items-center gap-1.5"><Clock size={12} /> {meal.preparation_time}m</span>
                        <span className="flex items-center gap-1.5 text-blue-500"><CheckCircle2 size={12} /> {meal.nutritional_info?.calories} kcal</span>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          ))}
        </div>

        <aside className="lg:sticky lg:top-28 space-y-8">
          <div className="bg-blue-600 p-10 rounded-[3rem] shadow-2xl shadow-blue-900/40 text-white relative overflow-hidden">
            <div className="absolute -right-8 -bottom-8 opacity-10 rotate-12">
              <ShoppingCart size={160} />
            </div>
            <div className="flex items-center gap-3 mb-6">
              <ShoppingCart size={24} />
              <h3 className="font-black text-xl uppercase tracking-tighter">Shopping List</h3>
            </div>
            <div className="text-6xl font-black mb-10 tracking-tighter">
              {parseFloat(plan.total_price).toFixed(0)} <span className="text-xl opacity-70 font-medium tracking-normal uppercase">{plan.currency}</span>
            </div>
            <div className="space-y-4 relative z-10">
              {plan.shopping_list.map((item: any, idx: number) => (
                <div key={idx} className="flex justify-between items-center text-sm border-b border-white/10 pb-3 last:border-0">
                  <span className="font-bold opacity-90 truncate mr-4">{item.ingredient}</span>
                  <span className="font-black whitespace-nowrap">{item.price} {item.currency}</span>
                </div>
              ))}
            </div>
          </div>

          <div className="bg-[#161d2f] border border-white/5 p-8 rounded-[2.5rem]">
            <h4 className="text-[10px] font-black text-gray-500 uppercase mb-6 tracking-[0.2em]">Efficiency Analysis</h4>
            <div className="space-y-4 text-xs font-bold text-gray-400">
              <div className="flex justify-between"><span>AI Engine</span><span className="text-white">Gemini 2.0</span></div>
              <div className="flex justify-between"><span>Processing</span><span className="text-white">Async Task</span></div>
              <div className="flex justify-between"><span>Price Match</span><span className="text-white">Store Realtime</span></div>
            </div>
          </div>
        </aside>
      </div>
    </div>
  );
};

// --- APP ROUTER ---
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