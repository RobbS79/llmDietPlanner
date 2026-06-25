import { ReactNode, HTMLAttributes, KeyboardEvent, MouseEvent } from 'react';
import { Link } from 'react-router-dom';
import { THEME } from '@/lib/theme';

interface CardProps extends HTMLAttributes<HTMLDivElement> {
  children: ReactNode;
  className?: string;
  /** When set, the card renders as a real navigational link (<a href>). */
  to?: string;
  /** 'app' (default) = dark auth-app surface from THEME; 'paper' = light public surface. */
  variant?: 'app' | 'paper';
}

export const Card = ({ children, className = "", onClick, to, variant = 'app', ...props }: CardProps) => {
  const isInteractive = !!onClick || !!to;
  const surface = variant === 'paper' ? 'bg-card border-line' : `${THEME.surface} ${THEME.border}`;
  const base = `${surface} border rounded-2xl shadow-lg transition-all`;
  const focusRing = isInteractive
    ? 'focus-visible:ring-2 focus-visible:ring-emerald-500 focus-visible:outline-none'
    : '';

  if (to) {
    return (
      <Link to={to} className={`block ${base} ${focusRing} ${className}`} onClick={onClick as ((e: MouseEvent) => void) | undefined}>
        {children}
      </Link>
    );
  }

  const handleKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    if (onClick && (e.key === 'Enter' || e.key === ' ')) {
      e.preventDefault();
      onClick(e as any);
    }
  };

  return (
    <div className={`${base} ${focusRing} ${className}`} onClick={onClick}
      {...(onClick ? { role: 'button', tabIndex: 0, onKeyDown: handleKeyDown } : {})} {...props}>
      {children}
    </div>
  );
};
