import { Link } from 'react-router-dom';
import { ArrowLeft } from 'lucide-react';
import { PublicHeader } from '@/components/layout/PublicHeader';

export const About = () => (
  <div className="min-h-screen bg-paper text-ink font-body">
    <PublicHeader />

    <main className="max-w-4xl mx-auto px-6 sm:px-12 py-12">
      <Link to="/" className="text-xs font-bold text-muted hover:text-green transition-colors inline-flex items-center gap-2 mb-8">
        <ArrowLeft size={14} /> Zpět na hlavní stránku
      </Link>

      <h1 className="font-display text-4xl font-black tracking-tighter mb-12">
        Kdo za tím <span className="text-paprika">stojí.</span>
      </h1>

      <div className="flex flex-col sm:flex-row items-center sm:items-start gap-8 mb-12">
        {/* TODO: nahradit iniciály skutečnou fotkou (frontend/public/founder.jpg) — Robert se rozhodne, jak veřejné chce být */}
        <div className="shrink-0 w-32 h-32 rounded-2xl bg-green-soft flex items-center justify-center shadow-md">
          <span className="text-4xl font-black font-display text-green">RS</span>
        </div>
        <div>
          <h2 className="font-display text-2xl font-black tracking-tight text-ink mb-1">Robert Soroka</h2>
          <p className="text-sm font-bold uppercase tracking-wide text-muted mb-4">Zakladatel</p>
          <p className="text-base text-ink leading-relaxed">
            Pracuju na plný úvazek a sportuju, ale nikdy mi nezbýval čas plánovat zdravá jídla
            ani počítat nákup. Tak jsem vytvořil DietPlanner, který zvládne obojí za pár vteřin —
            a teď ho sdílím s vámi.
          </p>
        </div>
      </div>

      <div className="max-w-none space-y-6 text-base text-muted leading-relaxed border-t border-line pt-10">
        <p>
          Ahoj, jsem <strong className="text-ink">Robert Soroka</strong> a DietPlanner jsem
          vytvořil sám. Pracuju na plný úvazek, žiju aktivně a sportovně a o duševní zdraví dbám
          stejně jako o to fyzické — a právě tam můj problém začínal: nikdy mi nezbýval čas
          naplánovat jídla, která by byla zároveň opravdu zdravá a stála za to je jíst.
        </p>
        <p>
          Procházet e-shopy a rozhodovat se, co týden co týden vařit, mi ukrajovalo hodiny, které
          jsem neměl. Tak jsem si postavil nástroj, který mi pořád chyběl — takový, co naplánuje
          opravdová výživná jídla a ukáže přesně, kolik budou stát v obchodech kolem mě.
        </p>
        <p>
          Byl jsem svým prvním uživatelem, a po měsících, kdy jsem se na něj sám spoléhal,
          ho teď otevírám všem.
        </p>
      </div>

      <div className="mt-12 pt-10 border-t border-line">
        <Link
          to="/pricing"
          className="inline-flex items-center gap-2 rounded-xl bg-green hover:bg-green-mid px-6 py-3 text-sm font-bold text-white transition-colors"
        >
          Vyzkoušet DietPlanner
        </Link>
      </div>
    </main>
  </div>
);
