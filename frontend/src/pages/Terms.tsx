import { Link } from 'react-router-dom';
import { Zap, ArrowLeft } from 'lucide-react';

export const Terms = () => (
  <div className="min-h-screen bg-[#09090b] text-white">
    <nav className="flex items-center justify-between px-6 sm:px-12 py-6 max-w-4xl mx-auto">
      <Link to="/" className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-indigo-600 to-indigo-400 flex items-center justify-center shadow-lg">
          <Zap size={20} fill="currentColor" />
        </div>
        <span className="text-xl font-black tracking-tighter uppercase italic">
          Diet<span className="text-indigo-500 not-italic">Planner.</span>
        </span>
      </Link>
    </nav>

    <main className="max-w-4xl mx-auto px-6 sm:px-12 py-12">
      <Link to="/" className="text-xs font-bold text-zinc-600 hover:text-indigo-400 transition-colors inline-flex items-center gap-2 mb-8">
        <ArrowLeft size={14} /> Zpet na hlavni stranku
      </Link>

      <h1 className="text-4xl font-black tracking-tighter uppercase italic mb-12">
        Obchodni <span className="text-indigo-500 not-italic">podminky.</span>
      </h1>

      <div className="prose prose-invert prose-zinc max-w-none space-y-8 text-sm text-zinc-400 leading-relaxed">
        <section>
          <h2 className="text-lg font-black text-white uppercase tracking-tight mb-4">1. Zakladni ustanoveni</h2>
          <p>Tyto obchodni podminky upravuji prava a povinnosti uzivatelu sluzby DietPlanner AI. Pouzitim sluzby souhlasite s temito podminkami.</p>
        </section>

        <section>
          <h2 className="text-lg font-black text-white uppercase tracking-tight mb-4">2. Popis sluzby</h2>
          <p>DietPlanner AI je webova aplikace, ktera pomoci umele inteligence generuje personalizovane jidelnicky, recepty a nakupni seznamy s realnimi cenami z ceskych a slovenskych obchodu.</p>
        </section>

        <section>
          <h2 className="text-lg font-black text-white uppercase tracking-tight mb-4">3. Bezplatne pouziti</h2>
          <p>Kazdy uzivatel ma narok na 10 bezplatnych generovani jidelniku. Po vycerpani bezplatnych generovani je mozne zakoupit dalsi kredity.</p>
        </section>

        <section>
          <h2 className="text-lg font-black text-white uppercase tracking-tight mb-4">4. Omezeni odpovednosti</h2>
          <ul className="list-disc pl-5 space-y-2">
            <li>Vygenerovane jidelnicky jsou informativniho charakteru a nenahrazuji odbornou vyzivovou poradu.</li>
            <li>Ceny produktu jsou orientacni a mohou se lisit od aktualnich cen v obchodech.</li>
            <li>Neneseme odpovednost za alergicke reakce ci zdravotni komplikace.</li>
          </ul>
        </section>

        <section>
          <h2 className="text-lg font-black text-white uppercase tracking-tight mb-4">5. Uzivatelsky ucet</h2>
          <p>Uzivatel je povinen chranit sve prihlasovaci udaje. Za aktivitu na uctu je odpovedny vlastnik uctu. Ucet je mozne kdykoliv zrusit kontaktovanim podpory.</p>
        </section>

        <section>
          <h2 className="text-lg font-black text-white uppercase tracking-tight mb-4">6. Dusevni vlastnictvi</h2>
          <p>Veskery obsah aplikace (design, kod, texty) je chraneny autorskym pravem. Vygenerovane jidelnicky jsou urceny vyhradne pro osobni pouziti uzivatele.</p>
        </section>

        <section>
          <h2 className="text-lg font-black text-white uppercase tracking-tight mb-4">7. Kontakt</h2>
          <p>Pro dotazy, pripominky a reklamace nas kontaktujte na <a href="mailto:support@dietplanner.cz" className="text-indigo-400 hover:text-indigo-300">support@dietplanner.cz</a>.</p>
        </section>

        <p className="text-zinc-600 text-xs pt-8 border-t border-zinc-800">Posledni aktualizace: kveten 2026</p>
      </div>
    </main>
  </div>
);
