import { useState } from 'react';
import { Link, useNavigate, useLocation } from 'react-router-dom';
import { LayoutDashboard, Sparkles, Crown, LogOut, Menu, X } from 'lucide-react';
import { clearAuthTokens } from '@/lib/auth';

const navLinks = [
  { path: '/', label: 'Moje plány', icon: LayoutDashboard },
  { path: '/create', label: 'Nový plán', icon: Sparkles },
  { path: '/pricing', label: 'Ceník', icon: Crown },
];

export const Navbar = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const [mobileOpen, setMobileOpen] = useState(false);
  const isActive = (path: string) => location.pathname === path;

  const handleLogout = () => {
    clearAuthTokens();
    navigate('/login');
  };

  return (
    <header className="h-16 border-b border-line bg-paper/90 backdrop-blur-xl flex-none z-50">
      <div className="max-w-7xl mx-auto px-6 h-full flex justify-between items-center">
        <Link to="/" className="flex items-center gap-3 group">
          <span className="font-display font-extrabold text-2xl tracking-tight text-ink lowercase">
            vařto<span className="text-paprika">.</span>
          </span>
        </Link>

        <div className="hidden md:flex items-center gap-4">
          <nav className="flex items-center gap-1 bg-kraft p-1 rounded-xl border border-line">
            {navLinks.map((link) => (
              <Link
                key={link.path}
                to={link.path}
                className={`px-4 py-1.5 rounded-lg text-[10px] font-black uppercase tracking-widest flex items-center gap-2 transition-all
                ${isActive(link.path) ? 'bg-green text-white shadow-lg' : 'text-muted hover:text-ink hover:bg-card'}`}
              >
                <link.icon size={12} />
                {link.label}
              </Link>
            ))}
          </nav>
          <div className="h-6 w-px bg-line" />
          <button onClick={handleLogout} aria-label="Odhlásit se" className="p-2 text-muted hover:text-paprika-strong hover:bg-paprika-soft rounded-lg transition-all">
            <LogOut size={18} />
          </button>
        </div>

        <button className="md:hidden p-2 text-ink" onClick={() => setMobileOpen(!mobileOpen)} aria-label={mobileOpen ? 'Zavřít menu' : 'Otevřít menu'}>
          {mobileOpen ? <X size={20} /> : <Menu size={20} />}
        </button>
      </div>

      {mobileOpen && (
        <div className="md:hidden absolute top-16 left-0 right-0 bg-card border-b border-line p-4 space-y-2 flex flex-col z-[100] shadow-2xl">
          {navLinks.map((link) => (
            <Link
              key={link.path}
              to={link.path}
              onClick={() => setMobileOpen(false)}
              className={`flex items-center gap-3 p-4 rounded-xl font-bold uppercase text-xs tracking-widest ${isActive(link.path) ? 'bg-green text-white' : 'text-muted'}`}
            >
              <link.icon size={16} />
              {link.label}
            </Link>
          ))}
          <button onClick={handleLogout} className="flex items-center gap-3 p-4 rounded-xl font-bold uppercase text-xs tracking-widest text-paprika-strong">
            <LogOut size={16} /> Odhlásit se
          </button>
        </div>
      )}
    </header>
  );
};
