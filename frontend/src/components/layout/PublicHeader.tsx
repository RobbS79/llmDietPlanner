import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Zap, Menu, X } from 'lucide-react';

const NAV_LINKS = [
  { to: '/recepty', label: 'Recepty' },
  { to: '/pricing', label: 'Ceník' },
];

const linkClass =
  'text-xs font-black text-zinc-200 hover:text-white uppercase tracking-widest transition-colors';

/**
 * Marketing/public header shared across Landing, Recepty, Pricing and About.
 * Below the `sm` breakpoint the links collapse into a hamburger drawer so the
 * primary CTA can never be clipped off the edge on a phone.
 */
export const PublicHeader = () => {
  const [open, setOpen] = useState(false);
  const close = () => setOpen(false);

  return (
    <header className="relative z-50">
      <nav className="flex items-center justify-between px-6 sm:px-12 py-6 max-w-7xl mx-auto">
        <Link to="/" className="flex items-center gap-3" onClick={close}>
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-emerald-600 to-emerald-400 flex items-center justify-center shadow-lg">
            <Zap size={20} fill="currentColor" />
          </div>
          <span className="text-xl font-black tracking-tighter uppercase italic">
            Diet<span className="text-emerald-500 not-italic">Planner.</span>
          </span>
        </Link>

        {/* Desktop nav */}
        <div className="hidden sm:flex items-center gap-4">
          {NAV_LINKS.map((l) => (
            <Link key={l.to} to={l.to} className={linkClass}>
              {l.label}
            </Link>
          ))}
          <Link to="/login" className={linkClass}>
            Přihlásit se
          </Link>
          <Link
            to="/login"
            className="bg-emerald-600 hover:bg-emerald-500 text-white px-6 py-2.5 rounded-xl text-xs font-black uppercase tracking-widest transition-all"
          >
            Začít zdarma
          </Link>
        </div>

        {/* Mobile hamburger */}
        <button
          type="button"
          className="sm:hidden p-2 -mr-2 text-zinc-100"
          onClick={() => setOpen((v) => !v)}
          aria-label={open ? 'Zavřít menu' : 'Otevřít menu'}
          aria-expanded={open}
        >
          {open ? <X size={24} /> : <Menu size={24} />}
        </button>
      </nav>

      {/* Mobile drawer */}
      {open && (
        <div className="sm:hidden absolute left-0 right-0 top-full bg-slate-900 border-y border-slate-700 px-6 py-3 flex flex-col shadow-2xl z-[100]">
          {NAV_LINKS.map((l) => (
            <Link
              key={l.to}
              to={l.to}
              onClick={close}
              className="py-3 text-sm font-black text-zinc-100 uppercase tracking-widest"
            >
              {l.label}
            </Link>
          ))}
          <Link
            to="/login"
            onClick={close}
            className="py-3 text-sm font-black text-zinc-100 uppercase tracking-widest"
          >
            Přihlásit se
          </Link>
          <Link
            to="/login"
            onClick={close}
            className="mt-2 mb-1 bg-emerald-600 text-white text-center px-6 py-3 rounded-xl text-sm font-black uppercase tracking-widest"
          >
            Začít zdarma
          </Link>
        </div>
      )}
    </header>
  );
};
