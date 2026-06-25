import { Link } from 'react-router-dom';
import { ArrowLeft } from 'lucide-react';
import { PublicHeader } from '@/components/layout/PublicHeader';

export const Terms = () => (
  <div className="min-h-screen bg-paper text-ink font-body">
    <PublicHeader />

    <main className="max-w-4xl mx-auto px-6 sm:px-12 py-12">
      <Link to="/" className="text-xs font-bold text-muted hover:text-green transition-colors inline-flex items-center gap-2 mb-8">
        <ArrowLeft size={14} /> Zpět na hlavní stránku
      </Link>

      <h1 className="font-display text-4xl font-black tracking-tight mb-12 text-ink">
        Obchodní <span className="text-paprika">podmínky.</span>
      </h1>

      <div className="prose max-w-none space-y-8 text-sm text-ink leading-relaxed">
        <section>
          <h2 className="font-display text-lg font-black text-ink uppercase tracking-tight mb-4">1. Základní ustanovení</h2>
          <p className="text-muted">Tyto obchodní podmínky upravují práva a povinnosti uživatelů služby Vařto. Použitím služby souhlasíte s těmito podmínkami.</p>
        </section>

        <section>
          <h2 className="font-display text-lg font-black text-ink uppercase tracking-tight mb-4">2. Popis služby</h2>
          <p className="text-muted">Vařto je webová aplikace, která generuje personalizované jídelníčky, recepty a nákupní seznamy s reálními cenami z českých a slovenských obchodů.</p>
        </section>

        <section>
          <h2 className="font-display text-lg font-black text-ink uppercase tracking-tight mb-4">3. Bezplatné použití</h2>
          <p className="text-muted">Každý uživatel má nárok na 2 bezplatná generování jídelníčků. Po vyčerpání bezplatných generování je možné přejít na placený tarif.</p>
        </section>

        <section>
          <h2 className="font-display text-lg font-black text-ink uppercase tracking-tight mb-4">4. Omezení odpovědnosti</h2>
          <ul className="list-disc pl-5 space-y-2 text-muted">
            <li>Vygenerované jídelníčky jsou informativního charakteru a nenahrazují odbornou výživovou poradu.</li>
            <li>Ceny produktů jsou orientační a mohou se lišit od aktuálních cen v obchodech.</li>
            <li>Neneseme odpovědnost za alergické reakce či zdravotní komplikace.</li>
          </ul>
        </section>

        <section>
          <h2 className="font-display text-lg font-black text-ink uppercase tracking-tight mb-4">5. Uživatelský účet</h2>
          <p className="text-muted">Uživatel je povinen chránit své přihlašovací údaje. Za aktivitu na účtu je odpovědný vlastník účtu. Účet je možné kdykoliv zrušit kontaktováním podpory.</p>
        </section>

        <section>
          <h2 className="font-display text-lg font-black text-ink uppercase tracking-tight mb-4">6. Duševní vlastnictví</h2>
          <p className="text-muted">Veškerý obsah aplikace (design, kód, texty) je chráněný autorským právem. Vygenerované jídelníčky jsou určeny výhradně pro osobní použití uživatele.</p>
        </section>

        <section>
          <h2 className="font-display text-lg font-black text-ink uppercase tracking-tight mb-4">7. Kontakt</h2>
          <p className="text-muted">Pro dotazy, připomínky a reklamace nás kontaktujte na <a href="mailto:admin@kentakin.eu" className="text-green hover:text-green-mid">admin@kentakin.eu</a>.</p>
        </section>

        <p className="text-muted text-xs pt-8 border-t border-line">Poslední aktualizace: květen 2026</p>
      </div>
    </main>
  </div>
);
