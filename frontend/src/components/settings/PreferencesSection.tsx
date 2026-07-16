import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { AlertCircle, Check, Loader2 } from 'lucide-react';
import { Card } from '@/components/ui/Card';
import { useToast } from '@/components/ui/Toast';
import { savePreferences, extractApiError, type Profile } from '@/lib/settings';
import {
  GOALS,
  DIETARY_STYLES,
  ALLERGIES,
  COOKING_SKILLS,
  COOKING_TIMES,
  DEFAULT_PREFERENCES,
  toggleMultiValue,
  type Preferences,
} from '@/lib/preferences';

type PrefsState = Preferences & { num_days: number };

const DEFAULT_NUM_DAYS = 7;

function seedFromProfile(profile: Profile): PrefsState {
  const saved = profile.dietary_preferences;
  const num_days = typeof saved.num_days === 'number' ? saved.num_days : DEFAULT_NUM_DAYS;
  return { ...DEFAULT_PREFERENCES, ...saved, num_days };
}

export function PreferencesSection({ profile }: { profile: Profile }) {
  const toast = useToast();
  const queryClient = useQueryClient();
  const [data, setData] = useState<PrefsState>(() => seedFromProfile(profile));
  const [error, setError] = useState('');
  // Separate raw text for the num_days input so the user can clear the field
  // while typing without `data.num_days` ever going NaN in between keystrokes.
  const [numDaysText, setNumDaysText] = useState(() => String(seedFromProfile(profile).num_days));

  const update = <K extends keyof PrefsState>(field: K, value: PrefsState[K]) =>
    setData(prev => ({ ...prev, [field]: value }));

  const toggleMulti = (field: 'dietary_styles' | 'allergies', id: string) => {
    setData(prev => ({ ...prev, [field]: toggleMultiValue(prev[field], id) }));
  };

  const mutation = useMutation({
    mutationFn: () => {
      // Defensive: guarantee an integer 1–30 lands in the payload even if
      // `data.num_days` were somehow left in a transient/invalid state.
      const num_days = Number.isFinite(data.num_days)
        ? Math.min(30, Math.max(1, Math.round(data.num_days)))
        : DEFAULT_NUM_DAYS;
      const payload: Record<string, unknown> = { ...data, num_days };
      return savePreferences(payload);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['profile'] });
      toast.success('Předvolby uloženy');
      setError('');
    },
    onError: (err: unknown) => setError(extractApiError(err, 'Nepodařilo se uložit předvolby.')),
  });

  return (
    <Card variant="paper" className="p-8 space-y-8">
      <h2 className="font-display text-xl font-black text-ink uppercase italic tracking-tight">Předvolby</h2>

      {error && (
        <div role="alert" className="flex items-center gap-3 bg-paprika-soft border border-paprika/20 text-paprika-strong rounded-xl p-4 text-xs font-bold">
          <AlertCircle size={16} className="shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* Goal — single-select card grid (Onboarding.tsx:161-172 pattern) */}
      <div>
        <label className="text-[10px] font-black uppercase tracking-widest text-muted mb-4 block">Cíl</label>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {GOALS.map(g => (
            <button key={g.id} type="button" onClick={() => update('goal', g.id)}
              className={`p-5 rounded-2xl border-2 transition-all text-left ${
                data.goal === g.id ? 'bg-green-soft border-green text-ink shadow-lg' : 'bg-paper border-transparent text-muted hover:text-muted'
              }`}>
              <span className="text-xl mb-2 block">{g.icon}</span>
              <span className="font-black uppercase text-xs tracking-tight block">{g.label}</span>
            </button>
          ))}
        </div>
      </div>

      {/* Dietary styles — multi-select pills (Onboarding.tsx:180-189 pattern) */}
      <div>
        <label className="text-[10px] font-black uppercase tracking-widest text-muted mb-4 block">Stravovací styl</label>
        <div className="flex flex-wrap gap-3">
          {DIETARY_STYLES.map(s => (
            <button key={s.id} type="button" onClick={() => toggleMulti('dietary_styles', s.id)}
              className={`px-5 py-3 rounded-xl text-sm font-bold transition-all border ${
                data.dietary_styles.includes(s.id) ? 'bg-green-soft border-green text-green' : 'bg-paper border-line text-muted hover:text-muted'
              }`}>
              {data.dietary_styles.includes(s.id) && <Check size={14} className="inline mr-2" />}{s.label}
            </button>
          ))}
        </div>
      </div>

      {/* Allergies — multi-select pills */}
      <div>
        <label className="text-[10px] font-black uppercase tracking-widest text-muted mb-4 block">Alergie</label>
        <div className="flex flex-wrap gap-3">
          {ALLERGIES.map(a => (
            <button key={a.id} type="button" onClick={() => toggleMulti('allergies', a.id)}
              className={`px-5 py-3 rounded-xl text-sm font-bold transition-all border ${
                data.allergies.includes(a.id) ? 'bg-green-soft border-green text-green' : 'bg-paper border-line text-muted hover:text-muted'
              }`}>
              {data.allergies.includes(a.id) && <Check size={14} className="inline mr-2" />}{a.label}
            </button>
          ))}
        </div>
      </div>

      {/* Household + budget */}
      <div className="grid sm:grid-cols-2 gap-8">
        <div>
          <label className="text-[10px] font-black uppercase tracking-widest text-muted mb-4 block">Počet osob</label>
          <div className="flex flex-wrap gap-2.5">
            {[1, 2, 3, 4, 5, 6].map(n => (
              <button key={n} type="button" onClick={() => update('household_size', n)}
                className={`px-4 py-2.5 rounded-xl text-[10px] font-black uppercase tracking-widest transition-all border border-line ${
                  data.household_size === n ? 'bg-green text-white shadow-lg border-green' : 'bg-paper text-muted hover:text-ink'
                }`}>
                {n}{n === 6 ? '+' : ''}
              </button>
            ))}
          </div>
        </div>

        <div>
          <div className="flex justify-between items-end mb-4">
            <label className="text-[10px] font-black uppercase tracking-widest text-muted">Týdenní rozpočet</label>
            <span className="text-lg font-black text-green italic">
              {data.weekly_budget.toLocaleString('cs-CZ')} {data.country === 'SK' ? 'EUR' : 'CZK'}
            </span>
          </div>
          <input type="range"
            min={data.country === 'SK' ? 20 : 500}
            max={data.country === 'SK' ? 200 : 5000}
            step={data.country === 'SK' ? 5 : 100}
            value={data.weekly_budget}
            onChange={e => update('weekly_budget', parseInt(e.target.value, 10))}
            className="w-full h-2 bg-kraft rounded-full appearance-none accent-green cursor-pointer"
          />
        </div>
      </div>

      {/* Cooking skill */}
      <div>
        <label className="text-[10px] font-black uppercase tracking-widest text-muted mb-4 block">Úroveň vaření</label>
        <div className="grid sm:grid-cols-3 gap-3">
          {COOKING_SKILLS.map(s => (
            <button key={s.id} type="button" onClick={() => update('cooking_skill', s.id)}
              className={`p-4 rounded-2xl border-2 transition-all text-left ${
                data.cooking_skill === s.id ? 'bg-green-soft border-green text-ink' : 'bg-paper border-transparent text-muted hover:text-muted'
              }`}>
              <span className="font-black uppercase text-xs tracking-tight block">{s.label}</span>
            </button>
          ))}
        </div>
      </div>

      {/* Cooking time */}
      <div>
        <label className="text-[10px] font-black uppercase tracking-widest text-muted mb-4 block">Čas na přípravu</label>
        <div className="flex flex-wrap gap-3">
          {COOKING_TIMES.map(t => (
            <button key={t.id} type="button" onClick={() => update('cooking_time', t.id)}
              className={`px-5 py-3 rounded-xl text-sm font-bold transition-all border ${
                data.cooking_time === t.id ? 'bg-green-soft border-green text-green' : 'bg-paper border-line text-muted hover:text-muted'
              }`}>
              {t.label}
            </button>
          ))}
        </div>
      </div>

      {/* Country + plan length */}
      <div className="grid sm:grid-cols-2 gap-8">
        <div>
          <label className="text-[10px] font-black uppercase tracking-widest text-muted mb-4 block">Země</label>
          <div className="flex gap-2.5">
            {['CZ', 'SK'].map(c => (
              <button key={c} type="button" onClick={() => update('country', c)}
                className={`px-5 py-2.5 rounded-xl text-[10px] font-black uppercase tracking-widest transition-all border border-line ${
                  data.country === c ? 'bg-green text-white shadow-lg border-green' : 'bg-paper text-muted hover:text-ink'
                }`}>
                {c}
              </button>
            ))}
          </div>
        </div>

        <div>
          <label className="text-[10px] font-black uppercase tracking-widest text-muted mb-4 block">Počet dní jídelníčku</label>
          <input
            type="number"
            min={1}
            max={30}
            value={numDaysText}
            onChange={e => {
              const raw = e.target.value;
              setNumDaysText(raw);
              if (raw === '') {
                // Let the field show empty while the user is editing, but
                // never let the underlying save-state go NaN in the meantime.
                update('num_days', DEFAULT_NUM_DAYS);
                return;
              }
              const n = parseInt(raw, 10);
              if (!Number.isNaN(n)) update('num_days', Math.min(30, Math.max(1, n)));
            }}
            onBlur={() => {
              if (numDaysText === '' || Number.isNaN(parseInt(numDaysText, 10))) {
                setNumDaysText(String(DEFAULT_NUM_DAYS));
                update('num_days', DEFAULT_NUM_DAYS);
              }
            }}
            className="w-full bg-paper border border-line rounded-xl h-12 px-4 text-sm font-bold text-ink focus:outline-none"
          />
        </div>
      </div>

      <button
        type="button"
        onClick={() => mutation.mutate()}
        disabled={mutation.isPending}
        className="flex items-center gap-3 px-8 h-12 bg-green hover:bg-green-mid text-white rounded-xl font-black uppercase text-[10px] tracking-widest transition-all active:scale-[0.98] disabled:opacity-50"
      >
        {mutation.isPending && <Loader2 size={14} className="animate-spin" />}
        Uložit předvolby
      </button>
    </Card>
  );
}
