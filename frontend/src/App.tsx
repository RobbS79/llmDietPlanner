import React, { useState } from 'react';
import { BrowserRouter, Routes, Route, Navigate, useNavigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider, useMutation } from '@tanstack/react-query';
import { LogIn, Plus, List, Utensils, Apple, Clock } from 'lucide-react';
import axios from 'axios';

/**
 * BRAND THEME: Dark Blue UI
 * Background: #0a0f1e
 * Card: #161d2f
 * Accent: #2563eb
 */

const api = axios.create({
  baseURL: '/api',
  withCredentials: true,
});

const Navbar = () => {
  const navigate = useNavigate();
  return (
    <nav className="bg-[#161d2f]/80 backdrop-blur-md border-b border-white/5 px-6 py-4 flex justify-between items-center sticky top-0 z-50">
      <div className="flex items-center gap-2 font-bold text-xl cursor-pointer" onClick={() => navigate('/')}>
        <div className="w-8 h-8 bg-blue-600 rounded-lg flex items-center justify-center text-white">
          <Utensils size={20} />
        </div>
        <span className="bg-gradient-to-r from-white to-gray-400 bg-clip-text text-transparent">DietPlanner AI</span>
      </div>
      <div className="flex gap-4">
        <button onClick={() => navigate('/create')} className="text-sm text-gray-400 hover:text-white transition-colors">New Goal</button>
        <button onClick={() => navigate('/login')} className="text-sm bg-blue-600 px-4 py-2 rounded-lg font-bold hover:bg-blue-500 transition-all">Logout</button>
      </div>
    </nav>
  );
};

const LoginView = () => {
  const handleGoogleLogin = () => {
    // Redirect to Django Social Auth
    window.location.href = '/api/auth/google/';
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
          className="w-full flex items-center justify-center gap-4 bg-white text-black font-bold py-4 rounded-2xl hover:bg-gray-100 transition-transform active:scale-[0.98]"
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

const CreateGoal = () => {
  const [prompt, setPrompt] = useState('');
  const mutation = useMutation({
    mutationFn: (data: any) => api.post('/goals/', data),
  });

  return (
    <div className="max-w-2xl mx-auto p-8">
      <div className="bg-[#161d2f] border border-white/5 rounded-3xl p-10 shadow-2xl">
        <h2 className="text-2xl font-bold mb-6 flex items-center gap-3 text-white"><Apple className="text-blue-500" /> New Dietary Goal</h2>
        <textarea 
          className="w-full bg-[#0a0f1e] border border-white/10 rounded-2xl p-5 text-white h-40 focus:ring-2 focus:ring-blue-600 outline-none transition-all"
          placeholder="E.g. I want a 1800kcal diet with high protein using local Lidl products..."
          onChange={(e) => setPrompt(e.target.value)}
        />
        <button 
          onClick={() => mutation.mutate({ prompt, country: 'CZ', city: 'Prague' })}
          className="w-full bg-blue-600 mt-6 py-4 rounded-xl font-bold text-white hover:bg-blue-500 transition-all shadow-xl shadow-blue-900/20"
        >
          {mutation.isPending ? 'Analyzing Requirements...' : 'Generate AI Plan'}
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
          <Route path="/" element={<><Navbar /><div className="max-w-6xl mx-auto p-8"><h1 className="text-3xl font-bold text-white">Dashboard</h1></div></>} />
          <Route path="/create" element={<><Navbar /><CreateGoal /></>} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}