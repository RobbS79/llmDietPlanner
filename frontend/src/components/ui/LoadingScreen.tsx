import { useState, useEffect } from 'react';
import { Loader2, Zap, RotateCcw } from 'lucide-react';
import { StatusTracker } from './StatusTracker';
import { api } from '@/lib/api';

export const LoadingScreen = ({ message, status, goalId }: { message: string; status?: any; goalId?: string }) => {
  const currentStatus = status?.goal_status || 'pending';
  const [elapsed, setElapsed] = useState(0);
  const [retrying, setRetrying] = useState(false);

  useEffect(() => {
    const interval = setInterval(() => setElapsed(e => e + 1), 1000);
    return () => clearInterval(interval);
  }, []);

  const handleRetry = async () => {
    if (!goalId || retrying) return;
    setRetrying(true);
    try {
      await api.post(`/goals/${goalId}/admin-retry/`, { action: 'retry' });
      setElapsed(0);
    } catch {
      // fall through
    } finally {
      setTimeout(() => setRetrying(false), 3000);
    }
  };

  const stepMessages: Record<string, string> = {
    pending: 'Analyzujeme vaše stravovací cíle a preference...',
    awaiting_payment: 'Analyzujeme vaše stravovací cíle a preference...',
    payment_confirmed: 'Vytváříme personalizovaný jídelníček s recepty...',
    processing: 'Vytváříme personalizovaný jídelníček s recepty...',
    processing_meal_plan: 'Vytváříme personalizovaný jídelníček s recepty...',
    processing_shopping_list: 'Počítáme odhad ceny receptů...',
    validating: 'Ověřujeme nutriční hodnoty a finalizujeme plán...',
  };

  const displayMessage = status ? (stepMessages[currentStatus] || message) : message;
  const isStuck = elapsed > 120;

  return (
    <div className="flex-1 flex flex-col items-center justify-center p-8 text-center bg-paper" role="status" aria-live="polite">
      <div className="relative mb-12 flex items-center justify-center">
        <div className="absolute inset-0 bg-green-soft blur-[80px] rounded-full" />
        <Loader2 className="animate-spin text-green relative z-10" size={100} strokeWidth={1} />
        <div className="absolute inset-0 flex items-center justify-center">
          <Zap size={28} className="text-green animate-pulse" />
        </div>
      </div>
      <div className="space-y-3 relative z-10">
        <h2 className="text-4xl font-display font-black text-ink tracking-tighter uppercase italic leading-none">Generujeme<span className="text-green animate-pulse">...</span></h2>
        <p className="text-muted text-[10px] font-bold uppercase tracking-widest italic max-w-sm mx-auto leading-relaxed">{displayMessage}</p>
      </div>
      {status && (
        <div className="mt-8 w-full max-w-xs mx-auto">
          <div className="h-1 bg-kraft rounded-full overflow-hidden mb-2">
            <div
              className="h-full bg-gradient-to-r from-green to-green-mid rounded-full transition-all duration-1000 ease-out"
              style={{ width: `${Math.min(((['pending', 'awaiting_payment'].includes(currentStatus) ? 1 : ['payment_confirmed', 'processing', 'processing_meal_plan'].includes(currentStatus) ? 2 : ['processing_shopping_list'].includes(currentStatus) ? 3 : ['validating'].includes(currentStatus) ? 4 : 5) / 5) * 100, 100)}%` }}
            />
          </div>
          <StatusTracker statusData={status} />
        </div>
      )}
      {isStuck && goalId && (
        <div className="mt-10 space-y-3">
          <p className="text-muted text-xs font-bold">Generování trvá déle než obvykle.</p>
          <button
            onClick={handleRetry}
            disabled={retrying}
            className="flex items-center gap-2 mx-auto px-6 h-12 bg-green hover:bg-green-mid text-white rounded-xl font-black uppercase text-[10px] tracking-widest transition-all disabled:opacity-40"
          >
            <RotateCcw size={14} className={retrying ? 'animate-spin' : ''} />
            {retrying ? 'Obnovujeme...' : 'Zkusit znovu'}
          </button>
        </div>
      )}
    </div>
  );
};
