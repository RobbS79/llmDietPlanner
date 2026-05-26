import { ReactNode, HTMLAttributes, KeyboardEvent } from 'react';
import { THEME } from '@/lib/theme';

interface CardProps extends HTMLAttributes<HTMLDivElement> {
  children: ReactNode;
  className?: string;
}

export const Card = ({ children, className = "", onClick, ...props }: CardProps) => {
  const isClickable = !!onClick;

  const handleKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    if (isClickable && (e.key === 'Enter' || e.key === ' ')) {
      e.preventDefault();
      onClick?.(e as any);
    }
  };

  return (
    <div
      className={`${THEME.surface} border ${THEME.border} rounded-2xl shadow-lg transition-all ${isClickable ? 'focus-visible:ring-2 focus-visible:ring-emerald-500 focus-visible:outline-none' : ''} ${className}`}
      onClick={onClick}
      {...(isClickable ? { role: 'button', tabIndex: 0, onKeyDown: handleKeyDown } : {})}
      {...props}
    >
      {children}
    </div>
  );
};
