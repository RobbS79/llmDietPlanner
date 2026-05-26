import { Link } from 'react-router-dom';
import { Zap, ArrowLeft } from 'lucide-react';

export const Privacy = () => (
  <div className="min-h-screen bg-[#09090b] text-white">
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
      <Link to="/" className="text-xs font-bold text-zinc-600 hover:text-emerald-400 transition-colors inline-flex items-center gap-2 mb-8">
        <ArrowLeft size={14} /> Zpet na hlavni stranku
      </Link>

      <h1 className="text-4xl font-black tracking-tighter uppercase italic mb-12">
        Zasady ochrany <span className="text-emerald-500 not-italic">soukromi.</span>
      </h1>

      <div className="prose prose-invert prose-zinc max-w-none space-y-8 text-sm text-zinc-400 leading-relaxed">
        <section>
          <h2 className="text-lg font-black text-white uppercase tracking-tight mb-4">1. Spravce udaju</h2>
          <p>Spravcem vasich osobnich udaju je DietPlanner AI. V pripade dotazu nas kontaktujte na <a href="mailto:support@dietplanner.cz" className="text-emerald-400 hover:text-emerald-300">support@dietplanner.cz</a>.</p>
        </section>

        <section>
          <h2 className="text-lg font-black text-white uppercase tracking-tight mb-4">2. Jake udaje shromazdujeme</h2>
          <ul className="list-disc pl-5 space-y-2">
            <li>Registracni udaje (e-mail, uzivatelske jmeno)</li>
            <li>Stravovaci preference a cile</li>
            <li>Vygenerovane jidelnicky a nakupni seznamy</li>
            <li>Technicke udaje (IP adresa, typ prohlizece)</li>
          </ul>
        </section>

        <section>
          <h2 className="text-lg font-black text-white uppercase tracking-tight mb-4">3. Jak udaje pouzivame</h2>
          <p>Vase udaje pouzivame vyhradne k poskytovani sluzby — generovani personalizovanych jidelniku, nakupnich seznamu a nutricnich informaci. Vase data neprodavame tretim stranam.</p>
        </section>

        <section>
          <h2 className="text-lg font-black text-white uppercase tracking-tight mb-4">4. Cookies</h2>
          <p>Pouzivame pouze technicke cookies nezbytne pro fungovani aplikace (autentizace, session). Nepouzivame sledovaci ani reklamni cookies.</p>
        </section>

        <section>
          <h2 className="text-lg font-black text-white uppercase tracking-tight mb-4">5. Vase prava</h2>
          <p>Mate pravo na pristup ke svym udajum, jejich opravu, vymazani a prenositelnost. Pro uplatneni techto prav nas kontaktujte na vyse uvedenem e-mailu.</p>
        </section>

        <section>
          <h2 className="text-lg font-black text-white uppercase tracking-tight mb-4">6. Zabezpeceni</h2>
          <p>Vase data chranime sifrovani pri prenosu (HTTPS/TLS) a bezpecnym ulozenim v databazi. Pristup k datum maji pouze opravnene osoby.</p>
        </section>

        <p className="text-zinc-600 text-xs pt-8 border-t border-zinc-800">Posledni aktualizace: kveten 2026</p>
      </div>
    </main>
  </div>
);
