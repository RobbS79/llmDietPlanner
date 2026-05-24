import { ReactNode, HTMLAttributes } from 'react';
import { THEME } from '@/lib/theme';

interface CardProps extends HTMLAttributes<HTMLDivElement> {
  children: ReactNode;
  className?: string;
}

export const Card = ({ children, className = "", ...props }: CardProps) => (
  <div
    className={`${THEME.surface} border ${THEME.border} rounded-2xl shadow-lg transition-all ${className}`}
    {...props}
  >
    {children}
  </div>
);
