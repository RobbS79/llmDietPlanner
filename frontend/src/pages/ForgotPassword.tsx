import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useMutation } from '@tanstack/react-query';
import { Zap, Loader2, AlertCircle, CheckCircle2, Mail, ArrowLeft } from 'lucide-react';
import axios from 'axios';

export const ForgotPassword = () => {
  const [email, setEmail] = useState('');
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  const mutation = useMutation({
    mutationFn: (data: { email: string }) => axios.post('/api/auth/password-reset/', data),
    onSuccess: () => {
      setSuccess('If an account with that email exists, a reset link has been sent. Check your inbox.');
      setError('');
    },
    onError: (err: any) => setError(err.response?.data?.error || 'Something went wrong. Please try again.'),
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setSuccess('');
    mutation.mutate({ email });
  };

  return (
    <div className="h-screen flex items-center justify-center p-6 bg-[#09090b] relative overflow-hidden">
      <div className="absolute top-0 left-0 w-full h-full pointer-events-none">
        <div className="absolute top-[-15%] left-[-15%] w-[800px] h-[800px] bg-indigo-600/[0.04] blur-[180px] rounded-full animate-pulse" />
        <div className="absolute bottom-[-15%] right-[-15%] w-[900px] h-[900px] bg-purple-600/[0.02] blur-[220px] rounded-full animate-pulse delay-1000" />
      </div>

      <div className="max-w-md w-full relative z-10 bg-zinc-900/50 border border-zinc-800 rounded-[3rem] shadow-[0_50px_100px_-20px_rgba(0,0,0,1)] p-12">
        <div className="text-center mb-10">
          <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-gradient-to-br from-indigo-600 to-indigo-400 text-white mb-6 shadow-[0_0_30px_rgba(37,99,235,0.3)]">
            <Zap size={32} fill="currentColor" />
          </div>
          <h1 className="text-3xl font-black text-white tracking-tighter leading-none uppercase italic mb-3">
            Obnova <span className="text-indigo-500 not-italic">hesla.</span>
          </h1>
          <p className="text-xs text-zinc-600 font-bold">Zadejte svuj e-mail a posleme vam odkaz pro obnovu.</p>
        </div>

        {error && (
          <div className="flex items-center gap-3 bg-rose-500/10 border border-rose-500/20 text-rose-400 rounded-xl p-4 mb-6 text-xs font-bold">
            <AlertCircle size={16} className="shrink-0" />
            <span>{error}</span>
          </div>
        )}
        {success && (
          <div className="flex items-center gap-3 bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 rounded-xl p-4 mb-6 text-xs font-bold">
            <CheckCircle2 size={16} className="shrink-0" />
            <span>{success}</span>
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-1.5">
            <label className="text-[10px] font-black uppercase tracking-widest text-zinc-600">E-mail</label>
            <div className="relative">
              <Mail size={16} className="absolute left-4 top-1/2 -translate-y-1/2 text-zinc-600" />
              <input
                required
                type="email"
                autoComplete="email"
                placeholder="you@example.com"
                value={email}
                onChange={e => setEmail(e.target.value)}
                className="w-full bg-zinc-950 border border-zinc-800 rounded-xl h-12 pl-11 pr-4 text-sm font-bold text-white placeholder:text-zinc-600 focus:outline-none focus:ring-2 focus:ring-indigo-600/50"
              />
            </div>
          </div>

          <button
            type="submit"
            disabled={mutation.isPending}
            className="w-full bg-indigo-600 hover:bg-indigo-500 text-white h-14 rounded-xl font-black uppercase text-[11px] tracking-[0.2em] shadow-lg transition-all active:scale-[0.98] disabled:opacity-50 flex items-center justify-center gap-3 mt-6"
          >
            {mutation.isPending ? <Loader2 className="animate-spin" size={18} /> : 'Odeslat odkaz pro obnovu'}
          </button>
        </form>

        <div className="text-center mt-8">
          <Link to="/login" className="text-xs font-bold text-zinc-600 hover:text-indigo-400 transition-colors inline-flex items-center gap-2">
            <ArrowLeft size={14} /> Zpet na prihlaseni
          </Link>
        </div>
      </div>
    </div>
  );
};
