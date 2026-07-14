import { useState, useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Check, X, ArrowRight, ArrowLeft, HelpCircle } from 'lucide-react';
import { startCheckout, type BillingTier } from '@/lib/billing';
import { isAccessTokenValid } from '@/lib/auth';
import { PublicHeader } from '@/components/layout/PublicHeader';
import { trackCheckoutStarted } from '@/lib/analytics';

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
    a: 'Ceny vycházejí z reálných cen v českých e-shopech a pravidelně je aktualizujeme. U akčních nabídek a podle aktuální dostupnosti se mohou drobně lišit.',
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
      trackCheckoutStarted(); // fire InitiateCheckout right before Stripe redirect
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
    <div className="min-h-screen bg-paper text-ink font-body">
      <PublicHeader />

      <main className="max-w-6xl mx-auto px-6 sm:px-12 py-12">
        <Link
          to="/"
          className="text-xs font-bold text-muted hover:text-green transition-colors inline-flex items-center gap-2 mb-8"
        >
          <ArrowLeft size={14} /> Zpět na hlavní stránku
        </Link>

        <header className="text-center mb-16 space-y-6">
          <p className="text-[10px] font-black text-green uppercase tracking-[1em]">Ceník</p>
          <h1 className="font-display text-5xl sm:text-6xl font-extrabold tracking-tight leading-tight text-ink">
            Jednoduchý <span className="text-paprika">ceník.</span>
          </h1>
          <p className="text-muted text-lg max-w-md mx-auto">
            Začněte zdarma. Upgradujte, až budete připraveni.
          </p>
        </header>

        {checkoutError && (
          <div className="max-w-md mx-auto mb-8 rounded-xl border border-paprika/40 bg-paprika-soft px-5 py-3 text-center text-sm text-paprika-strong">
            {checkoutError}
          </div>
        )}

        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-6 mb-24">
          {PLANS.map((plan) => (
            <div
              key={plan.name}
              className={`rounded-3xl transition-all flex flex-col ${
                plan.highlighted
                  ? 'bg-card border-2 border-green shadow-lg'
                  : 'bg-card border border-line'
              }`}
            >
              {/* Card header zone */}
              <div className={`rounded-t-3xl px-8 pt-8 pb-6 ${plan.highlighted ? 'bg-green-soft' : ''}`}>
                {plan.highlighted && (
                  <div className="inline-block px-3 py-1 bg-green text-white rounded-lg text-[10px] font-bold uppercase tracking-wide mb-4">
                    Doporučeno
                  </div>
                )}

                <h2 className="font-display text-2xl font-bold text-ink mb-1">{plan.name}</h2>
                <p className="text-muted text-sm mb-6">{plan.description}</p>

                <div className="mb-2">
                  {plan.price === 0 ? (
                    <p className="font-price text-5xl font-bold text-ink">
                      0 <span className="text-muted text-lg font-normal">Kč</span>
                    </p>
                  ) : (
                    <p className="font-price text-5xl font-bold text-ink">
                      {plan.price} <span className="text-muted text-lg font-normal">Kč/měsíc</span>
                    </p>
                  )}
                </div>
              </div>

              {/* Card body */}
              <div className="px-8 pb-8 flex flex-col flex-1">
                <button
                  onClick={() => handleSelectPlan((plan as { tier?: BillingTier }).tier)}
                  disabled={checkoutTier !== null}
                  className={`w-full h-14 rounded-xl font-bold text-sm transition-all active:scale-[0.98] flex items-center justify-center gap-3 mb-8 mt-6 disabled:opacity-60 disabled:cursor-not-allowed ${
                    plan.highlighted
                      ? 'bg-green hover:bg-green-mid text-white shadow-md'
                      : 'bg-green hover:bg-green-mid text-white'
                  }`}
                >
                  {checkoutTier === (plan as { tier?: BillingTier }).tier
                    ? 'Přesměrování…'
                    : plan.cta}{' '}
                  <ArrowRight size={16} />
                </button>

                <ul className="space-y-4 flex-1">
                  {plan.features.map((f) => (
                    <li key={f.text} className="flex items-center gap-3 text-sm">
                      {f.included ? (
                        <Check size={16} className="text-green shrink-0" />
                      ) : (
                        <X size={16} className="text-line shrink-0" />
                      )}
                      <span className={f.included ? 'text-ink' : 'text-muted'}>{f.text}</span>
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          ))}
        </div>

        <div className="text-center mb-16">
          <p className="text-muted text-sm">
            Stojí méně než jedno kafe týdně. Průměrný uživatel ušetří <strong className="text-ink">850 Kč měsíčně</strong> na nákupech.
          </p>
        </div>

        {/* FAQ */}
        <section className="max-w-3xl mx-auto mb-24">
          <div className="text-center mb-12">
            <p className="text-[10px] font-black text-green uppercase tracking-[1em] mb-4">FAQ</p>
            <h2 className="font-display text-3xl sm:text-4xl font-bold text-ink">Časté dotazy</h2>
          </div>

          <div className="space-y-3">
            {FAQ.map((item, i) => (
              <div key={i} className="bg-card border border-line rounded-2xl overflow-hidden">
                <button
                  onClick={() => setOpenFaq(openFaq === i ? null : i)}
                  className="w-full flex items-center justify-between p-6 text-left"
                >
                  <span className="text-sm font-bold text-ink pr-4">{item.q}</span>
                  <HelpCircle
                    size={18}
                    className={`shrink-0 transition-colors ${openFaq === i ? 'text-green' : 'text-muted'}`}
                  />
                </button>
                {openFaq === i && (
                  <div className="px-6 pb-6 pt-0 bg-kraft">
                    <p className="text-sm text-ink leading-relaxed">{item.a}</p>
                  </div>
                )}
              </div>
            ))}
          </div>
        </section>

        {/* Bottom CTA */}
        <section className="text-center pb-12">
          <div className="bg-green-soft border border-green/20 rounded-3xl p-12 sm:p-16">
            <h2 className="font-display text-3xl sm:text-4xl font-bold text-ink mb-4">
              Připraveni šetřit čas i peníze?
            </h2>
            <p className="text-muted mb-8">Začněte se 2 jídelníčky zdarma. Bez kreditní karty.</p>
            <button
              onClick={() => navigate('/login')}
              className="bg-green hover:bg-green-mid text-white px-10 py-4 rounded-2xl font-bold text-sm transition-all active:scale-[0.98] inline-flex items-center gap-3"
            >
              Vytvořit jídelníček zdarma <ArrowRight size={18} />
            </button>
          </div>
        </section>
      </main>

      <footer className="px-6 sm:px-12 py-12 max-w-7xl mx-auto border-t border-line">
        <div className="flex flex-col sm:flex-row items-center justify-between gap-4">
          <span className="font-display font-extrabold text-xl tracking-tight text-ink lowercase">
            vařto<span className="text-paprika">.</span>
          </span>
          <div className="flex items-center gap-6">
            <Link to="/privacy" className="text-xs font-bold text-muted hover:text-ink transition-colors">
              Zásady ochrany soukromí
            </Link>
            <Link to="/terms" className="text-xs font-bold text-muted hover:text-ink transition-colors">
              Obchodní podmínky
            </Link>
          </div>
        </div>
      </footer>
    </div>
  );
};
