import { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { AlertCircle, CheckCircle2, Loader2, Mail } from 'lucide-react';
import { Card } from '@/components/ui/Card';
import { useToast } from '@/components/ui/Toast';
import { changePassword, deleteAccountWithPassword, extractApiError, type Profile } from '@/lib/settings';
import { clearAuthTokens } from '@/lib/auth';

const SUPPORT_EMAIL = 'admin@kentakin.eu';

export function AccountSection({ profile }: { profile: Profile }) {
  const isEmailUser = profile.primary_auth_provider === 'email';
  const [deleteOpen, setDeleteOpen] = useState(false);

  return (
    <Card variant="paper" className="p-8 space-y-8">
      <h2 className="font-display text-xl font-black text-ink uppercase italic tracking-tight">Účet</h2>

      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-line pb-6">
        <div>
          <label className="text-[10px] font-black uppercase tracking-widest text-muted block mb-1.5">Přihlašovací metoda</label>
          <span className="text-sm font-bold text-ink">{isEmailUser ? 'E-mail' : 'Google'}</span>
        </div>
        <div className={`inline-flex items-center gap-2 rounded-full px-4 py-1.5 border ${
          profile.email_verified ? 'bg-green-soft border-green/40' : 'bg-paprika-soft border-paprika/30'
        }`}>
          {profile.email_verified
            ? <CheckCircle2 size={14} className="text-green" />
            : <AlertCircle size={14} className="text-paprika-strong" />}
          <span className={`text-[10px] font-black uppercase tracking-widest ${profile.email_verified ? 'text-green' : 'text-paprika-strong'}`}>
            {profile.email_verified ? 'Ověřeno' : 'Neověřeno'}
          </span>
        </div>
      </div>

      {isEmailUser && <ChangePasswordForm />}

      <div className="pt-2">
        {isEmailUser ? (
          <button
            type="button"
            onClick={() => setDeleteOpen(true)}
            className="px-6 h-12 bg-transparent border border-paprika/40 text-paprika-strong hover:bg-paprika-soft rounded-xl font-black uppercase text-[10px] tracking-widest transition-all"
          >
            Smazat účet
          </button>
        ) : (
          <div className="bg-kraft border border-line rounded-xl p-4 text-xs font-bold text-muted flex items-start gap-3">
            <Mail size={16} className="shrink-0 mt-0.5 text-muted" />
            <span>
              Účet vytvořený přes Google smažeme na vaši žádost. Napište nám na{' '}
              <a href={`mailto:${SUPPORT_EMAIL}`} className="text-green hover:text-green-mid underline">{SUPPORT_EMAIL}</a>.
            </span>
          </div>
        )}
      </div>

      {deleteOpen && <DeleteAccountModal onClose={() => setDeleteOpen(false)} />}
    </Card>
  );
}

function ChangePasswordForm() {
  const toast = useToast();
  const [oldPw, setOldPw] = useState('');
  const [newPw1, setNewPw1] = useState('');
  const [newPw2, setNewPw2] = useState('');
  const [error, setError] = useState('');

  const mutation = useMutation({
    mutationFn: () => changePassword(oldPw, newPw1),
    onSuccess: () => {
      toast.success('Heslo změněno');
      setError('');
      setOldPw('');
      setNewPw1('');
      setNewPw2('');
    },
    onError: (err: unknown) => setError(extractApiError(err, 'Heslo se nepodařilo změnit.')),
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (newPw1 !== newPw2) {
      setError('Nová hesla se neshodují.');
      return;
    }
    if (newPw1.length < 8) {
      setError('Nové heslo musí mít alespoň 8 znaků.');
      return;
    }
    setError('');
    mutation.mutate();
  };

  return (
    <form onSubmit={handleSubmit} className="border-b border-line pb-6 space-y-4">
      <h3 className="text-[10px] font-black uppercase tracking-widest text-muted">Změnit heslo</h3>

      {error && (
        <div role="alert" className="flex items-center gap-3 bg-paprika-soft border border-paprika/20 text-paprika-strong rounded-xl p-4 text-xs font-bold">
          <AlertCircle size={16} className="shrink-0" />
          <span>{error}</span>
        </div>
      )}

      <div className="grid sm:grid-cols-3 gap-4">
        <div className="space-y-1.5">
          <label className="text-[10px] font-black uppercase tracking-widest text-muted">Současné heslo</label>
          <input
            type="password"
            autoComplete="current-password"
            value={oldPw}
            onChange={e => setOldPw(e.target.value)}
            className="w-full bg-paper border border-line rounded-xl h-12 px-4 text-sm font-bold text-ink focus:outline-none"
          />
        </div>
        <div className="space-y-1.5">
          <label className="text-[10px] font-black uppercase tracking-widest text-muted">Nové heslo</label>
          <input
            type="password"
            autoComplete="new-password"
            value={newPw1}
            onChange={e => setNewPw1(e.target.value)}
            className="w-full bg-paper border border-line rounded-xl h-12 px-4 text-sm font-bold text-ink focus:outline-none"
          />
        </div>
        <div className="space-y-1.5">
          <label className="text-[10px] font-black uppercase tracking-widest text-muted">Nové heslo znovu</label>
          <input
            type="password"
            autoComplete="new-password"
            value={newPw2}
            onChange={e => setNewPw2(e.target.value)}
            className="w-full bg-paper border border-line rounded-xl h-12 px-4 text-sm font-bold text-ink focus:outline-none"
          />
        </div>
      </div>

      <button
        type="submit"
        disabled={mutation.isPending}
        className="flex items-center gap-3 px-8 h-12 bg-green hover:bg-green-mid text-white rounded-xl font-black uppercase text-[10px] tracking-widest transition-all active:scale-[0.98] disabled:opacity-50"
      >
        {mutation.isPending && <Loader2 size={14} className="animate-spin" />}
        Uložit nové heslo
      </button>
    </form>
  );
}

function DeleteAccountModal({ onClose }: { onClose: () => void }) {
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');

  const mutation = useMutation({
    mutationFn: () => deleteAccountWithPassword(password),
    onSuccess: () => {
      clearAuthTokens();
      window.location.href = '/';
    },
    onError: (err: unknown) => setError(extractApiError(err, 'Účet se nepodařilo smazat.')),
  });

  const handleConfirm = () => {
    if (mutation.isPending) return; // guard against double-submit
    mutation.mutate();
  };

  return (
    <div className="fixed inset-0 bg-ink/40 flex items-center justify-center z-[200] p-6">
      <div className="bg-card rounded-3xl p-8 max-w-md w-full space-y-6 shadow-2xl">
        <div>
          <h3 className="font-display text-xl font-black text-ink uppercase italic tracking-tight mb-3">Opravdu smazat účet?</h3>
          <p className="text-sm text-muted">
            Tato akce je nevratná. Trvale smažeme váš profil, jídelníčky a všechna data. Pokud máte aktivní předplatné,
            bude okamžitě zrušeno — zbývající období propadá bez vrácení peněz.
          </p>
        </div>

        {error && (
          <div role="alert" className="flex items-center gap-3 bg-paprika-soft border border-paprika/20 text-paprika-strong rounded-xl p-4 text-xs font-bold">
            <AlertCircle size={16} className="shrink-0" />
            <span>{error}</span>
          </div>
        )}

        <div className="space-y-1.5">
          <label className="text-[10px] font-black uppercase tracking-widest text-muted">Pro potvrzení zadejte heslo</label>
          <input
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={e => setPassword(e.target.value)}
            className="w-full bg-paper border border-line rounded-xl h-12 px-4 text-sm font-bold text-ink focus:outline-none"
          />
        </div>

        <div className="flex gap-3">
          <button
            type="button"
            onClick={onClose}
            disabled={mutation.isPending}
            className="flex-1 h-12 border border-line text-ink hover:bg-kraft rounded-xl font-black uppercase text-[10px] tracking-widest transition-all disabled:opacity-50"
          >
            Zrušit
          </button>
          <button
            type="button"
            onClick={handleConfirm}
            disabled={mutation.isPending || !password}
            className="flex-1 flex items-center justify-center gap-2 h-12 bg-paprika hover:bg-paprika-strong text-white rounded-xl font-black uppercase text-[10px] tracking-widest transition-all disabled:opacity-50"
          >
            {mutation.isPending && <Loader2 size={14} className="animate-spin" />}
            Trvale smazat
          </button>
        </div>
      </div>
    </div>
  );
}
