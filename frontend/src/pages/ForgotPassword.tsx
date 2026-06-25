import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useMutation } from '@tanstack/react-query';
import { Loader2, AlertCircle, CheckCircle2, Mail, ArrowLeft } from 'lucide-react';
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
    <div className="h-screen flex items-center justify-center p-6 bg-paper text-ink font-body relative overflow-hidden">
      <a href="#forgot-form" className="skip-to-content">
        Přejít na formulář
      </a>

      <div className="max-w-md w-full relative z-10 bg-card border border-line rounded-3xl shadow-deep-full p-12">
        <div className="text-center mb-10">
          <span className="font-display font-extrabold text-2xl tracking-tight text-ink lowercase">
            vařto<span className="text-paprika">.</span>
          </span>
          <h1 className="text-3xl font-black text-ink tracking-tighter leading-none uppercase italic mb-3 mt-6">
            Obnova <span className="text-green not-italic">hesla.</span>
          </h1>
          <p className="text-xs text-muted font-bold">Zadejte svůj e-mail a pošleme vám odkaz pro obnovu.</p>
        </div>

        <div aria-live="polite" aria-atomic="true">
        {error && (
          <div role="alert" className="flex items-center gap-3 bg-paprika-soft border border-paprika/20 text-paprika-strong rounded-xl p-4 mb-6 text-xs font-bold">
            <AlertCircle size={16} className="shrink-0" />
            <span>{error}</span>
          </div>
        )}
        {success && (
          <div role="status" className="flex items-center gap-3 bg-green-soft border border-green/20 text-green rounded-xl p-4 mb-6 text-xs font-bold">
            <CheckCircle2 size={16} className="shrink-0" />
            <span>{success}</span>
          </div>
        )}
        </div>

        <form id="forgot-form" onSubmit={handleSubmit} className="space-y-4">
          <fieldset className="space-y-4 border-0 p-0 m-0">
            <legend className="sr-only">Obnova hesla</legend>
          <div className="space-y-1.5">
            <label className="text-[10px] font-black uppercase tracking-widest text-muted">E-mail</label>
            <div className="relative">
              <Mail size={16} className="absolute left-4 top-1/2 -translate-y-1/2 text-muted" />
              <input
                required
                type="email"
                autoComplete="email"
                placeholder="you@example.com"
                value={email}
                onChange={e => setEmail(e.target.value)}
                className="w-full bg-paper border border-line rounded-xl h-12 pl-11 pr-4 text-sm font-bold text-ink placeholder:text-muted focus:outline-none"
              />
            </div>
          </div>

          </fieldset>

          <button
            type="submit"
            disabled={mutation.isPending}
            className="w-full bg-green hover:bg-green-mid text-white h-14 rounded-xl font-black uppercase text-xs tracking-[0.2em] shadow-lg transition-all active:scale-[0.98] disabled:opacity-50 flex items-center justify-center gap-3 mt-6"
          >
            {mutation.isPending ? <Loader2 className="animate-spin" size={18} /> : 'Odeslat odkaz pro obnovu'}
          </button>
        </form>

        <div className="text-center mt-8">
          <Link to="/login" className="text-xs font-bold text-muted hover:text-green transition-colors inline-flex items-center gap-2">
            <ArrowLeft size={14} /> Zpět na přihlášení
          </Link>
        </div>
      </div>
    </div>
  );
};
