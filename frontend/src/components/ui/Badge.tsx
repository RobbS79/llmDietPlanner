import { ReactNode } from 'react';

const colors = {
  blue: 'bg-blue-500/10 text-blue-400 border-blue-500/20',
  emerald: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
  amber: 'bg-amber-500/10 text-amber-400 border-amber-500/20',
  rose: 'bg-rose-500/10 text-rose-400 border-rose-500/20',
};

export const Badge = ({ children, variant = 'blue' }: { children: ReactNode; variant?: keyof typeof colors }) => (
  <span className={`px-2.5 py-0.5 rounded-full text-[10px] font-black uppercase tracking-wider border ${colors[variant]}`}>
    {children}
  </span>
);
