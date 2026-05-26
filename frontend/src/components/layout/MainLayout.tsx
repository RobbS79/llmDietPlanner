import { ReactNode } from 'react';
import { THEME } from '@/lib/theme';
import { Navbar } from './Navbar';

export const MainLayout = ({ children }: { children: ReactNode }) => (
  <div className={`h-screen flex flex-col ${THEME.bg} ${THEME.textPrimary} font-sans selection:bg-emerald-500/30 overflow-hidden`}>
    <a href="#main-content" className="skip-to-content">
      Prejit na obsah
    </a>
    <Navbar />
    <main id="main-content" className="flex-1 overflow-y-auto scroll-smooth flex flex-col relative z-0">
      {children}
    </main>
  </div>
);
