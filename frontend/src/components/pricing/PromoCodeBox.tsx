import { useState } from 'react';
import { Loader2, Tag, X } from 'lucide-react';
import { PROMO_REASON_TEXT, validPromoMessage, type PromoValidation } from '@/lib/promo';

interface Props {
  code: string;
  onCodeChange: (v: string) => void;
  validation: PromoValidation | null;
  checking: boolean;
  onApply: () => void;
  onClear: () => void;
}

/** "Mám promo kód" input + result line, rendered under the plan cards. */
export function PromoCodeBox({ code, onCodeChange, validation, checking, onApply, onClear }: Props) {
  const [open, setOpen] = useState(!!code);
  const applied = validation?.valid === true;

  if (!open) {
    return (
      <div className="text-center mb-16">
        <button
          type="button"
          onClick={() => setOpen(true)}
          className="text-xs font-bold text-muted hover:text-green transition-colors inline-flex items-center gap-2"
        >
          <Tag size={14} /> Mám promo kód
        </button>
      </div>
    );
  }

  return (
    <div className="max-w-md mx-auto mb-16">
      <form
        onSubmit={(e) => { e.preventDefault(); onApply(); }}
        className="flex gap-2"
      >
        <input
          value={code}
          onChange={(e) => onCodeChange(e.target.value)}
          placeholder="Promo kód"
          autoCapitalize="characters"
          disabled={applied}
          className="flex-1 h-12 rounded-xl border border-line bg-card px-4 text-sm font-bold uppercase tracking-widest text-ink disabled:opacity-70"
        />
        {applied ? (
          <button type="button" onClick={onClear} aria-label="Zrušit kód"
            className="h-12 px-4 rounded-xl border border-line text-muted hover:text-ink">
            <X size={16} />
          </button>
        ) : (
          <button type="submit" disabled={checking || !code.trim()}
            className="h-12 px-6 rounded-xl bg-green hover:bg-green-mid text-white font-bold text-sm disabled:opacity-60 inline-flex items-center gap-2">
            {checking && <Loader2 size={14} className="animate-spin" />} Použít
          </button>
        )}
      </form>
      {validation && (
        <p className={`mt-3 text-center text-sm font-bold ${validation.valid ? 'text-green' : 'text-paprika-strong'}`}>
          {validation.valid
            ? validPromoMessage(validation)
            : PROMO_REASON_TEXT[validation.reason]}
        </p>
      )}
    </div>
  );
}
