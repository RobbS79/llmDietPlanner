import { ReactNode } from 'react';
import { CheckCircle2, XCircle, Clock, AlertTriangle } from 'lucide-react';

const colors = {
  blue: 'bg-blue-500/10 text-blue-400 border-blue-500/20',
  emerald: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
  amber: 'bg-amber-500/10 text-amber-400 border-amber-500/20',
  rose: 'bg-rose-500/10 text-rose-400 border-rose-500/20',
};

const icons = {
  blue: Clock,
  emerald: CheckCircle2,
  amber: AlertTriangle,
  rose: XCircle,
};

export const Badge = ({ children, variant = 'blue' }: { children: ReactNode; variant?: keyof typeof colors }) => {
  const Icon = icons[variant];
  return (
    <span className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[10px] font-black uppercase tracking-wider border ${colors[variant]}`}>
      <Icon size={10} aria-hidden="true" />
      {children}
    </span>
  );
};
