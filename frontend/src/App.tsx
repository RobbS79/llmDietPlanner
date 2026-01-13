import { useState, useEffect } from 'react';
import { BrowserRouter, Routes, Route, Navigate, useNavigate, useSearchParams } from 'react-router-dom';
import { QueryClient, QueryClientProvider, useMutation } from '@tanstack/react-query';
import { Utensils, Apple, Loader2, AlertCircle } from 'lucide-react';
import axios from 'axios';

// Standardized API client
const api = axios.create({
  baseURL: '/api',
  withCredentials: true,
});

// Interceptor to add JWT
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

const Navbar = () => {
  const navigate = useNavigate();
  const handleLogout = () => {
    localStorage.clear();
    navigate('/login');
  };

  return (
    <nav className="bg-[#161d2f]/80 backdrop-blur-md border-b border-white/5 px-6 py-4 flex justify-between items-center sticky top-0 z-50">
      <div className="flex items-center gap-2 font-bold text-xl cursor-pointer" onClick={() => navigate('/')}>
        <div className="w-8 h-8 bg-blue-600 rounded-lg flex items-center justify-center text-white">
          <Utensils size={20} />
        </div>
        <span className="bg-gradient-to-r from-white to-gray-400 bg-clip-text text-transparent">DietPlanner AI</span>
      </div>
      <div className="flex gap-6 items-center">
        <button onClick={() => navigate('/create')} className="text-sm text-gray-400 hover:text-white transition-colors">New Goal</button>
        <button onClick={handleLogout} className="text-sm bg-red-600/10 text-red-500 px-4 py-2 rounded-lg font-bold hover:bg-red-600 hover:text-white transition-all">Logout</button>
      </div>
    </nav>
  );
};

const LoginView = () => {
  const handleGoogleLogin = () => {
    // Standard Redirect Flow
    window.location.href = '/api/auth/google/login/';
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-[#0a0f1e] p-6">
      <div className="max-w-md w-full bg-[#161d2f] border border-white/5 rounded-3xl p-10 shadow-2xl text-center">
        <div className="inline-flex items-center justify-center w-20 h-20 rounded-2xl bg-blue-600/10 text-blue-500 mb-8">
          <Utensils size={40} />
        </div>
        <h1 className="text-3xl font-extrabold text-white mb-2">Nutrition, Personalized.</h1>
        <p className="text-gray-400 text-sm mb-10">Map your dietary needs to local supermarket offers with AI.</p>
        
        <button 
          onClick={handleGoogleLogin}
          className="w-full flex items-center justify-center gap-4 bg-white text-black font-bold py-4 rounded-2xl hover:bg-gray-100 transition-all active:scale-[0.98]"
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

const Dashboard = () => {
  return (
    <div className="max-w-6xl mx-auto p-8">
      <header className="mb-12">
        <h1 className="text-4xl font-black text-white mb-2">My Meal Plans</h1>
        <p className="text-gray-400">View and manage your AI-generated nutrition goals.</p>
      </header>
      
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {/* Placeholder for Goals List */}
        <div className="bg-[#161d2f] border border-white/5 p-8 rounded-3xl flex flex-col items-center justify-center text-center min-h-[300px]">
          <div className="w-16 h-16 bg-blue-600/5 text-blue-500 rounded-2xl flex items-center justify-center mb-4">
            <Apple size={32} />
          </div>
          <h3 className="text-white font-bold text-lg">No active plans</h3>
          <p className="text-gray-500 text-sm mt-2 mb-6">Create your first goal to see AI magic.</p>
          <button className="bg-blue-600 px-6 py-3 rounded-xl font-bold text-sm">Start Planning</button>
        </div>
      </div>
    </div>
  );
};

const CreateGoal = () => {
  const [prompt, setPrompt] = useState('');
  const navigate = useNavigate();
  const mutation = useMutation({
    mutationFn: (data: any) => api.post('/goals/', data),
    onSuccess: () => navigate('/'),
  });

  return (
    <div className="max-w-2xl mx-auto p-8">
      <div className="bg-[#161d2f] border border-white/5 rounded-3xl p-10 shadow-2xl">
        <h2 className="text-2xl font-bold mb-6 flex items-center gap-3 text-white"><Apple className="text-blue-500" /> Define Your Goal</h2>
        <p className="text-gray-400 text-sm mb-6">Be specific about calories, allergies, and your favorite local shops.</p>
        
        <textarea 
          className="w-full bg-[#0a0f1e] border border-white/10 rounded-2xl p-5 text-white h-48 focus:ring-2 focus:ring-blue-600 outline-none transition-all resize-none"
          placeholder="E.g. I want to lose weight with a 1900kcal diet. High protein, no dairy. Source ingredients from Lidl in Prague..."
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
        />
        
        <button 
          onClick={() => mutation.mutate({ prompt, country: 'CZ', city: 'Prague', language_code: 'en' })}
          disabled={mutation.isPending || prompt.length < 10}
          className="w-full bg-blue-600 mt-8 py-4 rounded-xl font-bold text-white hover:bg-blue-500 transition-all shadow-xl shadow-blue-900/20 disabled:opacity-50 flex items-center justify-center gap-2"
        >
          {mutation.isPending ? <><Loader2 className="animate-spin" /> Analyzing Requirements...</> : 'Generate AI Plan'}
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
          <Route path="/" element={<><Navbar /><Dashboard /></>} />
          <Route path="/create" element={<><Navbar /><CreateGoal /></>} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}