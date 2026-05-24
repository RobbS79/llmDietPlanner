import { Loader2, Zap } from 'lucide-react';
import { StatusTracker } from './StatusTracker';

export const LoadingScreen = ({ message, status }: { message: string; status?: any }) => (
  <div className="flex-1 flex flex-col items-center justify-center p-8 text-center bg-[#09090b]">
    <div className="relative mb-12 flex items-center justify-center">
      <div className="absolute inset-0 bg-indigo-600/10 blur-[80px] rounded-full" />
      <Loader2 className="animate-spin text-indigo-500 relative z-10" size={100} strokeWidth={1} />
      <div className="absolute inset-0 flex items-center justify-center">
        <Zap size={28} className="text-indigo-400 animate-pulse" />
      </div>
    </div>
    <div className="space-y-3 relative z-10">
      <h2 className="text-4xl font-black text-white tracking-tighter uppercase italic leading-none">Generating<span className="text-indigo-500 animate-pulse">...</span></h2>
      <p className="text-zinc-500 text-[10px] font-bold uppercase tracking-widest italic max-w-sm mx-auto leading-relaxed">{message}</p>
    </div>
    {status && <StatusTracker statusData={status} />}
  </div>
);
