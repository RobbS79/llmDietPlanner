import { useState, useEffect } from 'react';
import { BrowserRouter, Routes, Route, Navigate, useNavigate, useSearchParams, useParams } from 'react-router-dom';
import { QueryClient, QueryClientProvider, useMutation, useQuery } from '@tanstack/react-query';
import { Utensils, Apple, Loader2, LogOut, PlusCircle, ChevronRight, Calendar, ShoppingCart, CheckCircle2, AlertCircle, ArrowLeft, Clock, Zap } from 'lucide-react';
import axios from 'axios';

/**
 * PRODUCTION FRONTEND
 * Path: frontend/src/App.tsx
 * Synchronized with GoogleCallbackView in backend.
 */

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
    // Correct logic: Trigger the backend GET redirect view
    window.location.href = '/api/auth/google/login/';
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-[#0a0f1e] p-6">
      <div className="max-w-md w-full bg-[#161d2f] border border-white/5 rounded-[2.5rem] p-12 shadow-2xl text-center">
        <div className="inline-flex items-center justify-center w-24 h-24 rounded-3xl bg-blue-600/10 text-blue-500 mb-10"><Zap size={48} fill="currentColor" /></div>
        <h1 className="text-4xl font-black text-white mb-4 tracking-tight">DietPlanner AI</h1>
        <p className="text-gray-400 mb-8">Personalized nutrition mapped to local deals.</p>
        
        {error && (
          <div className="bg-red-500/10 border border-red-500/20 text-red-500 p-4 rounded-xl mb-6 text-sm flex items-center gap-2">
            <AlertCircle size={16} /> Login failed: {error}
          </div>
        )}

        <button onClick={handleGoogleLogin} className="w-full flex items-center justify-center gap-4 bg-white text-black font-black py-5 rounded-[1.25rem] hover:bg-gray-100 transition-all shadow-xl active:scale-[0.98]">
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
      navigate('/login?error=token_missing', { replace: true });
    }
  }, [params, navigate]);

  return (
    <div className="min-h-screen flex flex-col items-center justify-center bg-[#0a0f1e] text-white">
      <Loader2 className="animate-spin text-blue-500 mb-4" size={48} />
      <p className="text-gray-400 font-bold uppercase tracking-widest text-xs">Authenticating...</p>
    </div>
  );
};

// --- CORE APP COMPONENTS ---

const Navbar = () => {
  const navigate = useNavigate();
  const logout = () => { localStorage.clear(); window.location.href = '/login'; };
  return (
    <nav className="bg-[#161d2f]/90 backdrop-blur-xl border-b border-white/5 px-8 py-5 flex justify-between items-center sticky top-0 z-50">
      <div className="flex items-center gap-2 font-black text-2xl cursor-pointer" onClick={() => navigate('/')}>
        <div className="w-10 h-10 bg-blue-600 rounded-xl flex items-center justify-center text-white shadow-lg shadow-blue-900/40 font-black">DP</div>
        <span className="bg-gradient-to-r from-white to-gray-400 bg-clip-text text-transparent">DietPlanner</span>
      </div>
      <div className="flex gap-6 items-center">
        <button onClick={() => navigate('/create')} className="text-sm font-black text-gray-400 hover:text-white transition-colors flex items-center gap-2">
          <PlusCircle size={18} /> <span className="hidden sm:inline">New Goal</span>
        </button>
        <button onClick={logout} className="p-2.5 bg-white/5 text-gray-400 hover:text-red-500 rounded-xl transition-all"><LogOut size={20} /></button>
      </div>
    </nav>
  );
};

const Dashboard = () => {
  const navigate = useNavigate();
  const { data, isLoading } = useQuery({
    queryKey: ['goals'],
    queryFn: () => api.get('/goals/list/').then(res => res.data),
    refetchInterval: (q) => q.state.data?.data?.some((g: any) => g.status !== 'completed' && g.status !== 'failed') ? 5000 : false,
  });

  if (isLoading) return <div className="min-h-screen flex items-center justify-center"><Loader2 className="animate-spin text-blue-500" size={40} /></div>;

  const goals = data?.data || [];

  return (
    <div className="max-w-6xl mx-auto p-12 space-y-12 min-h-screen">
      <h1 className="text-5xl font-black text-white tracking-tighter">My Plans</h1>
      {goals.length === 0 ? (
        <div className="bg-[#161d2f] border border-white/5 p-20 rounded-[3rem] text-center">
          <div className="w-24 h-24 bg-blue-600/5 text-blue-500 rounded-[2rem] flex items-center justify-center mx-auto mb-8"><Apple size={48} /></div>
          <h3 className="text-white font-black text-2xl mb-8">Ready to start?</h3>
          <button onClick={() => navigate('/create')} className="bg-blue-600 px-10 py-5 rounded-[1.5rem] font-black text-white hover:bg-blue-500 transition-all shadow-xl">Create Your First Plan</button>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
          {goals.map((g: any) => (
            <div key={g.id} onClick={() => g.status === 'completed' && navigate(`/plan/${g.id}`)} className={`bg-[#161d2f] border border-white/5 p-8 rounded-[2.5rem] transition-all ${g.status === 'completed' ? 'hover:border-blue-500/50 cursor-pointer shadow-xl' : 'opacity-80'}`}>
              <span className={`text-[10px] font-black uppercase tracking-widest mb-4 block ${g.status === 'completed' ? 'text-green-500' : 'text-blue-500 animate-pulse'}`}>{g.status}</span>
              <h3 className="text-white font-bold line-clamp-2 mb-6 h-12 leading-snug">{g.prompt}</h3>
              <div className="flex justify-between items-center text-[10px] font-black text-gray-500 uppercase tracking-widest">
                <span>{g.city}, {g.country}</span>
                <span>{new Date(g.created_at).toLocaleDateString()}</span>
              </div>
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
    <div className="max-w-2xl mx-auto p-12">
      <div className="bg-[#161d2f] border border-white/5 rounded-[3rem] p-12 shadow-2xl relative">
        <button onClick={() => navigate('/')} className="absolute -top-4 -left-4 w-12 h-12 bg-[#161d2f] border border-white/10 rounded-2xl flex items-center justify-center text-gray-400 hover:text-white transition-colors"><ArrowLeft size={20} /></button>
        <h2 className="text-3xl font-black mb-10 text-white tracking-tighter">New Goal</h2>
        <div className="space-y-8">
          <div>
            <label className="block text-[10px] font-black text-gray-500 uppercase tracking-[0.2em] mb-3">Dietary Context</label>
            <textarea className="w-full bg-[#0a0f1e] border border-white/10 rounded-2xl p-6 text-white h-48 focus:ring-2 focus:ring-blue-600 outline-none transition-all resize-none" value={prompt} onChange={(e) => setPrompt(e.target.value)} placeholder="E.g. Lose 5kg, high protein, shop at Lidl..." />
          </div>
          <div className="grid grid-cols-2 gap-6">
            <div>
              <label className="block text-[10px] font-black text-gray-500 uppercase tracking-[0.2em] mb-3">Country</label>
              <select value={country} onChange={(e) => setCountry(e.target.value)} className="w-full bg-[#0a0f1e] border border-white/10 rounded-xl p-4 text-white font-bold outline-none cursor-pointer">
                <option value="CZ">Czech Republic</option>
                <option value="SK">Slovakia</option>
                <option value="PL">Poland</option>
              </select>
            </div>
            <div>
              <label className="block text-[10px] font-black text-gray-500 uppercase tracking-[0.2em] mb-3">City</label>
              <input type="text" value={city} onChange={(e) => setCity(e.target.value)} className="w-full bg-[#0a0f1e] border border-white/10 rounded-xl p-4 text-white font-bold outline-none" />
            </div>
          </div>
        </div>
        <button onClick={() => mutation.mutate({ prompt, country, city, language_code: 'en' })} disabled={mutation.isPending || prompt.length < 10} className="w-full bg-blue-600 mt-12 py-5 rounded-[1.5rem] font-black text-white hover:bg-blue-500 transition-all shadow-2xl shadow-blue-900/30 disabled:opacity-50 flex items-center justify-center gap-3">
          {mutation.isPending ? <><Loader2 className="animate-spin" /> Thinking...</> : 'Generate Plan'}
        </button>
      </div>
    </div>
  );
};

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
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}