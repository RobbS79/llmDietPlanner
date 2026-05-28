import { Link } from 'react-router-dom';
import { Zap, ArrowLeft } from 'lucide-react';

export const Privacy = () => (
  <div className="min-h-screen bg-[#1e293b] text-white">
    <nav className="flex items-center justify-between px-6 sm:px-12 py-6 max-w-4xl mx-auto">
      <Link to="/" className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-emerald-600 to-emerald-400 flex items-center justify-center shadow-lg">
          <Zap size={20} fill="currentColor" />
        </div>
        <span className="text-xl font-black tracking-tighter uppercase italic">
          Diet<span className="text-emerald-500 not-italic">Planner.</span>
        </span>
      </Link>
    </nav>

    <main className="max-w-4xl mx-auto px-6 sm:px-12 py-12">
      <Link to="/" className="text-xs font-bold text-zinc-400 hover:text-emerald-400 transition-colors inline-flex items-center gap-2 mb-8">
        <ArrowLeft size={14} /> Zpět na hlavní stránku
      </Link>

      <h1 className="text-4xl font-black tracking-tighter uppercase italic mb-12">
        Zásady ochrany <span className="text-emerald-500 not-italic">soukromí.</span>
      </h1>

      <div className="prose prose-invert prose-zinc max-w-none space-y-8 text-sm text-zinc-200 leading-relaxed">
        <section>
          <h2 className="text-lg font-black text-white uppercase tracking-tight mb-4">1. Správce údajů</h2>
          <p>Správcem vašich osobních údajů je DietPlanner AI. V případě dotazů nás kontaktujte na <a href="mailto:admin@kentakin.eu" className="text-emerald-400 hover:text-emerald-300">admin@kentakin.eu</a>.</p>
        </section>

        <section>
          <h2 className="text-lg font-black text-white uppercase tracking-tight mb-4">2. Jaké údaje shromažďujeme</h2>
          <ul className="list-disc pl-5 space-y-2">
            <li>Registrační údaje (e-mail, uživatelské jméno)</li>
            <li>Stravovací preference a cíle</li>
            <li>Vygenerované jídelníčky a nákupní seznamy</li>
            <li>Technické údaje (IP adresa, typ prohlížeče)</li>
          </ul>
        </section>

        <section>
          <h2 className="text-lg font-black text-white uppercase tracking-tight mb-4">3. Jak údaje používáme</h2>
          <p>Vaše údaje používáme výhradně k poskytování služby — generování personalizovaných jídelníků, nákupních seznamů a nutričních informací. Vaše data neprodáváme třetím stranám.</p>
        </section>

        <section>
          <h2 className="text-lg font-black text-white uppercase tracking-tight mb-4">4. Cookies</h2>
          <p>Používáme pouze technické cookies nezbytné pro fungování aplikace (autentizace, session). Nepoužíváme sledovací ani reklamní cookies.</p>
        </section>

        <section>
          <h2 className="text-lg font-black text-white uppercase tracking-tight mb-4">5. Vaše práva</h2>
          <p>Máte právo na přístup ke svým údajům, jejich opravu, vymazání a přenositelnost. Pro uplatnění těchto práv nás kontaktujte na výše uvedeném e-mailu.</p>
        </section>

        <section>
          <h2 className="text-lg font-black text-white uppercase tracking-tight mb-4">6. Zabezpečení</h2>
          <p>Vaše data chráníme šifrováním při přenosu (HTTPS/TLS) a bezpečným uložením v databázi. Přístup k datům mají pouze oprávněné osoby.</p>
        </section>

        <p className="text-zinc-400 text-xs pt-8 border-t border-slate-600">Poslední aktualizace: květen 2026</p>
      </div>
    </main>
  </div>
);
