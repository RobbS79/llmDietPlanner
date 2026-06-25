import { useState } from 'react';
import { useSearchParams, Link, useNavigate } from 'react-router-dom';
import { useMutation } from '@tanstack/react-query';
import { Loader2, AlertCircle, CheckCircle2, KeyRound, Eye, EyeOff } from 'lucide-react';
import axios from 'axios';

export const ResetPassword = () => {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const uid = searchParams.get('uid') || '';
  const token = searchParams.get('token') || '';

  const [password, setPassword] = useState('');
  const [passwordConfirm, setPasswordConfirm] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  const mutation = useMutation({
    mutationFn: (data: { uid: string; token: string; password: string; passwordConfirm: string }) =>
      axios.post('/api/auth/password-reset-confirm/', data),
    onSuccess: () => {
      setSuccess('Password reset successfully! Redirecting to login...');
      setError('');
      setTimeout(() => navigate('/login'), 2000);
    },
    onError: (err: any) => setError(err.response?.data?.error || 'Failed to reset password. The link may have expired.'),
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    if (password !== passwordConfirm) {
      setError('Passwords do not match');
      return;
    }
    mutation.mutate({ uid, token, password, passwordConfirm });
  };

  if (!uid || !token) {
    return (
      <div className="h-screen flex items-center justify-center p-6 bg-paper text-ink font-body">
        <div className="max-w-md w-full text-center bg-card border border-line rounded-3xl p-12">
          <AlertCircle size={48} className="text-paprika mx-auto mb-6" />
          <h1 className="text-2xl font-black text-ink mb-4">Neplatný odkaz</h1>
          <p className="text-muted text-sm mb-8">Tento odkaz pro obnovu hesla je neplatný nebo vypršel.</p>
          <Link to="/forgot-password" className="text-green font-bold text-sm hover:text-green-mid">Požádat o nový odkaz</Link>
        </div>
      </div>
    );
  }

  return (
    <div className="h-screen flex items-center justify-center p-6 bg-paper text-ink font-body relative overflow-hidden">
      <a href="#reset-form" className="skip-to-content">
        Přejít na formulář
      </a>

      <div className="max-w-md w-full relative z-10 bg-card border border-line rounded-3xl shadow-deep-full p-12">
        <div className="text-center mb-10">
          <span className="font-display font-extrabold text-2xl tracking-tight text-ink lowercase">
            vařto<span className="text-paprika">.</span>
          </span>
          <h1 className="text-3xl font-black text-ink tracking-tighter leading-none uppercase italic mb-3 mt-6">
            Nové <span className="text-green not-italic">heslo.</span>
          </h1>
          <p className="text-xs text-muted font-bold">Zvolte si nové heslo pro svůj účet.</p>
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

        <form id="reset-form" onSubmit={handleSubmit} className="space-y-4">
          <fieldset className="space-y-4 border-0 p-0 m-0">
            <legend className="sr-only">Nastavení nového hesla</legend>
          <div className="space-y-1.5">
            <label className="text-[10px] font-black uppercase tracking-widest text-muted">Nové heslo</label>
            <div className="relative">
              <KeyRound size={16} className="absolute left-4 top-1/2 -translate-y-1/2 text-muted" />
              <input
                required
                type={showPassword ? 'text' : 'password'}
                autoComplete="new-password"
                placeholder="Min 8 chars, 1 letter, 1 digit"
                value={password}
                onChange={e => setPassword(e.target.value)}
                className="w-full bg-paper border border-line rounded-xl h-12 pl-11 pr-11 text-sm font-bold text-ink placeholder:text-muted focus:outline-none"
              />
              <button type="button" onClick={() => setShowPassword(!showPassword)} aria-label={showPassword ? 'Skrýt heslo' : 'Zobrazit heslo'} className="absolute right-4 top-1/2 -translate-y-1/2 text-muted hover:text-ink">
                {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
              </button>
            </div>
          </div>

          <div className="space-y-1.5">
            <label className="text-[10px] font-black uppercase tracking-widest text-muted">Potvrzení hesla</label>
            <div className="relative">
              <KeyRound size={16} className="absolute left-4 top-1/2 -translate-y-1/2 text-muted" />
              <input
                required
                type={showPassword ? 'text' : 'password'}
                autoComplete="new-password"
                placeholder="Re-enter new password"
                value={passwordConfirm}
                onChange={e => setPasswordConfirm(e.target.value)}
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
            {mutation.isPending ? <Loader2 className="animate-spin" size={18} /> : 'Nastavit nové heslo'}
          </button>
        </form>

        <div className="text-center mt-8">
          <Link to="/login" className="text-xs font-bold text-muted hover:text-green transition-colors">
            Zpět na přihlášení
          </Link>
        </div>
      </div>
    </div>
  );
};
