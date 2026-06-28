import { ReactNode } from 'react';
import { CheckCircle2, XCircle, Clock, AlertTriangle } from 'lucide-react';

const colors = {
  blue: 'bg-blue-500/10 text-blue-700 border-blue-500/30',
  emerald: 'bg-green-soft text-green border-green/40',
  amber: 'bg-amber-500/15 text-amber-700 border-amber-500/30',
  rose: 'bg-paprika-soft text-paprika-strong border-paprika/30',
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
