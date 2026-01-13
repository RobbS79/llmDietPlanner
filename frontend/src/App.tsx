// File: frontend/src/App.tsx
import { useState, useEffect } from 'react';
import { BrowserRouter, Routes, Route, Navigate, useNavigate, useSearchParams, useParams } from 'react-router-dom';
import { QueryClient, QueryClientProvider, useQuery } from '@tanstack/react-query';
import { 
  Loader2, LogOut, PlusCircle, CheckCircle2, 
  AlertCircle, ArrowLeft, Clock, Zap, Leaf, 
  ShoppingCart, ChefHat, TrendingUp
} from 'lucide-react';
import axios from 'axios';

/**
 * PRODUCTION FRONTEND - DEBUGGING EDITION
 * Optimized for Google OAuth Troubleshooting.
 * Updated to handle restricted build environments and fix the faulty 'process' keyword.
 */

// We access the variable directly to allow Vite's static analysis to perform 
// the replacement during the build process, but we use a fallback to avoid ReferenceErrors.
// @ts-ignore
const GOOGLE_CLIENT_ID = (typeof import.meta !== 'undefined' && import.meta.env) 
  ? import.meta.env.VITE_GOOGLE_CLIENT_ID 
  : undefined;

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
  const errorCode = params.get('error');

  useEffect(() => {
    // CRITICAL LOGGING: Identify what identity data is reaching the client
    console.log("[DEBUG AUTH] Configuration Discovery:");
    console.log(" - VITE_GOOGLE_CLIENT_ID present:", !!GOOGLE_CLIENT_ID);
    console.log(" - Current Origin:", window.location.origin);
    
    if (!GOOGLE_CLIENT_ID) {
      console.warn("[DEBUG AUTH] SYSTEM ALERT: VITE_GOOGLE_CLIENT_ID is not defined in the frontend build.");
    }
  }, []);

  const handleGoogleLogin = () => {
    console.log("[DEBUG AUTH] Handshake triggered. Redirecting to server-side OAuth initiator...");
    // Direct browser redirect to the Django authoritative trigger
    window.location.href = '/api/auth/google/login/';
  };

  const getErrorDetail = (code: string | null) => {
    switch (code) {
      case 'google_not_configured':
        return {
          title: "Provider Configuration Missing",
          desc: "The backend server is missing the GOOGLE_CLIENT_ID environment variable.",
          action: "Add GOOGLE_CLIENT_ID to your DigitalOcean App Settings."
        };
      case 'token_exchange_failed':
        return {
          title: "Identity Verification Failure",
          desc: "Google rejected the authorization code or the client secret is invalid.",
          action: "Check if your Google Cloud Console Redirect URIs match your production domain."
        };
      case 'email_access_denied':
        return {
          title: "Insufficient Permissions",
          desc: "We could not access your email address from Google.",
          action: "Ensure you grant the requested 'email' and 'profile' permissions."
        };
      case 'sync_failed':
        return {
          title: "Local Session Sync Error",
          desc: "Verification succeeded, but we couldn't write the session tokens to your browser.",
          action: "Clear your browser cache/cookies and ensure local storage is enabled."
        };
      default:
        return {
          title: "Authentication Interrupted",
          desc: "The OAuth handshake failed unexpectedly.",
          action: "Check the 'Runtime Logs' in DigitalOcean for [DEBUG] output."
        };
    }
  };

  const error = errorCode ? getErrorDetail(errorCode) : null;

  return (
    <div className="min-h-screen flex items-center justify-center p-6 bg-[#0a0f1e]">
      <div className="max-w-md w-full glass-card rounded-[3rem] p-12 text-center relative overflow-hidden shadow-2xl">
        <div className="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-transparent via-blue-500 to-transparent" />
        <div className="inline-flex items-center justify-center w-24 h-24 rounded-[2rem] bg-blue-600/10 text-blue-500 mb-10 shadow-inner">
          <Zap size={48} fill="currentColor" />
        </div>
        <h1 className="text-5xl font-black text-white mb-4 tracking-tighter">
          DietPlanner<span className="text-blue-500">.</span>
        </h1>
        <p className="text-gray-400 text-lg font-medium leading-relaxed mb-12">
          Clinical nutrition meets local retailer inventory.
        </p>
        
        {/* DEVELOPER ALERT FOR MISSING VARIABLE */}
        {!GOOGLE_CLIENT_ID && (
           <div className="bg-amber-500/10 border border-amber-500/20 text-amber-400 p-4 rounded-2xl mb-8 text-left text-xs">
             <div className="flex items-center gap-2 mb-1 font-bold">
               <AlertCircle size={14} /> Build Target Warning
             </div>
             The frontend build did not detect <code>VITE_GOOGLE_CLIENT_ID</code>. 
             Redeploy with this variable set in your <strong>Build Settings</strong>.
           </div>
        )}

        {errorCode && (
          <div className="bg-red-500/10 border border-red-500/20 text-red-500 p-6 rounded-3xl mb-10 text-left space-y-2 animate-pulse-slow">
            <div className="flex items-center gap-2 font-black uppercase tracking-widest text-[10px]">
              <AlertCircle size={14} /> {error?.title}
            </div>
            <p className="text-xs opacity-80 leading-relaxed">{error?.desc}</p>
            <div className="pt-2 text-[10px] font-bold text-white/40 italic">
               Try this: {error?.action}
            </div>
          </div>
        )}

        <button 
          onClick={handleGoogleLogin} 
          disabled={!GOOGLE_CLIENT_ID}
          className="w-full btn-primary py-6 text-black bg-white hover:bg-gray-100 disabled:bg-gray-800 disabled:text-gray-500 transition-all flex items-center justify-center gap-4"
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

const LoginSuccess = () => {
  const [params] = useSearchParams();
  const navigate = useNavigate();

  useEffect(() => {
    const access = params.get('access');
    const refresh = params.get('refresh');
    
    console.log("[DEBUG AUTH] Token parameters detected. Synchronizing session...");

    if (access && refresh) {
      localStorage.setItem('access_token', access);
      localStorage.setItem('refresh_token', refresh);
      console.log("[DEBUG AUTH] Login verified. Navigating to root...");
      navigate('/', { replace: true });
    } else {
      console.error("[DEBUG AUTH] CRITICAL: Tokens missing from callback URL.");
      navigate('/login?error=sync_failed');
    }
  }, [params, navigate]);

  return (
    <div className="min-h-screen flex flex-col items-center justify-center text-white bg-[#0a0f1e]">
      <Loader2 className="animate-spin text-blue-500 mb-6" size={64} />
      <p className="text-gray-500 font-black uppercase tracking-[0.3em] text-[10px]">Secure Identity Exchange...</p>
    </div>
  );
};

// --- NAVIGATION & VIEWS ---
const Navbar = () => <nav className="p-4 bg-gray-900 border-b border-white/5 text-[10px] text-gray-600 font-black uppercase tracking-widest">Main Interface Container</nav>;
const Dashboard = () => <div className="p-12 text-gray-500 font-medium">Authentication successful. Welcome back.</div>;

const queryClient = new QueryClient();

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<LoginView />} />
          <Route path="/login-success" element={<LoginSuccess />} />
          <Route path="/" element={<ProtectedRoute><Navbar /><Dashboard /></ProtectedRoute>} />
          <Route path="*" element={<Navigate to="/login" replace />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}