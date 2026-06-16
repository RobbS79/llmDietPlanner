import { useState, useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Zap, Check, X, ArrowRight, ArrowLeft, HelpCircle } from 'lucide-react';
import { startCheckout, type BillingTier } from '@/lib/billing';
import { isAccessTokenValid } from '@/lib/auth';

const PLANS = [
  {
    name: 'Zdarma',
    price: 0,
    description: 'Pro vyzkoušení',
    cta: 'Začít zdarma',
    highlighted: false,
    features: [
      { text: '2 jídelníčky', included: true },
      { text: '3 úpravy každého jídelníčku', included: true },
      { text: 'Nákupní seznam', included: true },
      { text: 'Nutriční hodnoty', included: true },
      { text: 'Akční ceny z obchodů', included: false },
      { text: 'Akční ceny ze všech obchodů', included: false },
    ],
  },
  {
    name: 'Standard',
    tier: 'standard' as const,
    price: 99,
    description: 'Pro aktivní plánování',
    cta: 'Vybrat Standard',
    highlighted: true,
    features: [
      { text: '7 jídelníčků', included: true },
      { text: '10 úprav jídelníčku', included: true },
      { text: 'Nákupní seznam', included: true },
      { text: 'Nutriční hodnoty', included: true },
      { text: 'Akční ceny z jednoho obchodu', included: true },
      { text: 'Akční ceny ze všech obchodů', included: false },
    ],
  },
  {
    name: 'Premium',
    tier: 'premium' as const,
    price: 199,
    description: 'Pro maximum úspor',
    cta: 'Vybrat Premium',
    highlighted: false,
    features: [
      { text: '30 jídelníčků', included: true },
      { text: '5 úprav u každého jídelníčku', included: true },
      { text: 'Nákupní seznam', included: true },
      { text: 'Nutriční hodnoty', included: true },
      { text: 'Akční ceny z jednoho obchodu', included: true },
      { text: 'Akční ceny ze všech obchodů', included: true },
    ],
  },
];

const FAQ = [
  {
    q: 'Kolik jídelníčků mohu zdarma vygenerovat?',
    a: 'V bezplatném tarifu vytvoříte 2 jídelníčky, každý s možností 3 úprav. Každý jídelníček obsahuje kompletní vícedenné menu s recepty a nákupním seznamem.',
  },
  {
    q: 'Jak přesné jsou ceny z obchodů?',
    a: 'Ceny aktualizujeme pravidelně přímo z e-shopů jako Rohlík.cz, Košík.cz a dalších. Přesnost je obvykle 97% a vyšší.',
  },
  {
    q: 'Mohu plán kdykoliv zrušit?',
    a: 'Ano, předplatné můžete zrušit kdykoliv. Přístup k placeným funkcím vám zůstane do konce zaplaceného období.',
  },
  {
    q: 'Podporujete dietní omezení?',
    a: 'Ano, zohledníme veškerá omezení — bezlepkové, veganské, keto, vysoko proteinové, alergie a další. Stačí je popsat při vytváření plánu.',
  },
  {
    q: 'V jakých obchodech jsou dostupné ceny?',
    a: 'Aktuálně podporujeme Rohlík.cz, Košík.cz, Kaufland a další obchody v Česku a na Slovensku. Postupně přidáváme další.',
  },
];

export const Pricing = () => {
  const navigate = useNavigate();
  const [openFaq, setOpenFaq] = useState<number | null>(null);
  const [checkoutTier, setCheckoutTier] = useState<BillingTier | null>(null);
  const [checkoutError, setCheckoutError] = useState<string | null>(null);

  // CTA: free tier -> signup; paid tier -> Stripe Checkout if logged in,
  // otherwise login first and bounce back here to buy.
  const handleSelectPlan = async (tier?: BillingTier) => {
    if (!tier) {
      navigate('/login');
      return;
    }
    if (!isAccessTokenValid()) {
      navigate('/login?next=/pricing');
      return;
    }
    setCheckoutError(null);
    setCheckoutTier(tier);
    try {
      await startCheckout(tier); // redirects to Stripe on success
    } catch {
      setCheckoutError('Platbu se nepodařilo zahájit. Zkuste to prosím znovu.');
      setCheckoutTier(null);
    }
  };

  useEffect(() => {
    const schema = {
      '@context': 'https://schema.org',
      '@type': 'FAQPage',
      mainEntity: FAQ.map(item => ({
        '@type': 'Question',
        name: item.q,
        acceptedAnswer: { '@type': 'Answer', text: item.a },
      })),
    };
    const script = document.createElement('script');
    script.type = 'application/ld+json';
    script.textContent = JSON.stringify(schema);
    script.id = 'faq-schema';
    document.head.appendChild(script);
    return () => { document.getElementById('faq-schema')?.remove(); };
  }, []);

  return (
    <div className="min-h-screen bg-[#1e293b] text-white">
      <nav className="flex items-center justify-between px-6 sm:px-12 py-6 max-w-7xl mx-auto">
        <Link to="/" className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-emerald-600 to-emerald-400 flex items-center justify-center shadow-lg">
            <Zap size={20} fill="currentColor" />
          </div>
          <span className="text-xl font-black tracking-tighter uppercase italic">
            Diet<span className="text-emerald-500 not-italic">Planner.</span>
          </span>
        </Link>
        <button onClick={() => navigate('/login')} className="bg-emerald-600 hover:bg-emerald-500 text-white px-6 py-2.5 rounded-xl text-xs font-black uppercase tracking-widest transition-all">
          Začít zdarma
        </button>
      </nav>

      <main className="max-w-6xl mx-auto px-6 sm:px-12 py-12">
        <Link to="/" className="text-xs font-bold text-zinc-400 hover:text-emerald-400 transition-colors inline-flex items-center gap-2 mb-8">
          <ArrowLeft size={14} /> Zpět na hlavní stránku
        </Link>

        <header className="text-center mb-16 space-y-6">
          <p className="text-[10px] font-black text-emerald-500 uppercase tracking-[1em]">Ceník</p>
          <h1 className="text-5xl sm:text-6xl font-black tracking-tighter uppercase italic leading-[0.85]">
            Jednoduchý <span className="text-emerald-500 not-italic">ceník.</span>
          </h1>
          <p className="text-zinc-200 text-lg max-w-md mx-auto">
            Začněte zdarma. Upgradujte, až budete připraveni.
          </p>
        </header>

        {checkoutError && (
          <div className="max-w-md mx-auto mb-8 rounded-xl border border-red-500/40 bg-red-500/10 px-5 py-3 text-center text-sm text-red-300">
            {checkoutError}
          </div>
        )}

        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-6 mb-24">
          {PLANS.map((plan) => (
            <div
              key={plan.name}
              className={`rounded-3xl p-8 transition-all ${
                plan.highlighted
                  ? 'bg-gradient-to-br from-emerald-600/10 to-teal-600/5 border-2 border-emerald-500/30 shadow-[0_0_60px_rgba(5,150,105,0.1)]'
                  : 'bg-slate-700/50 border border-slate-600'
              }`}
            >
              {plan.highlighted && (
                <div className="inline-block px-3 py-1 bg-emerald-600 rounded-lg text-[9px] font-black uppercase tracking-widest mb-6 shadow-lg">
                  Doporučeno
                </div>
              )}

              <h2 className="text-3xl font-black uppercase italic tracking-tighter mb-2">{plan.name}</h2>
              <p className="text-zinc-300 text-sm mb-8">{plan.description}</p>

              <div className="mb-8">
                {plan.price === 0 ? (
                  <p className="text-5xl font-black tracking-tighter">
                    0 <span className="text-zinc-300 text-lg">CZK</span>
                  </p>
                ) : (
                  <p className="text-5xl font-black tracking-tighter">
                    {plan.price} <span className="text-zinc-300 text-lg">CZK/měsíc</span>
                  </p>
                )}
              </div>

              <button
                onClick={() => handleSelectPlan((plan as { tier?: BillingTier }).tier)}
                disabled={checkoutTier !== null}
                className={`w-full h-14 rounded-xl font-black uppercase text-xs tracking-widest transition-all active:scale-[0.98] flex items-center justify-center gap-3 mb-10 disabled:opacity-60 disabled:cursor-not-allowed ${
                  plan.highlighted
                    ? 'bg-white text-black shadow-2xl hover:shadow-white/10'
                    : 'bg-slate-600 text-white hover:bg-zinc-700'
                }`}
              >
                {checkoutTier === (plan as { tier?: BillingTier }).tier
                  ? 'Přesměrování…'
                  : plan.cta}{' '}
                <ArrowRight size={16} />
              </button>

              <ul className="space-y-4">
                {plan.features.map((f) => (
                  <li key={f.text} className="flex items-center gap-3 text-sm">
                    {f.included ? (
                      <Check size={16} className="text-emerald-400 shrink-0" />
                    ) : (
                      <X size={16} className="text-zinc-700 shrink-0" />
                    )}
                    <span className={f.included ? 'text-zinc-300' : 'text-zinc-400'}>{f.text}</span>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        <div className="text-center mb-16">
          <p className="text-zinc-300 text-sm">
            Stojí méně než jedno kafe týdně. Průměrný uživatel ušetří <strong className="text-white">850 CZK měsíčně</strong> na nákupech.
          </p>
        </div>

        {/* FAQ */}
        <section className="max-w-3xl mx-auto mb-24">
          <div className="text-center mb-12">
            <p className="text-[10px] font-black text-emerald-500 uppercase tracking-[1em] mb-4">FAQ</p>
            <h2 className="text-3xl sm:text-4xl font-black tracking-tighter">Časté dotazy</h2>
          </div>

          <div className="space-y-3">
            {FAQ.map((item, i) => (
              <div key={i} className="bg-slate-700/50 border border-slate-600 rounded-2xl overflow-hidden">
                <button
                  onClick={() => setOpenFaq(openFaq === i ? null : i)}
                  className="w-full flex items-center justify-between p-6 text-left"
                >
                  <span className="text-sm font-bold text-white pr-4">{item.q}</span>
                  <HelpCircle size={18} className={`shrink-0 transition-colors ${openFaq === i ? 'text-emerald-400' : 'text-zinc-400'}`} />
                </button>
                {openFaq === i && (
                  <div className="px-6 pb-6 pt-0">
                    <p className="text-sm text-zinc-200 leading-relaxed">{item.a}</p>
                  </div>
                )}
              </div>
            ))}
          </div>
        </section>

        {/* Bottom CTA */}
        <section className="text-center pb-12">
          <div className="bg-gradient-to-br from-emerald-600/10 to-teal-600/5 border border-emerald-500/10 rounded-3xl p-12 sm:p-16">
            <h2 className="text-3xl sm:text-4xl font-black tracking-tighter mb-4">Připraveni šetřit čas i peníze?</h2>
            <p className="text-zinc-200 mb-8">Začněte se 2 jídelníčky zdarma. Bez kreditní karty.</p>
            <button onClick={() => navigate('/login')} className="bg-white text-black px-10 py-4 rounded-2xl font-black uppercase text-sm tracking-widest shadow-2xl hover:shadow-white/10 transition-all active:scale-[0.98] inline-flex items-center gap-3">
              Vytvořit jídelníček zdarma <ArrowRight size={18} />
            </button>
          </div>
        </section>
      </main>

      <footer className="px-6 sm:px-12 py-12 max-w-7xl mx-auto border-t border-slate-700">
        <div className="flex flex-col sm:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-2">
            <Zap size={16} className="text-emerald-500" />
            <span className="text-sm font-black tracking-tighter uppercase italic text-zinc-400">DietPlanner.</span>
          </div>
          <div className="flex items-center gap-6">
            <Link to="/privacy" className="text-xs font-bold text-zinc-300 hover:text-white transition-colors">Zásady ochrany soukromí</Link>
            <Link to="/terms" className="text-xs font-bold text-zinc-300 hover:text-white transition-colors">Obchodní podmínky</Link>
          </div>
        </div>
      </footer>
    </div>
  );
};
