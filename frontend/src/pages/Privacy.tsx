import { Link } from 'react-router-dom';
import { ArrowLeft } from 'lucide-react';
import { PublicHeader } from '@/components/layout/PublicHeader';

export const Privacy = () => (
  <div className="min-h-screen bg-paper text-ink font-body">
    <PublicHeader />

    <main className="max-w-4xl mx-auto px-6 sm:px-12 py-12">
      <Link to="/" className="text-xs font-bold text-muted hover:text-green transition-colors inline-flex items-center gap-2 mb-8">
        <ArrowLeft size={14} /> Zpět na hlavní stránku
      </Link>

      <h1 className="font-display text-4xl font-black tracking-tight mb-12 text-ink">
        Zásady ochrany <span className="text-paprika">soukromí.</span>
      </h1>

      <div className="prose max-w-none space-y-8 text-sm text-ink leading-relaxed">
        <section>
          <h2 className="font-display text-lg font-black text-ink uppercase tracking-tight mb-4">1. Správce údajů</h2>
          <p className="text-muted">Správcem vašich osobních údajů je Vařto. V případě dotazů nás kontaktujte na <a href="mailto:admin@kentakin.eu" className="text-green hover:text-green-mid">admin@kentakin.eu</a>.</p>
        </section>

        <section>
          <h2 className="font-display text-lg font-black text-ink uppercase tracking-tight mb-4">2. Jaké údaje shromažďujeme</h2>
          <ul className="list-disc pl-5 space-y-2 text-muted">
            <li>Registrační údaje (e-mail, uživatelské jméno)</li>
            <li>Stravovací preference a cíle</li>
            <li>Vygenerované jídelníčky a nákupní seznamy</li>
            <li>Technické údaje (IP adresa, typ prohlížeče)</li>
          </ul>
        </section>

        <section>
          <h2 className="font-display text-lg font-black text-ink uppercase tracking-tight mb-4">3. Jak údaje používáme</h2>
          <p className="text-muted">Vaše údaje používáme výhradně k poskytování služby — generování personalizovaných jídelníků, nákupních seznamů a nutričních informací. Vaše data neprodáváme třetím stranám.</p>
        </section>

        <section>
          <h2 className="font-display text-lg font-black text-ink uppercase tracking-tight mb-4">4. Cookies</h2>
          <p className="text-muted">Používáme pouze technické cookies nezbytné pro fungování aplikace (autentizace, session). Nepoužíváme sledovací ani reklamní cookies.</p>
        </section>

        <section>
          <h2 className="font-display text-lg font-black text-ink uppercase tracking-tight mb-4">5. Vaše práva</h2>
          <p className="text-muted">Máte právo na přístup ke svým údajům, jejich opravu, vymazání a přenositelnost. Pro uplatnění těchto práv nás kontaktujte na výše uvedeném e-mailu.</p>
        </section>

        <section>
          <h2 className="font-display text-lg font-black text-ink uppercase tracking-tight mb-4">6. Zabezpečení</h2>
          <p className="text-muted">Vaše data chráníme šifrováním při přenosu (HTTPS/TLS) a bezpečným uložením v databázi. Přístup k datům mají pouze oprávněné osoby.</p>
        </section>

        <p className="text-muted text-xs pt-8 border-t border-line">Poslední aktualizace: květen 2026</p>
      </div>
    </main>
  </div>
);
