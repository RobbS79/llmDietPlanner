import { Loader2, Zap } from 'lucide-react';
import { StatusTracker } from './StatusTracker';

export const LoadingScreen = ({ message, status }: { message: string; status?: any }) => {
  const currentStatus = status?.goal_status || 'pending';
  const stepMessages: Record<string, string> = {
    pending: 'Analyzujeme vaše stravovací cíle a preference...',
    awaiting_payment: 'Analyzujeme vaše stravovací cíle a preference...',
    payment_confirmed: 'Vytváříme personalizovaný jídelníček s recepty...',
    processing: 'Vytváříme personalizovaný jídelníček s recepty...',
    processing_meal_plan: 'Vytváříme personalizovaný jídelníček s recepty...',
    processing_shopping_list: 'Hledáme nejlepší ceny z vašeho obchodu...',
    validating: 'Ověřujeme nutriční hodnoty a finalizujeme plán...',
  };

  const displayMessage = status ? (stepMessages[currentStatus] || message) : message;

  return (
    <div className="flex-1 flex flex-col items-center justify-center p-8 text-center bg-[#09090b]" role="status" aria-live="polite">
      <div className="relative mb-12 flex items-center justify-center">
        <div className="absolute inset-0 bg-emerald-600/10 blur-[80px] rounded-full" />
        <Loader2 className="animate-spin text-emerald-500 relative z-10" size={100} strokeWidth={1} />
        <div className="absolute inset-0 flex items-center justify-center">
          <Zap size={28} className="text-emerald-400 animate-pulse" />
        </div>
      </div>
      <div className="space-y-3 relative z-10">
        <h2 className="text-4xl font-black text-white tracking-tighter uppercase italic leading-none">Generujeme<span className="text-emerald-500 animate-pulse">...</span></h2>
        <p className="text-zinc-500 text-[10px] font-bold uppercase tracking-widest italic max-w-sm mx-auto leading-relaxed">{displayMessage}</p>
      </div>
      {status && (
        <div className="mt-8 w-full max-w-xs mx-auto">
          <div className="h-1 bg-zinc-800 rounded-full overflow-hidden mb-2">
            <div
              className="h-full bg-gradient-to-r from-emerald-600 to-emerald-400 rounded-full transition-all duration-1000 ease-out"
              style={{ width: `${Math.min(((['pending', 'awaiting_payment'].includes(currentStatus) ? 1 : ['payment_confirmed', 'processing', 'processing_meal_plan'].includes(currentStatus) ? 2 : ['processing_shopping_list'].includes(currentStatus) ? 3 : ['validating'].includes(currentStatus) ? 4 : 5) / 5) * 100, 100)}%` }}
            />
          </div>
          <StatusTracker statusData={status} />
        </div>
      )}
    </div>
  );
};
