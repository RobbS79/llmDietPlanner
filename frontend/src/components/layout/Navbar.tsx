import { useState } from 'react';
import { Link, useNavigate, useLocation } from 'react-router-dom';
import { Zap, LayoutDashboard, Sparkles, LogOut, Menu, X } from 'lucide-react';

const navLinks = [
  { path: '/', label: 'Moje plány', icon: LayoutDashboard },
  { path: '/create', label: 'Nový plán', icon: Sparkles },
];

export const Navbar = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const [mobileOpen, setMobileOpen] = useState(false);
  const isActive = (path: string) => location.pathname === path;

  const handleLogout = () => {
    localStorage.clear();
    navigate('/login');
  };

  return (
    <header className="h-16 border-b border-zinc-800 bg-[#09090b]/80 backdrop-blur-xl flex-none z-50">
      <div className="max-w-7xl mx-auto px-6 h-full flex justify-between items-center">
        <Link to="/" className="flex items-center gap-3 group">
          <div className="w-8 h-8 rounded-lg bg-emerald-600 flex items-center justify-center text-white shadow-glow-sm">
            <Zap size={18} fill="currentColor" />
          </div>
          <span className="text-xl font-bold tracking-tight text-white uppercase italic">
            DietPlanner<span className="text-emerald-500 not-italic">.</span>
          </span>
        </Link>

        <div className="hidden md:flex items-center gap-4">
          <nav className="flex items-center gap-1 bg-zinc-900 p-1 rounded-xl border border-zinc-800">
            {navLinks.map((link) => (
              <Link
                key={link.path}
                to={link.path}
                className={`px-4 py-1.5 rounded-lg text-[10px] font-black uppercase tracking-widest flex items-center gap-2 transition-all
                ${isActive(link.path) ? 'bg-emerald-600 text-white shadow-lg' : 'text-zinc-500 hover:text-zinc-200 hover:bg-zinc-800'}`}
              >
                <link.icon size={12} />
                {link.label}
              </Link>
            ))}
          </nav>
          <div className="h-6 w-px bg-zinc-800" />
          <button onClick={handleLogout} aria-label="Odhlásit se" className="p-2 text-zinc-500 hover:text-rose-500 hover:bg-rose-500/10 rounded-lg transition-all">
            <LogOut size={18} />
          </button>
        </div>

        <button className="md:hidden p-2 text-zinc-400" onClick={() => setMobileOpen(!mobileOpen)} aria-label={mobileOpen ? 'Zavřít menu' : 'Otevřít menu'}>
          {mobileOpen ? <X size={20} /> : <Menu size={20} />}
        </button>
      </div>

      {mobileOpen && (
        <div className="md:hidden absolute top-16 left-0 right-0 bg-zinc-950 border-b border-zinc-800 p-4 space-y-2 flex flex-col z-[100] shadow-2xl">
          {navLinks.map((link) => (
            <Link
              key={link.path}
              to={link.path}
              onClick={() => setMobileOpen(false)}
              className={`flex items-center gap-3 p-4 rounded-xl font-bold uppercase text-xs tracking-widest ${isActive(link.path) ? 'bg-emerald-600 text-white' : 'text-zinc-500'}`}
            >
              <link.icon size={16} />
              {link.label}
            </Link>
          ))}
          <button onClick={handleLogout} className="flex items-center gap-3 p-4 rounded-xl font-bold uppercase text-xs tracking-widest text-rose-500">
            <LogOut size={16} /> Odhlásit se
          </button>
        </div>
      )}
    </header>
  );
};
