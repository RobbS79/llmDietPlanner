import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Menu, X } from 'lucide-react';

const NAV_LINKS = [
  { to: '/recepty', label: 'Recepty' },
  { to: '/pricing', label: 'Ceník' },
];

const linkClass =
  'text-ink/80 hover:text-ink font-body font-semibold transition-colors';

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
          <span className="font-display font-extrabold text-2xl tracking-tight text-ink lowercase">vařto<span className="text-paprika">.</span></span>
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
            className="bg-green hover:bg-green-mid text-white rounded-xl px-5 py-3 font-body font-bold transition-all"
          >
            Vytvořit jídelníček
          </Link>
        </div>

        {/* Mobile hamburger */}
        <button
          type="button"
          className="sm:hidden p-2.5 -mr-2 text-ink"
          onClick={() => setOpen((v) => !v)}
          aria-label={open ? 'Zavřít menu' : 'Otevřít menu'}
          aria-expanded={open}
        >
          {open ? <X size={24} /> : <Menu size={24} />}
        </button>
      </nav>

      {/* Mobile drawer */}
      {open && (
        <div className="sm:hidden absolute left-0 right-0 top-full bg-card border-y border-line px-6 py-3 flex flex-col shadow-2xl z-[100]">
          {NAV_LINKS.map((l) => (
            <Link
              key={l.to}
              to={l.to}
              onClick={close}
              className="py-3 text-sm font-body font-semibold text-ink"
            >
              {l.label}
            </Link>
          ))}
          <Link
            to="/login"
            onClick={close}
            className="py-3 text-sm font-body font-semibold text-ink"
          >
            Přihlásit se
          </Link>
          <Link
            to="/login"
            onClick={close}
            className="mt-2 mb-1 bg-green text-white text-center px-6 py-3 rounded-xl text-sm font-body font-bold"
          >
            Vytvořit jídelníček
          </Link>
        </div>
      )}
    </header>
  );
};
