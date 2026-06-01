import { Link } from 'react-router-dom';
import { Zap, ArrowLeft } from 'lucide-react';

export const Terms = () => (
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
        Obchodní <span className="text-emerald-500 not-italic">podmínky.</span>
      </h1>

      <div className="prose prose-invert prose-zinc max-w-none space-y-8 text-sm text-zinc-200 leading-relaxed">
        <section>
          <h2 className="text-lg font-black text-white uppercase tracking-tight mb-4">1. Základní ustanovení</h2>
          <p>Tyto obchodní podmínky upravují práva a povinnosti uživatelů služby DietPlanner AI. Použitím služby souhlasíte s těmito podmínkami.</p>
        </section>

        <section>
          <h2 className="text-lg font-black text-white uppercase tracking-tight mb-4">2. Popis služby</h2>
          <p>DietPlanner AI je webová aplikace, která pomocí umělé inteligence generuje personalizované jídelníčky, recepty a nákupní seznamy s reálními cenami z českých a slovenských obchodů.</p>
        </section>

        <section>
          <h2 className="text-lg font-black text-white uppercase tracking-tight mb-4">3. Bezplatné použití</h2>
          <p>Každý uživatel má nárok na 2 bezplatná generování jídelníčků. Po vyčerpání bezplatných generování je možné přejít na placený tarif.</p>
        </section>

        <section>
          <h2 className="text-lg font-black text-white uppercase tracking-tight mb-4">4. Omezení odpovědnosti</h2>
          <ul className="list-disc pl-5 space-y-2">
            <li>Vygenerované jídelníčky jsou informativního charakteru a nenahrazují odbornou výživovou poradu.</li>
            <li>Ceny produktů jsou orientační a mohou se lišit od aktuálních cen v obchodech.</li>
            <li>Neneseme odpovědnost za alergické reakce či zdravotní komplikace.</li>
          </ul>
        </section>

        <section>
          <h2 className="text-lg font-black text-white uppercase tracking-tight mb-4">5. Uživatelský účet</h2>
          <p>Uživatel je povinen chránit své přihlašovací údaje. Za aktivitu na účtu je odpovědný vlastník účtu. Účet je možné kdykoliv zrušit kontaktováním podpory.</p>
        </section>

        <section>
          <h2 className="text-lg font-black text-white uppercase tracking-tight mb-4">6. Duševní vlastnictví</h2>
          <p>Veškerý obsah aplikace (design, kód, texty) je chráněný autorským právem. Vygenerované jídelníčky jsou určeny výhradně pro osobní použití uživatele.</p>
        </section>

        <section>
          <h2 className="text-lg font-black text-white uppercase tracking-tight mb-4">7. Kontakt</h2>
          <p>Pro dotazy, připomínky a reklamace nás kontaktujte na <a href="mailto:admin@kentakin.eu" className="text-emerald-400 hover:text-emerald-300">admin@kentakin.eu</a>.</p>
        </section>

        <p className="text-zinc-400 text-xs pt-8 border-t border-slate-600">Poslední aktualizace: květen 2026</p>
      </div>
    </main>
  </div>
);
