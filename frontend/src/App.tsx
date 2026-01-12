import React, { useState, useEffect } from 'react';
import { BrowserRouter, Routes, Route, Navigate, useNavigate, useLocation } from 'react-router-dom';
import { QueryClient, QueryClientProvider, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { LogIn, Plus, List, User, LogOut, Utensils, Apple, ChevronRight, Clock, MapPin } from 'lucide-react';
import axios from 'axios';

/**
 * ARCHITECTURAL PLAN:
 * 1. Brand Identity: Dark Blue (#0a0f1e background, #161d2f cards).
 * 2. Auth: Integrated with Django's dj-rest-auth and Google Social Login.
 * 3. State: React Query for goal fetching and persistence.
 * 4. Structure: Single-file entry point for clean deployment integration.
 */

// --- API Configuration ---
const api = axios.create({
  baseURL: '/api',
  withCredentials: true,
});

// Interceptor for JWT
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// --- UI Components ---

const Navbar = () => {
  const navigate = useNavigate();
  const location = useLocation();
  
  const handleLogout = () => {
    localStorage.removeItem('access_token');
    navigate('/login');
  };

  const navItems = [
    { label: 'Dashboard', path: '/', icon: <Apple size={18} /> },
    { label: 'My Goals', path: '/goals', icon: <List size={18} /> },
    { label: 'New Goal', path: '/create', icon: <Plus size={18} /> },
  ];

  return (
    <nav className="sticky top-0 z-50 bg-brand-card/80 backdrop-blur-md border-b border-white/5 px-6 py-4 flex justify-between items-center">
      <div className="flex items-center gap-2 font-bold text-xl cursor-pointer" onClick={() => navigate('/')}>
        <div className="w-8 h-8 bg-brand-accent rounded-lg flex items-center justify-center text-white">
          <Utensils size={20} />
        </div>
        <span className="bg-gradient-to-r from-white to-gray-400 bg-clip-text text-transparent">DietPlanner</span>
      </div>
      
      <div className="flex items-center gap-6">
        {navItems.map((item) => (
          <button
            key={item.path}
            onClick={() => navigate(item.path)}
            className={`flex items-center gap-2 text-sm font-medium transition-colors ${
              location.pathname === item.path ? 'text-brand-accent' : 'text-gray-400 hover:text-white'
            }`}
          >
            {item.icon}
            {item.label}
          </button>
        ))}
        <button 
          onClick={handleLogout}
          className="p-2 text-gray-400 hover:text-red-400 transition-colors"
        >
          <LogOut size={20} />
        </button>
      </div>
    </nav>
  );
};

// --- Views ---

const LoginView = () => {
  const handleGoogleLogin = () => {
    // Redirect to Django Google Social Auth Login view
    window.location.href = '/api/auth/google/login/';
  };

  return (
    <div className="min-h-screen flex flex-col items-center justify-center p-6 bg-[#0a0f1e]">
      <div className="max-w-md w-full bg-[#161d2f] border border-white/5 rounded-3xl p-10 shadow-2xl">
        <div className="text-center mb-10">
          <div className="inline-flex items-center justify-center w-20 h-20 rounded-2xl bg-blue-600/10 text-blue-500 mb-6 shadow-inner">
            <Utensils size={40} />
          </div>
          <h1 className="text-4xl font-extrabold tracking-tight text-white mb-3">Welcome</h1>
          <p className="text-gray-400">AI-powered nutrition integrated with local supermarket leaflets.</p>
        </div>

        <button 
          onClick={handleGoogleLogin}
          className="w-full flex items-center justify-center gap-4 bg-white text-black font-bold py-4 px-6 rounded-2xl hover:bg-gray-100 transition-all active:scale-[0.98] shadow-lg shadow-white/5"
        >
          <svg className="w-6 h-6" viewBox="0 0 24 24">
            <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
            <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
            <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l3.66-2.84z"/>
            <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 12-4.53z"/>
          </svg>
          Continue with Google
        </button>

        <div className="relative my-8">
          <div className="absolute inset-0 flex items-center"><span className="w-full border-t border-white/5"></span></div>
          <div className="relative flex justify-center text-xs uppercase"><span className="bg-[#161d2f] px-3 text-gray-500">Secure SSO</span></div>
        </div>

        <p className="text-center text-xs text-gray-500 leading-relaxed">
          CEE Region Deployment (PL, CZ, SK, HU)
        </p>
      </div>
    </div>
  );
};

const Dashboard = () => {
  return (
    <div className="max-w-6xl mx-auto p-8">
      <header className="mb-12">
        <h1 className="text-4xl font-bold mb-2">Dashboard</h1>
        <p className="text-gray-400">Welcome back. Start your journey by defining a dietary goal.</p>
      </header>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="bg-brand-card p-8 rounded-3xl border border-white/5 flex flex-col items-center text-center shadow-xl">
          <div className="w-12 h-12 rounded-full bg-blue-500/10 text-blue-400 flex items-center justify-center mb-6">
            <Plus size={24} />
          </div>
          <h3 className="font-bold text-lg mb-2">Create New Goal</h3>
          <p className="text-gray-400 text-sm mb-6">Describe what you want to achieve with our AI.</p>
          <button className="w-full bg-blue-600 hover:bg-blue-500 text-white font-bold py-3 rounded-xl transition-all">Start Planning</button>
        </div>

        <div className="md:col-span-2 bg-brand-card p-8 rounded-3xl border border-white/5 shadow-xl overflow-hidden relative group">
           <div className="absolute top-0 right-0 p-8 text-blue-500/20 group-hover:scale-110 transition-transform"><Utensils size={120}/></div>
           <h3 className="font-bold text-xl mb-4">Latest Plans</h3>
           <div className="flex flex-col gap-4">
             <div className="bg-brand-dark/50 p-4 rounded-2xl flex justify-between items-center">
               <div>
                 <p className="font-semibold text-white">No active plans</p>
                 <p className="text-sm text-gray-500">Your generated plans will appear here.</p>
               </div>
               <ChevronRight size={20} className="text-gray-600"/>
             </div>
           </div>
        </div>
      </div>
    </div>
  );
};

const CreateGoalForm = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [formData, setFormData] = useState({
    prompt: '',
    country: 'CZ',
    city: '',
    language_code: 'cs',
  });

  const mutation = useMutation({
    mutationFn: (data: any) => api.post('/goals/', data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['goals'] });
      navigate('/goals');
    },
  });

  return (
    <div className="max-w-2xl mx-auto p-8">
      <div className="bg-brand-card border border-white/5 rounded-3xl p-10 shadow-2xl">
        <h2 className="text-3xl font-bold mb-8 flex items-center gap-3">
          <Apple className="text-brand-accent" /> New Dietary Goal
        </h2>

        <form onSubmit={(e) => { e.preventDefault(); mutation.mutate(formData); }} className="space-y-8">
          <div>
            <label className="block text-sm font-semibold text-gray-400 mb-3 uppercase tracking-wider">Your Request</label>
            <textarea
              required
              placeholder="E.g. I want to lose 5kg in 2 months with meals under 20 mins..."
              className="w-full bg-brand-dark border border-white/5 rounded-2xl p-5 focus:outline-none focus:ring-2 focus:ring-brand-accent h-40 transition-all"
              onChange={(e) => setFormData({...formData, prompt: e.target.value})}
            />
          </div>

          <div className="grid grid-cols-2 gap-6">
            <div>
              <label className="block text-sm font-semibold text-gray-400 mb-3 uppercase tracking-wider">Country</label>
              <select 
                className="w-full bg-brand-dark border border-white/5 rounded-xl p-4 focus:outline-none focus:ring-2 focus:ring-brand-accent appearance-none"
                onChange={(e) => setFormData({...formData, country: e.target.value})}
              >
                <option value="CZ">Czech Republic</option>
                <option value="PL">Poland</option>
                <option value="SK">Slovakia</option>
                <option value="HU">Hungary</option>
              </select>
            </div>
            <div>
              <label className="block text-sm font-semibold text-gray-400 mb-3 uppercase tracking-wider">City</label>
              <input
                required
                type="text"
                placeholder="Enter city"
                className="w-full bg-brand-dark border border-white/5 rounded-xl p-4 focus:outline-none focus:ring-2 focus:ring-brand-accent"
                onChange={(e) => setFormData({...formData, city: e.target.value})}
              />
            </div>
          </div>

          <button 
            type="submit"
            disabled={mutation.isPending}
            className="w-full bg-brand-accent hover:bg-blue-500 disabled:bg-gray-600 text-white font-bold py-4 rounded-2xl shadow-lg shadow-brand-accent/20 transition-all active:scale-[0.98]"
          >
            {mutation.isPending ? 'Processing AI Magic...' : 'Generate Plan'}
          </button>
        </form>
      </div>
    </div>
  );
};

// --- App Shell ---

const queryClient = new QueryClient();

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<LoginView />} />
          <Route path="/" element={<><Navbar /><Dashboard /></>} />
          <Route path="/create" element={<><Navbar /><CreateGoalForm /></>} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}