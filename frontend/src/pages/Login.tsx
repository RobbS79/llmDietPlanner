import { useState } from 'react';
import { useNavigate, useSearchParams, Link } from 'react-router-dom';
import { useMutation } from '@tanstack/react-query';
import { Zap, Loader2, AlertCircle, CheckCircle2, Mail, Eye, EyeOff, UserPlus, KeyRound } from 'lucide-react';
import axios from 'axios';

const GoogleIcon = () => (
  <svg className="w-5 h-5" viewBox="0 0 24 24"><path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/><path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/><path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l3.66-2.84z"/><path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 12-4.53z"/></svg>
);

export const Login = () => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [mode, setMode] = useState<'login' | 'register'>('login');
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [form, setForm] = useState({ username: '', email: '', password: '', passwordConfirm: '' });

  const urlError = searchParams.get('error');

  const loginMutation = useMutation({
    mutationFn: (data: { username: string; password: string }) => axios.post('/api/auth/login/', data),
    onSuccess: (res) => {
      const { access, refresh } = res.data.data;
      localStorage.setItem('access_token', access);
      localStorage.setItem('refresh_token', refresh);
      navigate('/', { replace: true });
    },
    onError: (err: any) => {
      const msg = err.response?.data?.error;
      setError(msg === 'Account pending verification' ? 'Check your email to verify your account before logging in.' : msg || 'Login failed');
    },
  });

  const registerMutation = useMutation({
    mutationFn: (data: { username: string; email: string; password: string; passwordConfirm: string }) => axios.post('/api/auth/register/', data),
    onSuccess: () => {
      setSuccess('Account created! Check your email to verify, then log in.');
      setError('');
      setMode('login');
      setForm(prev => ({ ...prev, password: '', passwordConfirm: '' }));
    },
    onError: (err: any) => setError(err.response?.data?.error || 'Registration failed'),
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setSuccess('');
    if (mode === 'register') {
      if (form.password !== form.passwordConfirm) { setError('Passwords do not match'); return; }
      registerMutation.mutate(form);
    } else {
      loginMutation.mutate({ username: form.username, password: form.password });
    }
  };

  const isLoading = loginMutation.isPending || registerMutation.isPending;
  const update = (field: string, value: string) => setForm(prev => ({ ...prev, [field]: value }));

  return (
    <div className="h-screen flex items-center justify-center p-6 bg-[#1e293b] relative overflow-hidden">
      <a href="#login-form" className="skip-to-content">
        Přejít na formulář
      </a>
      <div className="absolute top-0 left-0 w-full h-full pointer-events-none">
        <div className="absolute top-[-15%] left-[-15%] w-[800px] h-[800px] bg-emerald-600/[0.04] blur-[180px] rounded-full animate-pulse" />
        <div className="absolute bottom-[-15%] right-[-15%] w-[900px] h-[900px] bg-teal-600/[0.02] blur-[220px] rounded-full animate-pulse delay-1000" />
      </div>

      <div className="max-w-md w-full relative z-10 bg-slate-700/50 border border-slate-600 rounded-3xl shadow-deep-full p-12">
        <div className="text-center mb-10">
          <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-gradient-to-br from-emerald-600 to-emerald-400 text-white mb-6 shadow-glow-md">
            <Zap size={32} fill="currentColor" />
          </div>
          <h1 className="text-4xl font-black text-white tracking-tighter leading-none uppercase italic">
            Diet<span className="text-emerald-500 not-italic">Planner.</span>
          </h1>
        </div>

        <div className="flex gap-1 bg-slate-900 p-1 rounded-xl border border-slate-600 mb-8">
          {(['login', 'register'] as const).map((m) => (
            <button key={m} type="button" onClick={() => { setMode(m); setError(''); setSuccess(''); }}
              className={`flex-1 py-2.5 rounded-lg text-[10px] font-black uppercase tracking-widest flex items-center justify-center gap-2 transition-all ${mode === m ? 'bg-emerald-600 text-white shadow-lg' : 'text-zinc-300 hover:text-zinc-300'}`}>
              {m === 'login' ? <><KeyRound size={12} /> Přihlášení</> : <><UserPlus size={12} /> Registrace</>}
            </button>
          ))}
        </div>

        <div aria-live="polite" aria-atomic="true">
        {(error || urlError) && (
          <div role="alert" className="flex items-center gap-3 bg-rose-500/10 border border-rose-500/20 text-rose-400 rounded-xl p-4 mb-6 text-xs font-bold">
            <AlertCircle size={16} className="shrink-0" />
            <span>{error || urlError?.replace(/_/g, ' ')}</span>
          </div>
        )}
        {success && (
          <div role="status" className="flex items-center gap-3 bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 rounded-xl p-4 mb-6 text-xs font-bold">
            <CheckCircle2 size={16} className="shrink-0" />
            <span>{success}</span>
          </div>
        )}
        </div>

        <form id="login-form" onSubmit={handleSubmit} className="space-y-4">
          <fieldset className="space-y-4 border-0 p-0 m-0">
            <legend className="sr-only">{mode === 'login' ? 'Přihlašovací údaje' : 'Registrační údaje'}</legend>
          <div className="space-y-1.5">
            <label className="text-[10px] font-black uppercase tracking-widest text-zinc-400">Uživatelské jméno</label>
            <div className="relative">
              <Mail size={16} className="absolute left-4 top-1/2 -translate-y-1/2 text-zinc-400" />
              <input required type="text" autoComplete="username" placeholder={mode === 'login' ? 'Jméno nebo email' : 'Zvolte uživatelské jméno'} value={form.username} onChange={e => update('username', e.target.value)}
                className="w-full bg-slate-900 border border-slate-600 rounded-xl h-12 pl-11 pr-4 text-sm font-bold text-white placeholder:text-zinc-400 focus:outline-none focus:ring-2 focus:ring-emerald-600/50" />
            </div>
          </div>

          {mode === 'register' && (
            <div className="space-y-1.5">
              <label className="text-[10px] font-black uppercase tracking-widest text-zinc-400">E-mail</label>
              <div className="relative">
                <Mail size={16} className="absolute left-4 top-1/2 -translate-y-1/2 text-zinc-400" />
                <input required type="email" autoComplete="email" placeholder="you@example.com" value={form.email} onChange={e => update('email', e.target.value)}
                  className="w-full bg-slate-900 border border-slate-600 rounded-xl h-12 pl-11 pr-4 text-sm font-bold text-white placeholder:text-zinc-400 focus:outline-none focus:ring-2 focus:ring-emerald-600/50" />
              </div>
            </div>
          )}

          <div className="space-y-1.5">
            <label className="text-[10px] font-black uppercase tracking-widest text-zinc-400">Heslo</label>
            <div className="relative">
              <KeyRound size={16} className="absolute left-4 top-1/2 -translate-y-1/2 text-zinc-400" />
              <input required type={showPassword ? 'text' : 'password'} autoComplete={mode === 'login' ? 'current-password' : 'new-password'} placeholder={mode === 'register' ? 'Min. 8 znaků, 1 písmeno, 1 číslice' : 'Zadejte heslo'} value={form.password} onChange={e => update('password', e.target.value)}
                className="w-full bg-slate-900 border border-slate-600 rounded-xl h-12 pl-11 pr-11 text-sm font-bold text-white placeholder:text-zinc-400 focus:outline-none focus:ring-2 focus:ring-emerald-600/50" />
              <button type="button" onClick={() => setShowPassword(!showPassword)} aria-label={showPassword ? 'Skrýt heslo' : 'Zobrazit heslo'} className="absolute right-4 top-1/2 -translate-y-1/2 text-zinc-400 hover:text-zinc-200">
                {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
              </button>
            </div>
          </div>

          {mode === 'register' && (
            <div className="space-y-1.5">
              <label className="text-[10px] font-black uppercase tracking-widest text-zinc-400">Potvrzení hesla</label>
              <div className="relative">
                <KeyRound size={16} className="absolute left-4 top-1/2 -translate-y-1/2 text-zinc-400" />
                <input required type={showPassword ? 'text' : 'password'} autoComplete="new-password" placeholder="Zadejte heslo znovu" value={form.passwordConfirm} onChange={e => update('passwordConfirm', e.target.value)}
                  className="w-full bg-slate-900 border border-slate-600 rounded-xl h-12 pl-11 pr-4 text-sm font-bold text-white placeholder:text-zinc-400 focus:outline-none focus:ring-2 focus:ring-emerald-600/50" />
              </div>
            </div>
          )}

          </fieldset>

          <button type="submit" disabled={isLoading}
            className="w-full bg-emerald-600 hover:bg-emerald-500 text-white h-14 rounded-xl font-black uppercase text-xs tracking-[0.2em] shadow-lg transition-all active:scale-[0.98] disabled:opacity-50 flex items-center justify-center gap-3 mt-6">
            {isLoading ? <Loader2 className="animate-spin" size={18} /> : mode === 'login' ? 'Přihlásit se' : 'Vytvořit účet'}
          </button>

          {mode === 'login' && (
            <div className="text-center mt-4">
              <Link to="/forgot-password" className="text-xs font-bold text-zinc-400 hover:text-emerald-400 transition-colors">
                Zapomněli jste heslo?
              </Link>
            </div>
          )}
        </form>

        <div className="flex items-center gap-4 my-8">
          <div className="flex-1 h-px bg-slate-600" />
          <span className="text-[9px] font-black text-zinc-300 uppercase tracking-widest">nebo</span>
          <div className="flex-1 h-px bg-slate-600" />
        </div>

        <button onClick={() => window.location.href = `${import.meta.env.VITE_API_URL || ''}/api/auth/google/login/`}
          className="w-full bg-white hover:bg-zinc-100 text-black h-12 rounded-xl font-black transition-all flex items-center justify-center gap-4 text-xs uppercase tracking-[0.15em] shadow-xl active:scale-[0.98]">
          <GoogleIcon /> Pokračovat přes Google
        </button>

        <p className="text-center text-[10px] text-zinc-400 mt-6">Přidejte se k 500+ lidem, kteří už plánují chytřeji.</p>
      </div>
    </div>
  );
};
